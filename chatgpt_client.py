import json
import os
import uuid
import time
import base64
import hashlib
import subprocess
from curl_cffi import requests as cffi_requests

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "cookie": "",
    "auth_token": "",
    "oai_device_id": "336af599-fdc2-4e6f-8a57-e30dcbc29bfa",
    "model": "auto",
    "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    "timezone": "Europe/Istanbul",
    "timezone_offset_min": -180
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = DEFAULT_CONFIG.copy()
                merged.update(data)
                return merged
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(config_data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)

class ChatGPTClient:
    def __init__(self):
        self.config = load_config()
        if not self.config.get("oai_device_id"):
            self.config["oai_device_id"] = str(uuid.uuid4())
            save_config(self.config)
        self.cached_access_token = None
        self.token_fetch_time = 0

    def update_settings(self, cookie=None, auth_token=None, model=None, device_id=None):
        if cookie is not None:
            self.config["cookie"] = cookie.strip()
            self.cached_access_token = None
        if auth_token is not None:
            self.config["auth_token"] = auth_token.strip()
            if auth_token.strip():
                self.cached_access_token = auth_token.strip()
        if model is not None:
            self.config["model"] = model.strip()
        if device_id is not None:
            self.config["oai_device_id"] = device_id.strip()
        save_config(self.config)

    def refresh_access_token(self):
        """Fetches/renews accessToken from https://chatgpt.com/api/auth/session using Cookie."""
        cookie = self.config.get("cookie", "").strip()
        if not cookie:
            return self.config.get("auth_token", "").strip()

        url = "https://chatgpt.com/api/auth/session"
        headers = self.get_headers(skip_auth=True)

        try:
            res = cffi_requests.get(url, headers=headers, impersonate="chrome120", timeout=12)
            if res.status_code == 200:
                data = res.json()
                token = data.get("accessToken")
                if token:
                    self.cached_access_token = token
                    self.token_fetch_time = time.time()
                    return token
        except Exception:
            pass

        return self.config.get("auth_token", "").strip()

    def get_access_token(self):
        if self.cached_access_token and (time.time() - self.token_fetch_time < 1800):
            return self.cached_access_token
        return self.refresh_access_token()

    def get_headers(self, additional_headers=None, skip_auth=False, user_agent=None):
        ua = user_agent or self.config.get("user_agent", DEFAULT_CONFIG["user_agent"])
        is_mobile = "?1" if ("Mobile" in ua or "iPhone" in ua or "Android" in ua) else "?0"
        headers = {
            "User-Agent": ua,
            "oai-device-id": self.config.get("oai_device_id", DEFAULT_CONFIG["oai_device_id"]),
            "oai-client-build-number": "10577136",
            "oai-client-version": "prod-8bfe9e3526fbf9900f9332d46fef7bc0065c4478",
            "oai-session-id": str(uuid.uuid4()),
            "oai-language": "tr-TR",
            "accept-language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "origin": "https://chatgpt.com",
            "referer": "https://chatgpt.com/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-ch-ua-mobile": is_mobile
        }

        cookie = self.config.get("cookie", "").strip()
        if cookie:
            headers["Cookie"] = cookie

        if not skip_auth:
            token = self.get_access_token()
            if token:
                if not token.lower().startswith("bearer "):
                    token = f"Bearer {token}"
                headers["Authorization"] = token

        if additional_headers:
            headers.update(additional_headers)

        return headers

    def solve_turnstile_via_node_vm(self, prep_data, raw_dx):
        try:
            runner_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sentinel_runner.js")
            cmd = ["node", runner_script, json.dumps(prep_data), raw_dx]
            out = subprocess.check_output(cmd, timeout=8).decode("utf-8").strip()
            data = json.loads(out)
            if data.get("status") == "ok" and data.get("solved"):
                return data.get("solved")
        except Exception:
            pass
        return raw_dx

    def get_sentinel_tokens(self, flow="conversation", parent_message_id=None, pow_token=None):
        url_prepare = "https://chatgpt.com/backend-api/sentinel/chat-requirements/prepare"
        device_id = self.config.get("oai_device_id")
        if not device_id or device_id == "336af599-fdc2-4e6f-8a57-e30dcbc29bfa":
            device_id = str(uuid.uuid4())
            self.config["oai_device_id"] = device_id
            save_config(self.config)

        headers = self.get_headers({"content-type": "application/json", "accept": "*/*"})

        try:
            res = cffi_requests.post(url_prepare, headers=headers, json={"id": device_id, "flow": flow}, impersonate="chrome120", timeout=10)
            if res.status_code == 200:
                data = res.json()
                prep_token = data.get("prepare_token")
                turnstile_raw_dx = data.get("turnstile", {}).get("dx") or ""
                if prep_token:
                    solved_turnstile_token = self.solve_turnstile_via_node_vm(data, turnstile_raw_dx)
                    if not pow_token:
                        pow_token = self.generate_sentinel_proof_token(seed_uuid=parent_message_id or str(uuid.uuid4()))
                    url_fin = "https://chatgpt.com/backend-api/sentinel/chat-requirements/finalize"
                    res2 = cffi_requests.post(
                        url_fin,
                        headers=headers,
                        json={
                            "prepare_token": prep_token,
                            "proofofwork": pow_token,
                            "turnstile": solved_turnstile_token
                        },
                        impersonate="chrome120",
                        timeout=10
                    )
                    if res2.status_code == 200:
                        data2 = res2.json()
                        return {
                            "token": data2.get("token"),
                            "proof_token": pow_token,
                            "turnstile_token": solved_turnstile_token
                        }
        except Exception as e:
            pass
        return {}

    def list_conversations(self, offset=0, limit=28):
        url = f"https://chatgpt.com/backend-api/conversations?offset={offset}&limit={limit}&order=updated&is_archived=false&is_starred=false"
        headers = self.get_headers({"accept": "*/*"})
        res = cffi_requests.get(url, headers=headers, impersonate="chrome120", timeout=12)
        
        # Retry with refreshed token on 401
        if res.status_code == 401:
            self.refresh_access_token()
            headers = self.get_headers({"accept": "*/*"})
            res = cffi_requests.get(url, headers=headers, impersonate="chrome120", timeout=12)

        if res.status_code == 200:
            return res.json()
        elif res.status_code in [401, 403]:
            raise Exception("Authentication error (401/403). Please check your Cookie or Session Auth Token in Settings.")
        else:
            raise Exception(f"Failed to fetch conversations (Status Code: {res.status_code})")

    def get_conversation_history(self, conversation_id):
        url = f"https://chatgpt.com/backend-api/conversation/{conversation_id}"
        headers = self.get_headers({"accept": "*/*"})
        res = cffi_requests.get(url, headers=headers, impersonate="chrome120", timeout=12)
        
        if res.status_code == 401:
            self.refresh_access_token()
            headers = self.get_headers({"accept": "*/*"})
            res = cffi_requests.get(url, headers=headers, impersonate="chrome120", timeout=12)

        if res.status_code == 200:
            return res.json()
        else:
            raise Exception(f"Failed to fetch conversation history (Status Code: {res.status_code})")

    def get_conduit_token(self, parent_message_id, conversation_id=None, model="auto"):
        """Fetches short-lived conduit JWT token required by ChatGPT backend-api."""
        url = "https://chatgpt.com/backend-api/f/conversation/prepare"
        headers = self.get_headers({"content-type": "application/json", "accept": "*/*"})
        payload = {
            "action": "next",
            "parent_message_id": parent_message_id,
            "model": model,
            "client_prepare_state": "none",
            "client_prepare_dispatch": "immediate",
            "client_prepare_source": "context_change",
            "timezone_offset_min": self.config.get("timezone_offset_min", -180),
            "timezone": self.config.get("timezone", "Europe/Istanbul"),
            "conversation_mode": {"kind": "primary_assistant"},
            "system_hints": [],
            "supports_buffering": True,
            "supported_encodings": ["v1"],
            "client_contextual_info": {"app_name": "chatgpt.com"}
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id

        try:
            res = cffi_requests.post(url, headers=headers, json=payload, impersonate="chrome120", timeout=10)
            if res.status_code == 200:
                data = res.json()
                return data.get("conduit_token")
        except Exception:
            pass
        return None

    def generate_sentinel_proof_token(self, seed_uuid=None, difficulty=3000, user_agent=None):
        """Generates dynamic Proof-of-Work (PoW) token required by OpenAI Sentinel."""
        if not seed_uuid:
            seed_uuid = str(uuid.uuid4())
        
        if isinstance(difficulty, str):
            try:
                difficulty = int(difficulty, 16) if difficulty.startswith("0x") else int(difficulty)
            except Exception:
                difficulty = 3000

        ua = user_agent or self.config.get("user_agent", DEFAULT_CONFIG["user_agent"])
        time_str = time.strftime("%a %b %d %Y %H:%M:%S GMT+0300 (Türkiye Standart Saati)")
        epoch_ms = round(time.time() * 1000, 1)

        payload = [
            difficulty,
            time_str,
            4395630592,
            0,
            ua,
            "https://chatgpt.com/sentinel/20260810913b/sdk.js",
            "prod-8bfe9e3526fbf9900f9332d46fef7bc0065c4478",
            "tr-TR",
            "tr-TR,tr,en-US,en",
            6,
            "deprecatedRunAdAuctionEnforcesKAnonymity\u2212false",
            "location",
            "scroll",
            148620.30000000447,
            seed_uuid,
            "",
            4,
            epoch_ms,
            0, 0, 0, 0, 0, 0, 0
        ]

        target = 0xFFFFF // (difficulty // 1000 + 1)
        nonce = 0
        while nonce < 500000:
            payload[3] = nonce
            json_str = json.dumps(payload, separators=(',', ':'))
            hash_digest = hashlib.sha256(json_str.encode('utf-8')).hexdigest()
            if int(hash_digest[:5], 16) <= target:
                b64_payload = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
                return f"gAAAAAB{b64_payload}~S"
            nonce += 1

        json_str = json.dumps(payload, separators=(',', ':'))
        b64_payload = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
        return f"gAAAAAB{b64_payload}~S"

    def send_message_stream(self, prompt, conversation_id=None, parent_message_id=None, model=None, proof_token=None, user_agent=None):
        model = model or self.config.get("model", "auto")
        message_id = str(uuid.uuid4())
        if not parent_message_id:
            parent_message_id = str(uuid.uuid4())

        self.get_access_token()
        proof_token = proof_token or self.generate_sentinel_proof_token(seed_uuid=parent_message_id, user_agent=user_agent)
        conduit_token = self.get_conduit_token(parent_message_id, conversation_id=conversation_id, model=model)
        sentinel_data = self.get_sentinel_tokens(flow="conversation", parent_message_id=parent_message_id, pow_token=proof_token)

        sentinel_token = sentinel_data.get("token")
        turnstile_token = sentinel_data.get("turnstile_token")

        headers = self.get_headers({
            "content-type": "application/json",
            "accept": "text/event-stream",
            "x-openai-target-path": "/backend-api/f/conversation",
            "x-openai-target-route": "/backend-api/f/conversation",
            "x-oai-turn-trace-id": str(uuid.uuid4()),
            "x-oai-is-pending-updates": '{"v":3,"updates":[]}'
        }, user_agent=user_agent)

        if sentinel_token:
            headers["openai-sentinel-chat-requirements-token"] = sentinel_token
        if conduit_token:
            headers["x-conduit-token"] = conduit_token
        if proof_token:
            headers["openai-sentinel-proof-token"] = proof_token
        if turnstile_token:
            headers["openai-sentinel-turnstile-token"] = turnstile_token

        payload = {
            "action": "next",
            "messages": [
                {
                    "id": message_id,
                    "author": {"role": "user"},
                    "create_time": time.time(),
                    "content": {
                        "content_type": "text",
                        "parts": [prompt]
                    },
                    "metadata": {
                        "serialization_metadata": {"custom_symbol_offsets": []},
                        "submission_mode": "manual_send"
                    }
                }
            ],
            "parent_message_id": parent_message_id,
            "model": model,
            "client_prepare_state": "success",
            "timezone_offset_min": self.config.get("timezone_offset_min", -180),
            "timezone": self.config.get("timezone", "Europe/Istanbul"),
            "conversation_mode": {"kind": "primary_assistant"},
            "enable_message_followups": True,
            "supports_buffering": True,
            "supported_encodings": ["v1"],
            "client_contextual_info": {
                "is_dark_mode": False,
                "time_since_loaded": 200,
                "page_height": 897,
                "page_width": 1174,
                "pixel_ratio": 1,
                "screen_height": 1080,
                "screen_width": 1920,
                "app_name": "chatgpt.com",
                "has_web_push_capabilities": True,
                "web_push_notification_permission": "default"
            },
            "paragen_cot_summary_display_override": "allow",
            "force_parallel_switch": "auto"
        }

        if conversation_id:
            payload["conversation_id"] = conversation_id

        url = "https://chatgpt.com/backend-api/f/conversation"

        try:
            response = cffi_requests.post(url, headers=headers, json=payload, stream=True, impersonate="chrome120", timeout=60)
        except Exception as e:
            yield {"type": "error", "content": f"Network error: {str(e)}"}
            return

        if response.status_code in [401, 403]:
            yield {"type": "error", "content": f"Authentication failed ({response.status_code}). Please check your Cookie string in settings."}
            return
        elif response.status_code != 200:
            yield {"type": "error", "content": f"ChatGPT API returned HTTP error {response.status_code}: {response.text[:300]}"}
            return

        accumulated_text = ""
        current_conv_id = conversation_id
        last_message_id = None

        for line in response.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8") if isinstance(line, bytes) else line
            if line_str.startswith("data: "):
                data_str = line_str[6:].strip()
                if data_str == "[DONE]":
                    break

                try:
                    obj = json.loads(data_str)
                    if not isinstance(obj, dict):
                        continue
                    
                    if "conversation_id" in obj and obj["conversation_id"]:
                        current_conv_id = obj["conversation_id"]

                    if "v" in obj and isinstance(obj["v"], list):
                        for patch in obj["v"]:
                            if isinstance(patch, dict):
                                op = patch.get("o")
                                path = patch.get("p", "")
                                val = patch.get("v")

                                if path == "/message/content/parts/0" and op in ["append", "replace"] and isinstance(val, str):
                                    clean_chunk = val.replace("\ue200cite", "").replace("\ue202", "").replace("\ue201", "")
                                    accumulated_text += clean_chunk
                                    yield {
                                        "type": "text",
                                        "content": clean_chunk,
                                        "full_text": accumulated_text,
                                        "conversation_id": current_conv_id
                                    }

                    elif "message" in obj and isinstance(obj["message"], dict):
                        msg = obj["message"]
                        if "id" in msg:
                            last_message_id = msg["id"]
                        content = msg.get("content", {})
                        parts = content.get("parts", [])
                        if parts and isinstance(parts[0], str):
                            full_msg = parts[0]
                            full_msg = full_msg.replace("\ue200cite", "").replace("\ue202", "").replace("\ue201", "")
                            diff = full_msg[len(accumulated_text):]
                            if diff:
                                accumulated_text = full_msg
                                yield {
                                    "type": "text",
                                    "content": diff,
                                    "full_text": accumulated_text,
                                    "conversation_id": current_conv_id,
                                    "message_id": last_message_id
                                }

                except json.JSONDecodeError:
                    continue

        yield {
            "type": "done",
            "full_text": accumulated_text,
            "conversation_id": current_conv_id,
            "message_id": last_message_id
        }
