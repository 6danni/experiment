# app/firebase.py
from firebase_admin import db as rtdb

# RTDB paths in one place
SCENARIOS_PATH = "/catalog/scenarios"
TRIALS_PATH    = "/catalog/trials"
COUNTS_SCEN    = "/metrics/scenario_counts"
COUNTS_TRIAL   = "/metrics/trial_counts"
ASSIGN_PATH    = "/assignments"
PARTIC_PATH    = "/results"

def server_ts():
    """Realtime Database server timestamp sentinel."""
    return {".sv": "timestamp"}

def ref(path: str):
    """Convenience wrapper: rtdb.reference(path)."""
    return rtdb.reference(path)
