# app/services/assignment.py
from firebase_admin import db as rtdb
from app.main.firebase import (
    server_ts, SCENARIOS_PATH, TRIALS_PATH,
    COUNTS_SCEN, COUNTS_TRIAL, ASSIGN_PATH, PARTIC_PATH
)
import random
# from app.main.metrics import choose_and_increment_one
from app.main.catalog import list_scenarios, list_trials

from app.main.comparison import ensure_comparison_trials


# app/services/assignment.py (top of file where levels/constants live)

# ---- OA-16 base (use first 4 cols of your 5-col table) ----
OA_L16_4x4 = [
    [1,1,1,1],
    [1,2,2,2],
    [1,3,3,3],
    [1,4,4,4],
    [2,1,2,3],
    [2,2,1,4],
    [2,3,4,1],
    [2,4,3,2],
    [3,1,3,4],
    [3,2,4,3],
    [3,3,1,2],
    [3,4,2,1],
    [4,1,4,2],
    [4,2,3,1],
    [4,3,2,4],
    [4,4,1,3],
]

CRIT_ORDER = ["recommendation", "frequency", "missing", "coverage"]

def _oa32_from_oa16() -> list[list[int]]:
    """
    Build OA(32, 4, 4, 2) by stacking OA-16 with a level-permuted copy.
    Column-wise permutations are bijections on {1,2,3,4}, preserving strength-2.
    """
    # distinct permutations per column
    perms = [
        {1:2, 2:3, 3:4, 4:1},  # col1 cyclic shift
        {1:3, 2:4, 3:1, 4:2},  # col2 2-cycles
        {1:4, 2:1, 3:2, 4:3},  # col3 reverse cycle
        {1:2, 2:1, 3:4, 4:3},  # col4 swap pairs
    ]
    blockA = [row[:] for row in OA_L16_4x4]
    blockB = [[perms[j][row[j]] for j in range(4)] for row in OA_L16_4x4]
    return blockA + blockB  # 32×4

LEVELS = {
    "recommendation": ["95", "85", "75", "65"],
    "frequency":      ["Daily", "Weekly", "Monthly", "Quarterly"],
    "missing":        ["5", "10", "15", "20"],
    "coverage":       ["35", "30", "25", "20"],
}

def _oa_row_to_dataset(row4: list[int]) -> dict[str, str]:
    ds: dict[str, str] = {}
    for j, crit in enumerate(CRIT_ORDER):
        ds[crit] = LEVELS[crit][row4[j]-1]  # 1..4 -> 0..3
    return ds

def _ensure_scenario_trials_OA32(sid: str) -> list[str]:
    """
    Idempotently create exactly 32 trials under /scenarios/{sid}/trials
    using OA(32,4,4,2). Single-option trials (no A/B).
    """
    base = f"{SCENARIOS_PATH}/{sid}/trials"
    existing = rtdb.reference(base).get()
    if isinstance(existing, dict) and existing:
        return list(existing.keys())

    oa32 = _oa32_from_oa16()
    datasets = [_oa_row_to_dataset(r) for r in oa32]  # 32 dicts

    payload: dict[str, dict] = {
        str(i): {"option": ds, "created": server_ts()} for i, ds in enumerate(datasets, start=1)
    }
    rtdb.reference(base).update(payload)
    return list(payload.keys())

def choose_and_increment_one(path: str, candidate_ids: list[str]) -> str:
    """
    RTDB transactional chooser:
    - normalizes existing node (None | list | dict) to a dict with string keys
    - initializes missing counters to 0
    - chooses among min-count IDs with random tiebreak
    - increments chosen ID atomically
    """
    chosen = {"id": None}
    counts_ref = rtdb.reference(path)

    # Ensure we always look up string keys (Firebase keys are strings)
    cand_keys = [str(cid) for cid in candidate_ids]

    def _normalize(node) -> dict:
        # Start with everything at 0 so we don't miss any candidate
        norm = {k: 0 for k in cand_keys}

        if node is None:
            return norm

        if isinstance(node, dict):
            # Coerce to ints; keep only candidates we care about
            for k, v in node.items():
                sk = str(k)
                if sk in norm:
                    try:
                        norm[sk] = int(v or 0)
                    except Exception:
                        norm[sk] = 0
            return norm

        if isinstance(node, list):
            # Map by position if available; otherwise leave 0
            # NOTE: we assume candidate_ids has a stable order (e.g., ["1","2",...])
            for i, key in enumerate(cand_keys):
                if i < len(node):
                    try:
                        norm[key] = int(node[i] or 0)
                    except Exception:
                        norm[key] = 0
            return norm

        # Unexpected type → fall back to zeros
        return norm

    def txn(curr):
        curr = _normalize(curr)

        # Pick among the minimum-count candidates
        min_count = min(curr[k] for k in cand_keys)
        pool = [k for k in cand_keys if curr[k] == min_count]

        cid = random.choice(pool)
        curr[cid] += 1
        chosen["id"] = cid
        return curr

    counts_ref.transaction(txn)
    return chosen["id"]


# def choose_and_increment_one(path: str, candidate_ids: list[str]) -> str:
#     """
#     Generic RTDB transactional chooser:
#     - initializes missing counters to 0
#     - chooses among min-count IDs with random tiebreak
#     - increments chosen ID atomically
#     """
#     chosen = {"id": None}
#     counts_ref = rtdb.reference(path)

#     def txn(curr):
#         curr = curr or {}
#         for cid in candidate_ids:
#             curr.setdefault(cid, 0)
#         min_count = min(curr[cid] for cid in candidate_ids)
#         pool = [cid for cid in candidate_ids if curr[cid] == min_count]
#         cid = random.choice(pool)
#         curr[cid] += 1
#         chosen["id"] = cid
#         return curr

#     counts_ref.transaction(txn)
#     return chosen["id"]

def create_participant_pid() -> str:
    ref = rtdb.reference(PARTIC_PATH).push({"created": server_ts()})
    return ref.key  # pid

def get_assignment(pid: str) -> tuple[str | None, list[str] | None]:
    doc = rtdb.reference(f"{ASSIGN_PATH}/{pid}").get() or {}
    return (doc.get("scenario_id"), doc.get("trial_ids"), doc.get("comparison_trials"))

# def assign_participant(pid: str, n_trials: int = 30) -> tuple[str, list[str]]:
#     """
#     Assign a balanced scenario and n balanced trials, persist under /assignments/{pid}.
#     Idempotent for an already-assigned pid.
#     """
#     existing_sid, existing_trials = get_assignment(pid)
#     if existing_sid and existing_trials:
#         return existing_sid, existing_trials

#     scenarios = list_scenarios()
#     trials    = list_trials()

#     # Balance participants across scenarios
#     sid = choose_and_increment_one(COUNTS_SCEN, list(scenarios.keys()))

#     # Balance trials globally (keep your original behavior)
#     chosen_trials: list[str] = []
#     candidate_tids = list(trials.keys())
#     for _ in range(n_trials):
#         tid = choose_and_increment_one(COUNTS_TRIAL, candidate_tids)
#         chosen_trials.append(tid)

#     # Persist both (multi-location write)
#     rtdb.reference("/").update({
#         f"{ASSIGN_PATH}/{pid}": {
#             "scenario_id": sid,
#             "trial_ids": chosen_trials,
#         },
#         f"{PARTIC_PATH}/{pid}/assigned": {
#             "scenario_id": sid,
#             "trial_ids": chosen_trials,
#             "ts": server_ts(),
#         },
#     })
#     return sid, chosen_trials
def assign_participant(pid: str, n_trials: int = 32) -> tuple[str, list[str]]:
    existing_sid, existing_trials, existing_comparison = get_assignment(pid)
    if existing_sid and existing_trials and existing_comparison:
        return existing_sid, existing_trials, existing_comparison

    scenarios = list_scenarios()
    sid = choose_and_increment_one(COUNTS_SCEN, list(scenarios.keys()))

    # Ensure OA-32 trials exist for this scenario
    trial_ids = _ensure_scenario_trials_OA32(sid)

    # Unique shuffled order per participant; no repeats
    random.shuffle(trial_ids)
    chosen = trial_ids[: min(n_trials, len(trial_ids))]

    # Materialize levels for each chosen trial and store alongside ids
    trials_with_levels = []
    for tid in chosen:
        node = rtdb.reference(f"{SCENARIOS_PATH}/{sid}/trials/{tid}").get() or {}
        trials_with_levels.append({
            "id": str(tid),
            "option": node.get("option", {})  # levels dict {recommendation, frequency, ...}
        })
    ensure_comparison_trials(pid, sid)

    rtdb.reference("/").update({
        f"{ASSIGN_PATH}/{pid}": {
            "scenario_id": sid,
            "trial_ids": chosen,
            "trials": trials_with_levels,   # <-- ordered list with levels
        },
        f"{PARTIC_PATH}/{pid}/assigned": {
            "scenario_id": sid,
            "trial_ids": chosen,
            "ts": server_ts(),
        },
    })
    return sid, chosen
