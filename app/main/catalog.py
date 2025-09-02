# app/services/catalog.py
from firebase_admin import db as rtdb
from app.main.firebase import SCENARIOS_PATH, TRIALS_PATH

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
