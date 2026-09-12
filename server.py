#!/usr/bin/env python3
import os
import json
import uuid
import time
import asyncio
import threading
from flask import Flask, request, Response, jsonify, send_from_directory, stream_with_context
from chatgpt_client import ChatGPTClient
from headless_bridge import HeadlessChatGPTBridge

app = Flask(__name__, static_folder="public", static_url_path="")
client = ChatGPTClient()
headless_bridge = HeadlessChatGPTBridge()

# Asyncio loop thread for Headless Bridge
loop = asyncio.new_event_loop()

def run_async_loop(l):
    asyncio.set_event_loop(l)
    l.run_forever()

loop_thread = threading.Thread(target=run_async_loop, args=(loop,), daemon=True)
loop_thread.start()

# Initialize Headless Bridge in background thread
asyncio.run_coroutine_threadsafe(headless_bridge.start(), loop)

@app.route("/")
def index():
    return send_from_directory("public", "index.html")

@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory("public", filename)

@app.route("/api/settings", methods=["GET"])
def get_settings():
    cfg = client.config
    masked_cookie = (cfg.get("cookie", "")[:20] + "...") if len(cfg.get("cookie", "")) > 20 else cfg.get("cookie", "")
    masked_token = (cfg.get("auth_token", "")[:20] + "...") if len(cfg.get("auth_token", "")) > 20 else cfg.get("auth_token", "")

    return jsonify({
        "status": "ok",
        "has_cookie": bool(cfg.get("cookie", "").strip()),
        "has_auth_token": bool(cfg.get("auth_token", "").strip()),
        "masked_cookie": masked_cookie,
        "masked_auth_token": masked_token,
        "model": cfg.get("model", "auto"),
        "device_id": cfg.get("oai_device_id", ""),
        "headless_ready": headless_bridge.is_ready
    })

@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.get_json() or {}
    cookie = data.get("cookie")
    auth_token = data.get("auth_token")
    model = data.get("model")
    device_id = data.get("device_id")

    client.update_settings(cookie=cookie, auth_token=auth_token, model=model, device_id=device_id)

    # Re-initialize Headless Bridge with new cookies if updated
    if cookie:
        asyncio.run_coroutine_threadsafe(headless_bridge.start(), loop)

    return jsonify({"status": "ok", "message": "Settings updated successfully"})

@app.route("/api/conversations", methods=["GET"])
def list_conversations():
    try:
        offset = request.args.get("offset", 0, type=int)
        limit = request.args.get("limit", 28, type=int)
        data = client.list_conversations(offset=offset, limit=limit)
        return jsonify({"status": "ok", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route("/api/conversation/<id>", methods=["GET"])
def get_conversation(id):
    try:
        data = client.get_conversation_history(id)
        return jsonify({"status": "ok", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

import queue

# Relay State
relay_last_heartbeat = 0
pending_tasks = queue.Queue()
task_responses = {}

@app.route("/api/relay/heartbeat", methods=["POST"])
def relay_heartbeat():
    global relay_last_heartbeat
    relay_last_heartbeat = time.time()
    return jsonify({"status": "ok"})

@app.route("/api/relay/pending", methods=["GET"])
def relay_pending():
    try:
        task = pending_tasks.get_nowait()
        return jsonify({"status": "ok", "task": task})
    except queue.Empty:
        return jsonify({"status": "idle"})

@app.route("/api/relay/chunk", methods=["POST"])
def relay_chunk():
    data = request.get_json() or {}
    task_id = data.get("task_id")
    chunk = data.get("chunk")
    if task_id in task_responses:
        task_responses[task_id].put(chunk)
    return jsonify({"status": "ok"})

# --- CHAT ENDPOINT USING USERSCRIPT RELAY / HEADLESS / DIRECT CLIENT ---
@app.route("/api/chat", methods=["POST"])
def chat_stream():
    data = request.get_json() or {}
    prompt = data.get("prompt", "").strip()
    conversation_id = data.get("conversation_id")
    parent_message_id = data.get("parent_message_id")
    model = data.get("model") or client.config.get("model", "auto")
    client_proof_token = data.get("client_proof_token")

    if not prompt:
        return jsonify({"status": "error", "message": "Prompt is required"}), 400

    def generate_chat():
        # Priority 1: Userscript Browser Relay (if tab is open & heartbeat active)
        if time.time() - relay_last_heartbeat < 10:
            task_id = str(uuid.uuid4())
            task_queue = queue.Queue()
            task_responses[task_id] = task_queue

            task = {
                "id": task_id,
                "prompt": prompt,
                "conversation_id": conversation_id,
                "parent_message_id": parent_message_id,
                "model": model
            }
            pending_tasks.put(task)

            accumulated_text = ""
            current_conv_id = conversation_id

            while True:
                try:
                    chunk = task_queue.get(timeout=45)
                    ctype = chunk.get("type")

                    if ctype == "done":
                        yield f"data: {json.dumps({'type': 'done', 'full_text': accumulated_text, 'conversation_id': current_conv_id})}\n\n"
                        break
                    elif ctype == "error":
                        yield f"data: {json.dumps({'type': 'error', 'content': chunk.get('content', 'Relay Error')})}\n\n"
                        break
                    elif ctype == "raw":
                        line = chunk.get("line", "")
                        if line == "[DONE]":
                            yield f"data: {json.dumps({'type': 'done', 'full_text': accumulated_text, 'conversation_id': current_conv_id})}\n\n"
                            break
                        try:
                            obj = json.loads(line)
                            if not isinstance(obj, dict):
                                continue
                            if obj.get("conversation_id"):
                                current_conv_id = obj.get("conversation_id")
                            if "v" in obj and isinstance(obj["v"], list):
                                for patch in obj["v"]:
                                    if patch.get("p") == "/message/content/parts/0" and isinstance(patch.get("v"), str):
                                        accumulated_text += patch["v"]
                                        yield f"data: {json.dumps({'type': 'text', 'content': patch['v'], 'full_text': accumulated_text, 'conversation_id': current_conv_id})}\n\n"
                            elif "message" in obj and isinstance(obj["message"], dict):
                                parts = obj["message"].get("content", {}).get("parts", [])
                                if parts and isinstance(parts[0], str):
                                    diff = parts[0][len(accumulated_text):]
                                    if diff:
                                        accumulated_text = parts[0]
                                        yield f"data: {json.dumps({'type': 'text', 'content': diff, 'full_text': accumulated_text, 'conversation_id': current_conv_id})}\n\n"
                        except Exception:
                            pass
                except queue.Empty:
                    yield f"data: {json.dumps({'type': 'error', 'content': 'Browser Relay timeout (no chunk received)'})}\n\n"
                    break

            task_responses.pop(task_id, None)
            yield "data: [DONE]\n\n"
            return

        # Priority 2: Headless Playwright Bridge
        use_headless = headless_bridge.is_ready
        headless_success = False

        if use_headless:
            future = asyncio.run_coroutine_threadsafe(
                headless_bridge.send_chat_message(
                    prompt=prompt,
                    conversation_id=conversation_id,
                    parent_message_id=parent_message_id,
                    model=model
                ),
                loop
            )

            try:
                res = future.result(timeout=40)
                status = res.get("status")
                if status == 200:
                    full_text = res.get("fullText", "")
                    conv_id = res.get("conversation_id", conversation_id)
                    yield f"data: {json.dumps({'type': 'text', 'content': full_text, 'full_text': full_text, 'conversation_id': conv_id})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'full_text': full_text, 'conversation_id': conv_id})}\n\n"
                    headless_success = True
            except Exception:
                headless_success = False

        # Priority 3: Direct HTTP client fallback
        if not headless_success:
            for chunk in client.send_message_stream(
                prompt=prompt,
                conversation_id=conversation_id,
                parent_message_id=parent_message_id,
                model=model,
                proof_token=client_proof_token
            ):
                yield f"data: {json.dumps(chunk)}\n\n"

        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate_chat()), content_type="text/event-stream")

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8023))
    print(f"🚀 ChatGPT Custom Web Interface starting on http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=True)
