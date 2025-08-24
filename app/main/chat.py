# routes.py (or llm.py)
from flask import request, jsonify
from openai import OpenAI
from app.main import bp
from .firebase import ref, server_ts, ASSIGN_PATH
from config import Config

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
                "version": "4",
                # "inputs": {"user_input": user_text, "pid": pid, "scenario_id": scenario_id}
            }
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
