import asyncio
import json
import time
import uuid
import sys
import os

sys.path.append("/home/gorkem/.local/lib/python3.11/site-packages")
from playwright.async_api import async_playwright
from chatgpt_client import load_config

class HeadlessChatGPTBridge:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.is_ready = False
        self._lock = asyncio.Lock()

    async def start(self):
        async with self._lock:
            if self.is_ready and self.page:
                return

            config = load_config()
            cookie_str = config.get("cookie", "")
            user_agent = config.get("user_agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")

            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox"
                ]
            )
            self.context = await self.browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1280, "height": 800}
            )

            # Mask webdriver detection
            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['tr-TR', 'tr', 'en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            """)

            # Add cookies using url
            cookies_list = []
            if cookie_str:
                for pair in cookie_str.split(";"):
                    if "=" in pair:
                        k, v = pair.strip().split("=", 1)
                        name = k.strip()
                        val = v.strip()
                        if name:
                            cookies_list.append({
                                "name": name,
                                "value": val,
                                "url": "https://chatgpt.com"
                            })
                try:
                    await self.context.add_cookies(cookies_list)
                except Exception as e:
                    print("⚠️ Cookie parsing warning:", e)

            self.page = await self.context.new_page()
            print("🚀 [Headless Bridge] Navigating to https://chatgpt.com/ in background with stealth...")
            try:
                await self.page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(5)
                # Check for Cloudflare Turnstile iframe
                cf_frame = self.page.frame(url=lambda u: "challenges.cloudflare.com" in u)
                if cf_frame:
                    print("⚠️ Cloudflare Turnstile detected, attempting click...")
                    try:
                        await cf_frame.click("input[type='checkbox']", timeout=3000)
                    except Exception:
                        pass
                    await asyncio.sleep(5)
            except Exception as e:
                print("⚠️ [Headless Bridge] Initial page load warning:", e)

            self.is_ready = True
            print("✅ [Headless Bridge] Ready to process ChatGPT prompts silently!")

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.is_ready = False

    async def send_chat_message(self, prompt, conversation_id=None, parent_message_id=None, model="auto"):
        if not self.is_ready or not self.page:
            await self.start()

        parent_msg_id = parent_message_id or str(uuid.uuid4())

        js_fetch_script = r"""
        (async ([prompt, convId, parentMsgId, modelName]) => {
            let sentinelToken = null;
            try {
                const sPrep = await fetch("https://chatgpt.com/backend-api/sentinel/chat-requirements/prepare", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" }
                });
                if (sPrep.ok) {
                    const sPrepData = await sPrep.json();
                    if (sPrepData.prepare_token) {
                        const sFin = await fetch("https://chatgpt.com/backend-api/sentinel/chat-requirements/finalize", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ prepare_token: sPrepData.prepare_token })
                        });
                        if (sFin.ok) {
                            const sFinData = await sFin.json();
                            sentinelToken = sFinData.token;
                        }
                    }
                }
            } catch(e) {}

            let conduitToken = null;
            try {
                const prepRes = await fetch("https://chatgpt.com/backend-api/f/conversation/prepare", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        action: "next",
                        conversation_id: convId || undefined,
                        parent_message_id: parentMsgId,
                        model: modelName || "auto",
                        client_prepare_state: "none",
                        client_prepare_dispatch: "immediate",
                        client_prepare_source: "context_change",
                        timezone_offset_min: -180,
                        timezone: "Europe/Istanbul",
                        conversation_mode: { kind: "primary_assistant" },
                        system_hints: [],
                        supports_buffering: true,
                        supported_encodings: ["v1"],
                        client_contextual_info: { app_name: "chatgpt.com" }
                    })
                });
                if (prepRes.ok) {
                    const prepData = await prepRes.json();
                    conduitToken = prepData.conduit_token;
                }
            } catch(e) {}

            const headers = {
                "Content-Type": "application/json",
                "Accept": "text/event-stream"
            };
            if (sentinelToken) headers["openai-sentinel-chat-requirements-token"] = sentinelToken;
            if (conduitToken) headers["x-conduit-token"] = conduitToken;

            const payload = {
                action: "next",
                messages: [{
                    id: crypto.randomUUID(),
                    author: { role: "user" },
                    create_time: Date.now() / 1000,
                    content: { content_type: "text", parts: [prompt] },
                    metadata: { serialization_metadata: { custom_symbol_offsets: [] }, submission_mode: "manual_send" }
                }],
                parent_message_id: parentMsgId,
                model: modelName || "auto",
                timezone_offset_min: -180,
                timezone: "Europe/Istanbul",
                conversation_mode: { kind: "primary_assistant" },
                enable_message_followups: true,
                supports_buffering: true,
                supported_encodings: ["v1"],
                client_contextual_info: {
                    is_dark_mode: false,
                    time_since_loaded: 200,
                    page_height: 897,
                    page_width: 1174,
                    pixel_ratio: 1,
                    screen_height: 1080,
                    screen_width: 1920,
                    app_name: "chatgpt.com",
                    has_web_push_capabilities: true,
                    web_push_notification_permission: "default"
                },
                paragen_cot_summary_display_override: "allow",
                force_parallel_switch: "auto"
            };

            if (convId) payload.conversation_id = convId;

            const res = await fetch("https://chatgpt.com/backend-api/f/conversation", {
                method: "POST",
                headers: headers,
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                return { status: res.status, text: await res.text() };
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let fullText = "";
            let returnedConvId = convId;

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                const chunkStr = decoder.decode(value, { stream: true });
                const lines = chunkStr.split("\n");
                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        const d = line.slice(6).trim();
                        if (d === "[DONE]") break;
                        try {
                            const obj = JSON.parse(d);
                            if (obj.conversation_id) returnedConvId = obj.conversation_id;
                            if (obj.v && Array.isArray(obj.v)) {
                                for (const p of obj.v) {
                                    if (p.p === "/message/content/parts/0" && typeof p.v === "string") {
                                        fullText += p.v;
                                    }
                                }
                            } else if (obj.message && obj.message.content && obj.message.content.parts) {
                                const p0 = obj.message.content.parts[0];
                                if (typeof p0 === "string" && p0.length > fullText.length) {
                                    fullText = p0;
                                }
                            }
                        } catch(e) {}
                    }
                }
            }
            return { status: 200, fullText: fullText, conversation_id: returnedConvId };
        })
        """

        try:
            res = await self.page.evaluate(js_fetch_script, [prompt, conversation_id, parent_msg_id, model])
            return res
        except Exception as e:
            self.is_ready = False
            return {"status": 500, "text": str(e)}
