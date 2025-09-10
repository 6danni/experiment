# app/services/catalog.py
from firebase_admin import db as rtdb
from app.main.firebase import SCENARIOS_PATH, TRIALS_PATH
from itertools import product

LEVELS = {
    "recommendation": ["95", "90", "85", "80"],
    "frequency": ["Daily", "Weekly", "Monthly", "Quarterly"],
    "missing": ["5", "10", "15", "20"],
    "coverage": ["35", "30", "25", "20"],
}

SCENARIO_TO_CRITERION = {
    "s1": "recommendation",
    "s2": "coverage",
    "s3": "frequency",
    "s4": "missing",
}

CRIT_ORDER = ["recommendation", "frequency", "missing", "coverage"]


def list_scenarios() -> dict:
    data = rtdb.reference(SCENARIOS_PATH).get() or {}
    if not isinstance(data, dict) or not data:
        raise RuntimeError("No scenarios available.")
    return data  # {sid: {...}}

def list_trials() -> dict:
    data = rtdb.reference(TRIALS_PATH).get() or {}
    if not isinstance(data, dict) or not data:
        raise RuntimeError("No trials available.")
    return data  # {tid: {...}}

def build_catalog():
    trials = rtdb.reference(f"/catalog/trials").get() 
    if trials is None: 
        trials = {}
        i = 0
        for combo in product(*(LEVELS[c] for c in CRIT_ORDER)):
            tid = f"{i:03d}"
            trials[tid] = {"id": tid, "option": {c: str(v) for c, v in zip(CRIT_ORDER, combo)}}
            i += 1
    rtdb.reference(f"{TRIALS_PATH}").set(trials)


def build_catalog_for_sid(sid: str): 
    trials = rtdb.reference(f"/catalog/trials").get() 
    if trials is None: 
        build_catalog() 
    target = SCENARIO_TO_CRITERION[sid] 
    trials_by_sid = {lvl: {} for lvl in LEVELS[target]}
   
    for idx, trial in trials.items(): 
        chosen_level = trial.get("option").get(target)
        trials_by_sid[chosen_level][trial["id"]] = {"id": trial["id"], "option": trial["option"]}
    
    rtdb.reference(f"catalog/trials_by_scenario/{sid}").set(trials_by_sid)