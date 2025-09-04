# routes.py (same blueprint as your experiment pages)
from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from firebase_admin import db as rtdb
from app.main.assignments import get_assignment, assign_participant
from app.main.firebase import SCENARIOS_PATH, server_ts

# bp = Blueprint("main", __name__)

AGE_GROUPS = {"18-24", "25-34", "35-44", "45-54", "55-64", "65+"}
GENDERS = {"Female", "Male", "Non-binary", "Prefer not to say", "Self-describe"}
DATA_FREQUENCY = {
    "Never",
    "Rarely",
    "Every few months",
    "Monthly",
    "Weekly",
    "Multiple times per week",
}

def validate_demo(payload: dict) -> tuple[dict, dict]:
    """Return (clean_payload, errors). Does NOT write to DB."""
    errors = {}
    pid = (payload.get("pid") or "").strip()
    age_group = payload.get("age_group")
    gender = payload.get("gender")
    gender_text = (payload.get("gender_text") or "").strip()
    data_frequency = payload.get("data_frequency")
    years_raw = payload.get("years_with_data")

    if age_group not in AGE_GROUPS:
        errors["age_group"] = "Please select a valid age group."

    if gender not in GENDERS:
        errors["gender"] = "Please select a valid gender option."
    elif gender == "Self-describe" and not gender_text:
        errors["gender_text"] = "Please provide a short self-description."

    if data_frequency not in DATA_FREQUENCY:
        errors["data_frequency"] = "Please select a valid frequency."

    years_with_data = None
    try:
        years_with_data = float(years_raw)
        if not (0.0 <= years_with_data <= 60.0):
            errors["years_with_data"] = "Enter years between 0 and 60."
    except (TypeError, ValueError):
        errors["years_with_data"] = "Enter years as a number (e.g., 0, 1, 2.5)."

    clean = {
        "pid": pid or None,
        "age_group": age_group,
        "gender": gender if gender != "Self-describe" else gender_text,
        "gender_raw": gender,
        "gender_text": gender_text if gender == "Self-describe" else "",
        "data_frequency": data_frequency,
        "years_with_data": years_with_data,
        "submitted_at": server_ts(),  # server timestamp
    }
    return clean, errors
