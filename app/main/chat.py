from flask import request, jsonify
from openai import OpenAI
from app.main import bp
from app.main.firebase import ref, server_ts, ASSIGN_PATH
from config import Config
from typing import List, Dict, Any, Optional

def _messages_path(pid: str) -> str:
    return f"{ASSIGN_PATH}/{pid}/messages"

@bp.post("/api/llm/send")
def llm_send():
    body = request.get_json(silent=True) or {}
    pid         = (body.get("pid") or "").strip()
    scenario_id = (body.get("scenario_id") or "").strip()
    user_text   = (body.get("input") or "").strip()
    if not pid or not user_text:
        return jsonify(error="BadRequest", detail="pid and input required"), 400

    base = _messages_path(pid)

    # 1) store user msg
    ref(base).push({
        "role": "user",
        "content": user_text,
        **({"scenario_id": scenario_id} if scenario_id else {}),
        "ts": server_ts(),
    })

    try:
        # Reads OPENAI_API_KEY from env; no config.py needed
        client = OpenAI(
            api_key=Config.OPENAI_API_KEY
        )

        # 2) call your saved Prompt (version 2). Add "inputs" only if your prompt has variables.
        resp = client.responses.create(
            prompt={
                "id": "pmpt_68a792c45f448190bf767ed4133e253f0aedd092065c9099",
                "version": "11",
            },input = user_text
            # If your Prompt does NOT specify a default model, you may need:
            # , model="gpt-4.1-mini"
        )

        reply_text = getattr(resp, "output_text", "") or ""
        usage = getattr(resp, "usage", None)
        if hasattr(usage, "model_dump"):
            usage = usage.model_dump()

    except Exception as e:
        ref(base).push({
            "role": "system",
            "content": f"LLM error: {type(e).__name__}",
            **({"scenario_id": scenario_id} if scenario_id else {}),
            "ts": server_ts(),
        })
        return jsonify(error=type(e).__name__, detail=str(e)), 500

    # 3) store assistant msg
    msg_ref = ref(base).push({
        "role": "assistant",
        "content": reply_text,
        "response_id": getattr(resp, "id", None),
        "usage": usage,
        **({"scenario_id": scenario_id} if scenario_id else {}),
        "ts": server_ts(),
    })

    return jsonify(text=reply_text, id=msg_ref.key), 200

def _fetch_messages(pid: str, scenario_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    snap = (
        ref(_messages_path(pid))
        .order_by_key()             
        .limit_to_last(limit)
        .get()
        or {}
    )
    # print(snap)
    items = list(snap.values())
    # print(items)
    if scenario_id:
        items = [m for m in items if m.get("scenario_id") == scenario_id]
    items.sort(key=lambda m: (m.get("ts") or 0))
    return items

def _render_transcript(messages: List[Dict[str, Any]], max_chars: int = 12000) -> str:
    lines = []
    for m in messages:
        role = m.get("role", "user")
        prefix = "User" if role == "user" else ("Assistant" if role == "assistant" else role.title())
        content = (m.get("content") or "").strip()
        if content:
            lines.append(f"{prefix}: {content}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[-max_chars:]
        cut = text.find("\n")
        text = text[cut+1:] if cut != -1 else text
    return text

def _last_response_id(messages: List[Dict[str, Any]]) -> Optional[str]:
    for m in reversed(messages):
        if m.get("role") == "assistant" and m.get("response_id"):
            return m["response_id"]
    return None


@bp.post("/api/llm/analyze_final")
def analyze_final():
    body = request.get_json(silent=True) or {}
    pid         = (body.get("pid") or "").strip()
    scenario_id = (body.get("scenario_id") or "").strip() or None

    if not pid:
        return jsonify(error="BadRequest", detail="pid required"), 400

    # 1) Fetch ALL messages for this pid (and scenario if provided)
    msgs = _fetch_messages(pid, scenario_id=scenario_id, limit=2000)
    transcript = _render_transcript(msgs)
    client = OpenAI(api_key=Config.OPENAI_API_KEY)
    resp = client.responses.create(
        prompt={
            "id": "pmpt_68c2d5fdb3448190bb4d52f2e05bb04800e286e5ad67df0c",
            "version": "1",
            # "variables": {
            #     "trials": transcript,
            #     ""
            # }
        },
        input = transcript
        
    )
    text = getattr(resp, "output_text", "") or ""
    print(text)
    # usage = getattr(resp, "usage", None)
    

    result_node = {
        "scenario_id": scenario_id,
        "result_text": text,
        "response_id": getattr(resp, "id", None),
        # "usage": usage,
        "ts": server_ts(),
    }

    ref(f"{ASSIGN_PATH}/{pid}/chat_analysis").push(result_node)
    return jsonify(result_node), 200

@bp.post("/api/llm/analyze_wtp")
def analyze_wtp():
    body = request.get_json(silent=True) or {}
    pid         = (body.get("pid") or "").strip()
    scenario_id = (body.get("scenario_id") or "").strip() or None
    assign_doc  = rtdb.reference(f"{ASSIGN_PATH}/{pid}").get() or {}
    trial_ids   = [str(t) for t in (assign_doc.get("trial_ids") or [])]
    if not pid:
        return jsonify(error="BadRequest", detail="pid required"), 400
    wtp_map = rtdb.reference(f"{PARTIC_PATH}/{pid}/scenarios/{sid}/trials").get() or {}

    records = []
    for i, tid in enumerate(trial_ids, start=1):
        bid = (wtp_map.get(str(i)) or {}).get("bid")
        if bid is None:
            continue
        node = rtdb.reference(f"/catalog/trials/{tid}").get() or {}
        option = node.get("option", node) or {}
        records.append({"index": i, "trial_id": tid, "bid": float(bid), "option": option})
    print(records)
    if not records:
        return jsonify(error="NoData", detail="no completed WTP trials"), 400

    # 1) Fetch ALL messages for this pid (and scenario if provided)
    msgs = _fetch_messages(pid, scenario_id=scenario_id, limit=2000)
    transcript = _render_transcript(msgs)
    client = OpenAI(api_key=Config.OPENAI_API_KEY)
    resp = client.responses.create(
        prompt={
            "id": "pmpt_68c246f0ac4c8197b49415db98fa9c700321f99fda2f516f",
            "version": "2",
            "variables": {
                "trials_json": json.dumps(records, ensure_ascii=False)
            }
        },
        input = transcript
        
    )
    text = getattr(resp, "output_text", "") or ""
    print(text)
    
    

    result_node = {
        "scenario_id": scenario_id,
        "result_text": text,
        "response_id": getattr(resp, "id", None),
        # "usage": usage,
        "ts": server_ts(),
    }

    ref(f"{ASSIGN_PATH}/{pid}/chat_wtp").push(result_node)
    return jsonify(result_node), 200

# @bp.post("/api/llm/run_action_continue")
# def llm_run_action_continue():
#     body = request.get_json(silent=True) or {}
#     pid         = (body.get("pid") or "").strip()
#     scenario_id = (body.get("scenario_id") or "").strip() or None
#     prompt_id   = (body.get("prompt_id") or "").strip()
#     version     = (body.get("version") or "").strip() or None
#     user_input  = (body.get("input") or "Please perform the action.").strip()

#     if not pid or not prompt_id:
#         return jsonify(error="BadRequest", detail="pid and prompt_id required"), 400

#     try:
#         msgs = _fetch_messages(pid, scenario_id=scenario_id, limit=200)
#         prev_id = _last_response_id(msgs)

#         client = OpenAI(api_key=Config.OPENAI_API_KEY)
#         payload = {"id": prompt_id}
#         if version:
#             payload["version"] = version

#         kwargs = dict(prompt=payload, input=user_input)
#         if prev_id:
#             kwargs["previous_response_id"] = prev_id

#         resp = client.responses.create(**kwargs)
#         reply_text = getattr(resp, "output_text", "") or ""
#         usage = getattr(resp, "usage", None)
#         if hasattr(usage, "model_dump"):
#             usage = usage.model_dump()

#         msg_ref = ref(_messages_path(pid)).push({
#             "role": "assistant",
#             "content": reply_text,
#             "response_id": getattr(resp, "id", None),
#             "usage": usage,
#             "scenario_id": scenario_id or None,
#             "ts": server_ts(),
#             "meta": {"action_prompt_id": prompt_id, "action_kind": "continue"},
#         })
#         return jsonify(text=reply_text, id=msg_ref.key), 200

#     except Exception as e:
#         ref(_messages_path(pid)).push({
#             "role": "system",
#             "content": f"LLM action error: {type(e).__name__}",
#             "scenario_id": scenario_id or None,
#             "ts": server_ts(),
#         })
#         return jsonify(error=type(e).__name__, detail=str(e)), 500