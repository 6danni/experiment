# helpers (put in services or routes file)
import random
from app.main.firebase import ref, server_ts, PARTIC_PATH, TRIALS_PATH, SCENARIOS_PATH, ASSIGN_PATH
from firebase_admin import db as rtdb

# ---- Comparison trial generator (stored under /assignments/{pid}/comparison_trails)
RECOMMENDATIONS = ["65", "75", "85", "95"]
FREQUENCIES     = ["Daily", "Weekly", "Monthly", "Quarterly"]
MISSING_RATES   = ["5", "10", "15", "20"]
COVERAGES       = ["20", "25", "30", "35"]
COMP_ATTR_COUNTS = "/metrics/comparison_attr_counts_by_scenario"

def _ensure_comparison_trials(pid: str, scenario_id: str, n: int = 20) -> None:
    """
    Seeds A/B comparison trials once per participant into:
      /assignments/{pid}/comparison_trials
    For scenario "1", we cycle 'recommendation' across 4 values; others are pseudo-random.
    """
    base = f"{ASSIGN_PATH}/{pid}/comparison_trials"
    existing = rtdb.reference(base).get()
    if existing:
        return

    def _rand_dataset(force_rec: str | None = None) -> dict:
        return {
            "recommendation": force_rec if force_rec else random.choice(RECOMMENDATIONS),
            "frequency":      random.choice(FREQUENCIES),
            "missing":        random.choice(MISSING_RATES),
            "coverage":       random.choice(COVERAGES),
        }

    trials = {}
    for i in range(n):
        if str(scenario_id) in {"1", "s1", "scenario_1"}:
            rec = RECOMMENDATIONS[i % len(RECOMMENDATIONS)]
        else:
            rec = random.choice(RECOMMENDATIONS)

        option_a = _rand_dataset(force_rec=rec)  # A gets cycled recommendation
        option_b = _rand_dataset()                # B fully random

        trials[str(i + 1)] = {
            "scenario_id": scenario_id,          # keep for auditing
            "option_a": option_a,
            "option_b": option_b,
            "ts": server_ts(),
        }

    # Write all trials and initialize progress under /assignments/{pid}
    rtdb.reference(base).update(trials)
    rtdb.reference(f"{ASSIGN_PATH}/{pid}/last_comparison_trial").set(0)


def _trial_at(trials_node, trial_index: int):
    """
    Return (trial_dict, total_count) for given 1-based trial_index,
    whether trials_node is a list or a dict with '1','2',...
    """
    # print(trials_node)
    # print(type(trials_node))
    print(trial_index)
    
    if isinstance(trials_node, list):
        total = len(trials_node)
        idx0 = trial_index - 1
        # print(trials_node[idx0])
        return ((trials_node[idx0] or {}) if 0 <= idx0 < total else {}), total

    return {}, 0
