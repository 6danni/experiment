# app/main/assignments_targeted_levels.py
import math, random
from typing import List, Tuple
from firebase_admin import db as rtdb
from app.main.firebase import server_ts, SCENARIOS_PATH, ASSIGN_PATH, PARTIC_PATH, COUNTS_SCEN
from typing import Optional, List, Tuple, Dict, Any

# if you still want this metadata in the assignment record:
SCENARIO_TO_CRITERION = {"s1":"recommendation","s2":"coverage","s3":"frequency","s4":"missing"}

N_TRIALS = 32                 # divisible by 4
ENTROPY_MIN_BITS = 2.5
ENTROPY_RETRY_LIMIT = 25

def get_assignment(pid: str) -> Tuple[Optional[str], Optional[List[str]], Optional[Dict[str, Any]]]:
    doc = rtdb.reference(f"{ASSIGN_PATH}/{pid}").get() or {}
    return (doc.get("scenario_id"), doc.get("trial_ids"), doc.get("comparison_trials"))

def create_participant_pid() -> str:
    ref = rtdb.reference(PARTIC_PATH).push({"created": server_ts()})
    return ref.key  # pid

def _choose_min_count(path: str, sids: List[str]) -> str:
    chosen = {"sid": None}
    ref = rtdb.reference(path)
    def txn(curr):
        curr = curr or {}
        for s in sids: curr.setdefault(s, 0)
        m = min(curr[s] for s in sids)
        pool = [s for s in sids if curr[s] == m]
        sid = random.choice(pool); curr[sid] += 1; chosen["sid"] = sid
        return curr
    ref.transaction(txn)
    return chosen["sid"]

# ---- order-invariant signature (a-b-c == c-b-a) ----
def _order_signature(ids: List[str]) -> str:
    return ",".join(sorted(map(str, ids)))

def _entropy(counts: dict) -> float:
    tot = sum(counts.values())
    if tot <= 0: return 0.0
    h = 0.0
    for c in counts.values():
        if c > 0:
            p = c / tot
            h -= p * math.log(p, 2)
    return h

def _try_register_order(sid: str, ids: List[str], hmin: float) -> bool:
    sig = _order_signature(ids)
    ok = {"v": False}
    def txn(curr):
        curr = curr or {}
        after = {k: int(v or 0) for k, v in curr.items()}
        after[sig] = after.get(sig, 0) + 1
        k = max(1, len(after))
        if hmin <= math.log(k, 2) and _entropy(after) < hmin:
            return None
        ok["v"] = True
        return after
    rtdb.reference(f"/orders/{sid}").transaction(txn)
    return ok["v"]

def assign_participant(pid: str, n_trials: int = N_TRIALS, entropy_min_bits: float = ENTROPY_MIN_BITS) -> Tuple[str, List[str]]:
    # sticky reuse
    doc = rtdb.reference(f"{ASSIGN_PATH}/{pid}").get() or {}
    if doc.get("scenario_id") and doc.get("trial_ids"):
        return doc["scenario_id"], doc["trial_ids"]

    sids = list((rtdb.reference(SCENARIOS_PATH).get() or {}).keys())
    sid = _choose_min_count(COUNTS_SCEN, sids)

    # read levels -> ids -> records
    buckets = rtdb.reference(f"/catalog/trials_by_scenario/{sid}").get() or {}  # {level: {id: {id, option}}}
    levels = list(buckets.keys())[:4]
    if n_trials % 4: raise ValueError("n_trials must be divisible by 4.")
    if len(levels) != 4: raise RuntimeError(f"Need 4 levels, found {len(levels)}.")
    per = n_trials // 4

    # pick balanced ids and build lookup for final write
    chosen, lookup = [], {}
    for lvl in levels:
        ids = list((buckets.get(lvl) or {}).keys())
        if len(ids) < per: raise RuntimeError(f"Not enough trials for level '{lvl}'.")
        random.shuffle(ids)
        pick = ids[:per]
        chosen.extend(pick)
        for tid in pick:
            rec = buckets[lvl][tid]
            lookup[str(tid)] = {"id": str(tid), "option": rec["option"]}

    # entropy-guard attempts (order-invariant)
    for _ in range(ENTROPY_RETRY_LIMIT):
        order = chosen[:]; random.shuffle(order)
        if _try_register_order(sid, order, entropy_min_bits):
            trials = [lookup[tid] for tid in order]
            rtdb.reference("/").update({
                f"{ASSIGN_PATH}/{pid}": {
                    "scenario_id": sid,
                    "trial_ids": order,
                    "trials": trials,
                    "assigned_ts": server_ts(),
                    # optional metadata if you still want it:
                    "targeted_criterion": SCENARIO_TO_CRITERION.get(sid),
                    "entropy_bits_threshold": entropy_min_bits,
                },
                f"{PARTIC_PATH}/{pid}/assigned": {"scenario_id": sid, "trial_ids": order, "ts": server_ts()},
            })
            return sid, order

    # fallback (still order-invariant for counting)
    random.shuffle(chosen)
    sig = _order_signature(chosen)
    orders_ref = rtdb.reference(f"/orders/{sid}")
    curr = orders_ref.get() or {}; curr[sig] = int(curr.get(sig, 0)) + 1; orders_ref.set(curr)
    trials = [lookup[tid] for tid in chosen]
    rtdb.reference("/").update({
        f"{ASSIGN_PATH}/{pid}": {
            "scenario_id": sid, "trial_ids": chosen, "trials": trials,
            "assigned_ts": server_ts(),
            "targeted_criterion": SCENARIO_TO_CRITERION.get(sid),
            "entropy_bits_threshold": entropy_min_bits,
            "entropy_guard": "fallback_used",
        },
        f"{PARTIC_PATH}/{pid}/assigned": {"scenario_id": sid, "trial_ids": chosen, "ts": server_ts()},
    })
    return sid, chosen

COUNTS_TASK_ORDER = "/metrics/task_order_counts"

TASK_ORDER_KEY = "task_order"
TASK_ORDERS = ["wtp_first", "llm_first"]

def ensure_task_order(pid: str) -> str:
    """Ensure a pid has a balanced task order (wtp_first / llm_first)."""
    existing = (rtdb.reference(f"{ASSIGN_PATH}/{pid}/{TASK_ORDER_KEY}").get() or "").strip()
    if existing in TASK_ORDERS:
        return existing

    # Balanced pick via RTDB transaction counter
    chosen = _choose_min_count(COUNTS_TASK_ORDER, TASK_ORDERS)

    # Persist in both assignments and participants for convenience
    rtdb.reference("/").update({
        f"{ASSIGN_PATH}/{pid}/{TASK_ORDER_KEY}": chosen,
        f"{PARTIC_PATH}/{pid}/{TASK_ORDER_KEY}": chosen,
        f"{PARTIC_PATH}/{pid}/task_order_assigned_ts": server_ts(),
    })
    return chosen