from datetime import datetime
from flask import render_template, flash, redirect, url_for, request, g, \
    jsonify, current_app, send_from_directory
import os
import random
import itertools
import re
import math
import csv
from config import Config
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db as rtdb
from app.main.demographics import validate_demo
# from app import db
# from app.models import User, Post
from app.main import bp
# from pair import _ensure_comparison_trials, _trial_at
from app.main.firebase import (
    server_ts, SCENARIOS_PATH, TRIALS_PATH,
    ASSIGN_PATH, PARTIC_PATH
)
from app.main.catalog import list_scenarios, list_trials, build_catalog_for_sid
from app.main.assignments2 import create_participant_pid, assign_participant, get_assignment, ensure_task_order
from app.main.metrics import choose_and_increment_one
from app.main.comparison import ensure_comparison_trials


NUM = 32
# @bp.route('/<string:page_name>')
# def static_page(page_name):
#     print('GET: ' + '%s.html' % ('/experiment/' + page_name))
#     return render_template('%s.html' % ('/experiment/' + page_name))

@bp.before_app_request
def _stash_pid_from_query():
    pid = request.args.get("pid")
    if pid:
        g.pid = pid

def url_for_pid(endpoint, **values):
    if "pid" not in values and getattr(g, "pid", None):
        values["pid"] = g.pid
    return url_for(endpoint, **values)

bp.add_app_template_global(url_for_pid, name="url_for_pid")

@bp.app_context_processor
def _inject_pid():
    return {"pid": getattr(g, "pid", None)}

@bp.route('/', methods=['GET', 'POST'])
def root():
    return redirect("/0_landing")

@bp.route('/test')
def test():
    return 'Server is running'

@bp.get("/api/catalog/scenarios")
def api_scenarios():
    data = rtdb.reference("/catalog/scenarios").get() or {}
    items = [{"id": k, **v} if isinstance(v, dict) else {"id": k, "value": v}
             for k, v in (data.items() if isinstance(data, dict) else [])]
    return jsonify(items), 200

# SCENARIOS_PATH = "/catalog/scenarios"
# TRIALS_PATH    = "/catalog/trials"
COUNTS_SCEN    = "/metrics/scenario_counts"
COUNTS_TRIAL   = "/metrics/trial_counts"
# ASSIGN_PATH    = "/assignments"

    
@bp.get("/0_landing")
def page_0_landing():
    return render_template(
        "experiment/0_landing.html",
    )


@bp.get("/1_scenario")
def page_1_scenario():
    pid = request.args.get("pid")
    if not pid:
        # First visit → create pid, assign scenario+trials, then canonicalize URL
        pid = create_participant_pid()
        scenario_id, trial_ids = assign_participant(pid, n_trials=NUM)
        return redirect(url_for("main.page_1_scenario", pid=pid), code=302)

    # Has pid → use existing assignment or assign now if missing
    scenario_id, trial_ids, comparison_trials = get_assignment(pid)
    if not scenario_id or not trial_ids:
        scenario_id, trial_ids, comparison_trials = assign_participant(pid, n_trials=30)
    task_order = ensure_task_order(pid)
    # Load scenario object for display
    scenario = rtdb.reference(f"{SCENARIOS_PATH}/{scenario_id}").get() or {}
    trials = rtdb.reference(f"/catalog/trials_by_scenario/{scenario_id}").get() 
    if trials is None: 
        build_catalog_for_sid(scenario_id) 

    return render_template(
        "experiment/1_scenario.html",
        pid=pid,
        scenario_id=scenario_id,
        scenario=scenario,
        trial_ids=trial_ids,
        total_trials=len(trial_ids),
        first_task=task_order,
        # trials=selected_trials, 
    )

@bp.get("/start_first_task")
def start_first_task():
    pid = request.args.get("pid")
    if not pid:
        return redirect(url_for("main.page_1_scenario"), code=302)

    scenario_id, trial_ids, comparison_trials = get_assignment(pid)
    if not scenario_id:
        scenario_id, trial_ids, comparison_trials = assign_participant(pid, n_trials=NUM)

    order = ensure_task_order(pid)

    if order == "wtp_first":
        return redirect(url_for("main.page_2_WTP_task", pid=pid), code=302)
    else:
        return redirect(url_for("main.page_3_LLM_task", pid=pid), code=302)

@bp.get("/2_WTP_task")
def page_2_WTP_task():
    # print("yes here")
    pid = request.args.get("pid")
    if not pid:
        return redirect(url_for("main.page_1_scenario"), code=302)

    scenario_id, trial_ids, comparison_trials = get_assignment(pid)
    if not scenario_id:
        scenario_id, trial_ids, comparison_trials = assign_participant(pid, n_trials=NUM)
    # ensure_comparison_trials(pid, scenario_id)
    
    scenario = rtdb.reference(f"{SCENARIOS_PATH}/{scenario_id}").get() or {}
    
    return render_template(
        "experiment/2_WTP_task.html",
        pid=pid,
        scenario_id=scenario_id,
        scenario=scenario,
        trial_ids=trial_ids,
        total_trials=len(trial_ids),
    )

@bp.get("/2_WTP_task_trial")
def page_2_WTP_task_trial():
    pid = request.args.get("pid")
    if not pid:
        return redirect(url_for("main.page_1_scenario"), code=302)

    scenario_id, trial_ids, comparison_trials = get_assignment(pid)
    if not scenario_id or not trial_ids:
        scenario_id, trial_ids, comparison_trials = assign_participant(pid, n_trials=32)

    scenario = rtdb.reference(f"{SCENARIOS_PATH}/{scenario_id}").get() or {}
    total = len(trial_ids)

    last = rtdb.reference(f"{PARTIC_PATH}/{pid}/scenarios/{scenario_id}/last_trial").get() or 0
    current_idx = int(last) + 1  # 1-based

    if current_idx > total:
        return redirect(url_for("main.page_2_WTP_task", pid=pid), code=302)

    # Pull ordered trials with levels from assignment (if available)
    assign_doc = rtdb.reference(f"{ASSIGN_PATH}/{pid}").get() or {}
    trials_with_levels = assign_doc.get("trials") or []

    # Determine current trial id
    current_tid = trial_ids[current_idx - 1]

    # Prefer levels saved in assignment (keeps UI stable even if catalog moves)
    trial = {}
    if isinstance(trials_with_levels, list) and len(trials_with_levels) >= current_idx:
        entry = trials_with_levels[current_idx - 1] or {}
        trial = entry.get("option", {}) or {}
        # sanity: if the id at this position mismatches, fall back to scenario node
        if str(entry.get("id")) != str(current_tid):
            trial = {}

    if not trial:
        node = rtdb.reference(f"{SCENARIOS_PATH}/{scenario_id}/trials/{current_tid}").get() or {}
        trial = node.get("option", node)  # flatten if OA stored under "option"
    task_order = ensure_task_order(pid)
    return render_template(
        "experiment/2_WTP_task_trial.html",
        pid=pid,
        scenario_id=scenario_id,
        scenario=scenario,
        trial_id=current_tid,
        trial_index=current_idx,
        total_trials=total,
        trial=trial,
        task_order=task_order, 
    )

# @bp.get("/2_WTP_task_trial")
# def page_2_WTP_task_trial():
#     pid = request.args.get("pid")
#     if not pid:
#         # No pid? Send them to scenario page to mint pid/assignment.
#         return redirect(url_for("main.page_1_scenario"), code=302)

#     scenario_id, trial_ids = get_assignment(pid)
#     if not scenario_id or not trial_ids:
#         # Edge case: somehow no assignment yet
#         scenario_id, trial_ids = assign_participant(pid, n_trials=30)

#     scenario = rtdb.reference(f"{SCENARIOS_PATH}/{scenario_id}").get() or {}
#     total = len(trial_ids)

#     # Progress: either 'last_trial' or derive from responses count
#     last = rtdb.reference(f"{PARTIC_PATH}/{pid}/scenarios/{scenario_id}/last_trial").get() or 0
#     current_idx = int(last) + 1  # 1-based

#     if current_idx > total:
#         # All trials complete → go to the next page
#         return redirect(url_for("main.page_2_WTP_task", pid=pid), code=302)

#     # Load current trial object (e.g., catalog/trials/t015)
#     current_tid = trial_ids[current_idx - 1]
#     trial_obj = rtdb.reference(f"{TRIALS_PATH}/{current_tid}").get() or {}

#     return render_template("experiment/2_WTP_task_trial.html",
#                            pid=pid,
#                            scenario_id=scenario_id,
#                            scenario=scenario,
#                            trial_id=current_tid,
#                            trial_index=current_idx,
#                            total_trials=total,
#                            trial=trial_obj)


@bp.post("/api/trials")
def save_trial():
    body = request.get_json(silent=True) or {}
    pid         = body.get("pid")
    scenario_id = body.get("scenario_id")
    trial_idx   = body.get("trial")        # 1-based index
    bid         = body.get("bid")

    if not pid or not scenario_id or not trial_idx or bid is None:
        return jsonify(error="BadRequest", detail="pid, scenario_id, trial, bid required"), 400

    base = f"{PARTIC_PATH}/{pid}/scenarios/{scenario_id}"
    rtdb.reference(f"{base}/trials/{int(trial_idx)}").update({
        "bid": float(bid),
        "ts": server_ts()
    })

    rtdb.reference(f"{base}/last_trial").set(int(trial_idx))

    return jsonify(ok=True), 200


@bp.get("/3_LLM_task")
def page_3_LLM_task():
    pid = request.args.get("pid")
    if not pid:
        # No pid? Send them to /1_scenario to mint and assign.
        return redirect(url_for("main.page_1_scenario"), code=302)

    scenario_id, trial_ids, comparison_trials = get_assignment(pid)
    if not scenario_id:
        # Edge case: pid exists but no assignment yet
        scenario_id, trial_ids, comparison_trials = assign_participant(pid, n_trials=NUM)

    scenario = rtdb.reference(f"{SCENARIOS_PATH}/{scenario_id}").get() or {}
    
    return render_template(
        "experiment/3_LLM_task.html",
        pid=pid,
        scenario_id=scenario_id,
        scenario=scenario,
        trial_ids=trial_ids,
        total_trials=len(trial_ids),
    )


@bp.get("/3_LLM_task_chat")
def page_3_LLM_task_chat():
    pid = request.args.get("pid")
    if not pid:
        return redirect(url_for("main.page_1_scenario"), code=302)

    scenario_id, trial_ids, comparison_trials = get_assignment(pid)
    if not scenario_id:
        scenario_id, trial_ids, comparison_trials = assign_participant(pid, n_trials=NUM)

    scenario = rtdb.reference(f"{SCENARIOS_PATH}/{scenario_id}").get() or {}
    task_order = ensure_task_order(pid)
    return render_template(
        "experiment/3_LLM_task_chat.html",
        pid=pid,
        scenario_id=scenario_id,
        scenario=scenario,
        trial_ids=trial_ids,
        total_trials=len(trial_ids),
        task_order=task_order,
    )


@bp.get("/4_comparison")
def page_4_comparison():
    pid = request.args.get("pid")
    if not pid:
        return redirect(url_for("main.page_1_scenario"), code=302)

    scenario_id, trial_ids, comparison_trials = get_assignment(pid)
    if not scenario_id:
        scenario_id, trial_ids, comparison_trials = assign_participant(pid, n_trials=NUM)

    scenario = rtdb.reference(f"{SCENARIOS_PATH}/{scenario_id}").get() or {}
    
    return render_template(
        "experiment/4_comparison.html",
        pid=pid,
        scenario_id=scenario_id,
        scenario=scenario,
        trial_ids=trial_ids,
        total_trials=len(trial_ids),
    )


@bp.get("/4_comparison_trial")
def page_4_comparison_trial():
    pid = request.args.get("pid")
    if not pid:
        return redirect(url_for("main.page_1_scenario"), code=302)

    scenario_id, trial_ids, comparison_trials = get_assignment(pid)
    if not scenario_id or not trial_ids:
        scenario_id, trial_ids, comparison_trials = assign_participant(pid, n_trials=NUM)

    # Seed comparison trials once, under /assignments/{pid}/comparison_trials
    ensure_comparison_trials(pid, scenario_id)

    base_assign = f"{ASSIGN_PATH}/{pid}"
    last = rtdb.reference(f"{base_assign}/last_comparison_trial").get() or 0
    #trial_index = int(last)+1
    trial_index = int(last) + 1
    trials_node = rtdb.reference(f"{base_assign}/comparison_trials").get() or {}
    total = 16
    if trial_index > total:
        # All done → go to the summary/next page
        return redirect(url_for("main.page_0_landing", pid=pid), code=302)

    scenario = rtdb.reference(f"{SCENARIOS_PATH}/{scenario_id}").get() or {}
    prior_decision = None
    if last >= 1:
        prior_decision = rtdb.reference(f"{base_assign}/decisions/{last}").get()

    return render_template(
        "experiment/4_comparison_trial.html",
        pid=pid,
        scenario_id=scenario_id,
        scenario=scenario,
        trial=trials_node[trial_index],
        trial_index=trial_index,
        total_trials=total,
        prior_decision=prior_decision,
    )

@bp.post("/api/prefs")
def save_pref():
    body = request.get_json(silent=True) or {}
    pid         = (body.get("pid") or "").strip()
    scenario_id = (body.get("scenario_id") or "").strip()
    trial_idx   = body.get("trial")
    choice      = (body.get("choice") or "").strip()
    a_features  = body.get("option_a") or {}
    b_features  = body.get("option_b") or {}
    if not pid or not trial_idx or choice not in {"A", "B"}:
        return jsonify(error="BadRequest", detail="pid, trial, and choice (A/B) required"), 400

    base_assign = f"{ASSIGN_PATH}/{pid}"
    chosen = a_features if choice == "A" else b_features
    
    # Pull out common fields for quick querying
    chosen_rec   = chosen.get("recommendation") or chosen.get("recommended_by")
    chosen_freq  = chosen.get("frequency")
    chosen_miss  = chosen.get("missing") or chosen.get("missing_rate")
    chosen_cov   = chosen.get("coverage")

    rtdb.reference(f"{base_assign}/comparison_trials/{int(trial_idx)}").update({
        "scenario_id": scenario_id or None,
        "choice": choice,
        "option_a": a_features,     
        "option_b": b_features,
        "chosen": chosen,
        "chosen_recommendation": chosen_rec,
        "chosen_frequency": chosen_freq,
        "chosen_missing": chosen_miss,
        "chosen_coverage": chosen_cov,
        "answered_ts": server_ts(),
    })

    rtdb.reference(f"{base_assign}/last_comparison_trial").set(int(trial_idx))
    return jsonify(ok=True), 200


@bp.route("/5_demographics", methods=["GET", "POST"])
def page_5_demographics():
    if request.method == "POST":
        # Accept JSON (from fetch) or form-encoded (from a normal form POST)
        data = request.get_json(silent=True) or request.form.to_dict(flat=True)
        clean, errors = validate_demo(data)
        if errors:
            return jsonify({"ok": False, "errors": errors}), 400

        pid = clean["pid"]
        # If PID present, write under that participant; else push under /demographics
        if pid:
            rtdb.reference(f"/demographics/{pid}").set(clean)
            key = pid
        else:
            key = rtdb.reference("/demographics").push(clean).key

        return jsonify({"ok": True, "id": key})

    # GET → render page
    pid = request.args.get("pid")
    if not pid:
        return redirect(url_for("main.page_1_scenario"), code=302)

    scenario_id, trial_ids, comparison_trials = get_assignment(pid)
    if not scenario_id:
        scenario_id, trial_ids, comparison_trials = assign_participant(pid, n_trials=NUM)

    scenario = rtdb.reference(f"{SCENARIOS_PATH}/{scenario_id}").get() or {}

    # IMPORTANT: do NOT call any save function here; just render the page.
    return render_template(
        "experiment/5_demographics.html",
        pid=pid,
        scenario_id=scenario_id,
        scenario=scenario,
        trial_ids=trial_ids,
        total_trials=len(trial_ids),
    )