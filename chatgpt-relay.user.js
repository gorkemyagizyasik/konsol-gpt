// ==UserScript==
// @name         ChatGPT 8023 Web UI Relay
// @namespace    http://localhost:8023/
// @version      1.0
// @description  Connects ChatGPT web tab to local 8023 web UI to bypass 403 Sentinel PoW blocks
// @match        https://chatgpt.com/*
// @grant        GM_xmlhttpRequest
// @run-at       document-idle
// ==UserScript==

(function () {
  'use strict';

  const RELAY_SERVER = 'http://localhost:8023';
  let isRelaying = false;

  console.log('[ChatGPT 8023 Relay] Script loaded and listening for 8023 Web UI prompts...');

  // Poll for pending messages from local 8023 server
  async function pollRelay() {
    if (isRelaying) return;

    try {
      const res = await fetch(`${RELAY_SERVER}/api/relay/pending`, { method: 'GET' });
      if (!res.ok) return;

      const data = await res.json();
      if (data.status === 'ok' && data.task) {
        isRelaying = true;
        console.log('[ChatGPT 8023 Relay] Received prompt from Web UI:', data.task.prompt);
        await handleRelayTask(data.task);
        isRelaying = false;
      }
    } catch (e) {
      // Local server might be offline or idle
    }
  }

  // Ping heartbeat to local server
  async function sendHeartbeat() {
    try {
      await fetch(`${RELAY_SERVER}/api/relay/heartbeat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: true, url: window.location.href })
      });
    } catch (e) {}
  }

  // Send request natively inside browser tab context
  async function handleRelayTask(task) {
    const taskId = task.id;
    const prompt = task.prompt;
    const model = task.model || 'auto';
    const conversationId = task.conversation_id;
    const parentMessageId = task.parent_message_id || crypto.randomUUID();

    // 1. Prepare
    let conduitToken = null;
    try {
      const prepRes = await fetch('https://chatgpt.com/backend-api/f/conversation/prepare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'next',
          conversation_id: conversationId,
          parent_message_id: parentMessageId,
          model: model,
          client_prepare_state: 'none',
          client_prepare_dispatch: 'immediate',
          client_prepare_source: 'context_change',
          timezone_offset_min: -180,
          timezone: 'Europe/Istanbul',
          conversation_mode: { kind: 'primary_assistant' },
          system_hints: [],
          supports_buffering: true,
          supported_encodings: ['v1'],
          client_contextual_info: { app_name: 'chatgpt.com' }
        })
      });
      if (prepRes.ok) {
        const prepData = await prepRes.json();
        conduitToken = prepData.conduit_token;
      }
    } catch (e) {
      console.warn('[ChatGPT 8023 Relay] Prepare failed:', e);
    }

    // 2. Main Conversation Post
    const messageId = crypto.randomUUID();
    const payload = {
      action: 'next',
      messages: [
        {
          id: messageId,
          author: { role: 'user' },
          create_time: Date.now() / 1000,
          content: { content_type: 'text', parts: [prompt] },
          metadata: { serialization_metadata: { custom_symbol_offsets: [] }, submission_mode: 'manual_send' }
        }
      ],
      parent_message_id: parentMessageId,
      model: model,
      timezone_offset_min: -180,
      timezone: 'Europe/Istanbul',
      conversation_mode: { kind: 'primary_assistant' },
      enable_message_followups: true,
      supports_buffering: true,
      supported_encodings: ['v1'],
      client_contextual_info: {
        is_dark_mode: false,
        time_since_loaded: 200,
        page_height: window.innerHeight,
        page_width: window.innerWidth,
        pixel_ratio: 1,
        screen_height: window.screen.height,
        screen_width: window.screen.width,
        app_name: 'chatgpt.com',
        has_web_push_capabilities: true,
        web_push_notification_permission: 'default'
      },
      paragen_cot_summary_display_override: 'allow',
      force_parallel_switch: 'auto'
    };

    if (conversationId) payload.conversation_id = conversationId;

    const headers = {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream'
    };

    if (conduitToken) headers['x-conduit-token'] = conduitToken;

    try {
      const convRes = await fetch('https://chatgpt.com/backend-api/f/conversation', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(payload)
      });

      if (!convRes.ok) {
        const errText = await convRes.text();
        await pushChunk(taskId, { type: 'error', content: `HTTP ${convRes.status}: ${errText.slice(0, 200)}` });
        return;
      }

      // Stream response back to 8023 server
      const reader = convRes.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const rawData = line.slice(6).strip ? line.slice(6).strip() : line.slice(6).trim();
            await pushChunk(taskId, { type: 'raw', line: rawData });
          }
        }
      }

      await pushChunk(taskId, { type: 'done' });

    } catch (e) {
      await pushChunk(taskId, { type: 'error', content: `Browser Relay Error: ${e.message}` });
    }
  }

  async function pushChunk(taskId, chunkObj) {
    try {
      await fetch(`${RELAY_SERVER}/api/relay/chunk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId, chunk: chunkObj })
      });
    } catch (e) {}
  }

  // Poll loop
  setInterval(pollRelay, 1000);
  setInterval(sendHeartbeat, 3000);
  sendHeartbeat();
})();
