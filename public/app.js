document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const sidebar = document.getElementById('sidebar');
  const btnToggleSidebar = document.getElementById('btn-toggle-sidebar');
  const btnNewChat = document.getElementById('btn-new-chat');
  const searchThreads = document.getElementById('search-threads');
  const historyList = document.getElementById('history-list');
  const authStatusCard = document.getElementById('auth-status-card');
  const authIndicator = document.getElementById('auth-indicator');
  const authStatusText = document.getElementById('auth-status-text');
  const btnOpenSettings = document.getElementById('btn-open-settings');
  const activeThreadTitle = document.getElementById('active-thread-title');
  const activeThreadId = document.getElementById('active-thread-id');
  const selectModel = document.getElementById('select-model');
  const messagesContainer = document.getElementById('messages-container');
  const welcomeScreen = document.getElementById('welcome-screen');
  const chatForm = document.getElementById('chat-form');
  const userInput = document.getElementById('user-input');
  const btnSend = document.getElementById('btn-send');

  // Dialog Elements
  const settingsDialog = document.getElementById('settings-dialog');
  const btnCloseSettings = document.getElementById('btn-close-settings');
  const btnSaveSettings = document.getElementById('btn-save-settings');
  const settingCookie = document.getElementById('setting-cookie');
  const settingToken = document.getElementById('setting-token');
  const settingDeviceId = document.getElementById('setting-device-id');

  // Application State
  let currentConversationId = null;
  let currentParentMessageId = null;
  let allConversations = [];
  let isGenerating = false;

  // Initialize Marked.js
  if (window.marked) {
    marked.setOptions({
      highlight: function(code, lang) {
        if (window.hljs && hljs.getLanguage(lang)) {
          return hljs.highlight(code, { language: lang }).value;
        }
        return code;
      },
      breaks: true
    });
  }

  // --- Initial Operations ---
  fetchSettings();
  fetchConversations();

  // --- Sidebar Toggle ---
  btnToggleSidebar.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
  });

  // --- New Chat Button ---
  btnNewChat.addEventListener('click', () => {
    startNewChat();
  });

  function startNewChat() {
    currentConversationId = null;
    currentParentMessageId = null;
    activeThreadTitle.textContent = "Yeni Sohbet";
    activeThreadId.textContent = "Oturum başlatılmadı";
    messagesContainer.innerHTML = '';
    messagesContainer.appendChild(welcomeScreen);
    welcomeScreen.style.display = 'block';

    // Remove active class from history items
    document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
  }

  // --- Settings Dialog ---
  btnOpenSettings.addEventListener('click', () => {
    fetchSettings();
    if (settingsDialog.showModal) {
      settingsDialog.showModal();
    } else {
      settingsDialog.setAttribute('open', 'true');
    }
  });

  btnCloseSettings.addEventListener('click', () => {
    if (settingsDialog.close) {
      settingsDialog.close();
    } else {
      settingsDialog.removeAttribute('open');
    }
  });

  btnSaveSettings.addEventListener('click', async () => {
    const cookie = settingCookie.value.trim();
    const auth_token = settingToken.value.trim();
    const device_id = settingDeviceId.value.trim();

    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cookie, auth_token, device_id })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        alert('Ayarlar başarıyla kaydedildi!');
        if (settingsDialog.close) settingsDialog.close();
        fetchSettings();
        fetchConversations();
      } else {
        alert('Hata: ' + data.message);
      }
    } catch (e) {
      alert('Ayarlar kaydedilirken sunucu hatası oluştu.');
    }
  });

  // --- Fetch Settings from Backend ---
  async function fetchSettings() {
    try {
      const res = await fetch('/api/settings');
      const data = await res.json();
      if (data.status === 'ok') {
        const hasAuth = data.has_cookie || data.has_auth_token;
        if (hasAuth) {
          authIndicator.classList.add('active');
          authStatusText.textContent = "Auth Kayıtlı (" + (data.has_cookie ? "Cookie" : "Token") + ")";
        } else {
          authIndicator.classList.remove('active');
          authStatusText.textContent = "Auth Eksik (Ayarlardan Girin)";
        }
        if (data.model) {
          selectModel.value = data.model;
        }
        settingCookie.value = data.masked_cookie ? data.masked_cookie : "";
        settingToken.value = data.masked_auth_token ? data.masked_auth_token : "";
        settingDeviceId.value = data.device_id || "";
      }
    } catch (e) {
      authStatusText.textContent = "Sunucu bağlantı hatası";
    }
  }

  // --- Fetch Conversations List ---
  async function fetchConversations() {
    try {
      const res = await fetch('/api/conversations');
      const json = await res.json();
      if (json.status === 'ok') {
        allConversations = json.data.items || [];
        renderConversationsList(allConversations);
      } else {
        historyList.innerHTML = `<li class="history-loading" style="color:#ef4444;">${json.message}</li>`;
      }
    } catch (e) {
      historyList.innerHTML = '<li class="history-loading" style="color:#ef4444;">Sohbetler yüklenemedi</li>';
    }
  }

  function renderConversationsList(items) {
    if (!items || items.length === 0) {
      historyList.innerHTML = '<li class="history-loading">Geçmiş sohbet yok</li>';
      return;
    }

    historyList.innerHTML = '';
    items.forEach(item => {
      const li = document.createElement('li');
      li.className = 'history-item' + (item.id === currentConversationId ? ' active' : '');
      li.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
        <span>${escapeHtml(item.title || 'İsimsiz Sohbet')}</span>
      `;
      li.addEventListener('click', () => loadConversation(item.id, item.title));
      historyList.appendChild(li);
    });
  }

  // --- Load Conversation History ---
  async function loadConversation(id, title) {
    currentConversationId = id;
    activeThreadTitle.textContent = title || "Sohbet";
    activeThreadId.textContent = "ID: " + id;
    welcomeScreen.style.display = 'none';
    messagesContainer.innerHTML = '<div style="text-align:center; padding: 40px; color:#9ca3af;">Sohbet geçmişi yükleniyor...</div>';

    renderConversationsList(allConversations);

    try {
      const res = await fetch(`/api/conversation/${id}`);
      const json = await res.json();
      if (json.status === 'ok') {
        renderConversationMessages(json.data);
      } else {
        messagesContainer.innerHTML = `<div style="color:#ef4444; padding:20px;">Hata: ${json.message}</div>`;
      }
    } catch (e) {
      messagesContainer.innerHTML = `<div style="color:#ef4444; padding:20px;">Sohbet yüklenirken hata oluştu.</div>`;
    }
  }

  function renderConversationMessages(data) {
    messagesContainer.innerHTML = '';
    const mapping = data.mapping || {};
    const currentNode = data.current_node;

    // Traverse tree back to root
    const nodes = [];
    let curr = currentNode;
    while (curr && mapping[curr]) {
      nodes.unshift(mapping[curr]);
      curr = mapping[curr].parent;
    }

    let renderedCount = 0;
    nodes.forEach(node => {
      const msg = node.message;
      if (!msg) return;
      const role = msg.author ? msg.author.role : null;
      if (role !== 'user' && role !== 'assistant') return;

      const contentParts = msg.content ? msg.content.parts : [];
      if (!contentParts || contentParts.length === 0) return;

      const text = typeof contentParts[0] === 'string' ? contentParts[0] : JSON.stringify(contentParts[0]);
      if (!text.trim()) return;

      appendMessageRow(role, text);
      renderedCount++;

      if (role === 'assistant') {
        currentParentMessageId = msg.id;
      }
    });

    if (renderedCount === 0) {
      messagesContainer.appendChild(welcomeScreen);
      welcomeScreen.style.display = 'block';
    }

    scrollToBottom();
  }

  // --- Auto Resize Textarea ---
  userInput.addEventListener('input', () => {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 150) + 'px';
  });

  userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      chatForm.dispatchEvent(new Event('submit'));
    }
  });

  // Global helper for click cards
  window.setInputPrompt = function(promptText) {
    userInput.value = promptText;
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 150) + 'px';
    userInput.focus();
  };

  function safeBtoa(str) {
    try {
      return btoa(encodeURIComponent(str).replace(/%([0-9A-F]{2})/g, (match, p1) => String.fromCharCode('0x' + p1)));
    } catch(e) {
      return btoa(str);
    }
  }

  // --- Client-Side Sentinel Proof-of-Work Generator ---
  async function generateSentinelProofToken(seedUuid, difficulty = 3000) {
    if (!seedUuid) seedUuid = crypto.randomUUID();
    const timeStr = new Date().toUTCString();
    const epochMs = Date.now();

    const payload = [
      difficulty,
      timeStr,
      4395630592,
      0,
      navigator.userAgent,
      "https://chatgpt.com/sentinel/20260810913b/sdk.js",
      "prod-8bfe9e3526fbf9900f9332d46fef7bc0065c4478",
      navigator.language || "tr-TR",
      (navigator.languages || ["tr-TR", "tr", "en-US", "en"]).join(","),
      navigator.hardwareConcurrency || 6,
      "deprecatedRunAdAuctionEnforcesKAnonymity−false",
      "location",
      "scroll",
      "148:20.30000000447",
      seedUuid,
      "",
      4,
      epochMs,
      0, 0, 0, 0, 0, 0, 0
    ];

    const encoder = new TextEncoder();
    let nonce = 0;
    
    try {
      while (nonce < 150) {
        payload[3] = nonce;
        const jsonStr = JSON.stringify(payload);
        const data = encoder.encode(jsonStr);
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');

        if (hashHex.startsWith('000') || (parseInt(hashHex.slice(0, 5), 16) < (0xFFFFF / (Math.floor(difficulty / 1000) + 1)))) {
          const b64Payload = safeBtoa(jsonStr);
          return `gAAAAAB${b64Payload}~S`;
        }
        nonce++;
      }
    } catch(e) {}

    const jsonStr = JSON.stringify(payload);
    return `gAAAAAB${safeBtoa(jsonStr)}~S`;
  }

  // --- Send Chat Message Stream ---
  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const prompt = userInput.value.trim();
    if (!prompt || isGenerating) return;

    // Hide welcome screen
    welcomeScreen.style.display = 'none';

    // Append User Message Row
    appendMessageRow('user', prompt);

    // Reset input
    userInput.value = '';
    userInput.style.height = 'auto';
    scrollToBottom();

    // Prepare Assistant Message Row
    const assistantBubble = appendMessageRow('assistant', '<i>Düşünüyor...</i>');
    isGenerating = true;
    btnSend.disabled = true;

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: prompt,
          conversation_id: currentConversationId,
          parent_message_id: currentParentMessageId,
          model: selectModel.value
        })
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let fullText = '';
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep last incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6).trim();
            if (dataStr === '[DONE]') break;

            try {
              const obj = JSON.parse(dataStr);
              if (obj.type === 'error') {
                assistantBubble.innerHTML = `<span style="color:#ef4444;">Hata: ${escapeHtml(obj.content)}</span>`;
                break;
              } else if (obj.type === 'text') {
                fullText = obj.full_text;
                if (obj.conversation_id) {
                  currentConversationId = obj.conversation_id;
                  activeThreadId.textContent = "ID: " + currentConversationId;
                }
                if (obj.message_id) {
                  currentParentMessageId = obj.message_id;
                }
                renderMarkdown(assistantBubble, fullText);
                scrollToBottom();
              } else if (obj.type === 'done') {
                if (obj.conversation_id) currentConversationId = obj.conversation_id;
                if (obj.message_id) currentParentMessageId = obj.message_id;
                fetchConversations();
              }
            } catch (err) {
              // ignore parse errors
            }
          }
        }
      }

    } catch (e) {
      assistantBubble.innerHTML = `<span style="color:#ef4444;">Sunucu isteği başarısız oldu: ${escapeHtml(e.message || 'Bağlantı hatası')}</span>`;
    } finally {
      isGenerating = false;
      btnSend.disabled = false;
    }
  });

  function appendMessageRow(role, content) {
    const row = document.createElement('div');
    row.className = `message-row ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = role === 'user' ? 'S' : 'AI';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    if (role === 'user') {
      bubble.textContent = content;
    } else {
      renderMarkdown(bubble, content);
    }

    row.appendChild(avatar);
    row.appendChild(bubble);
    messagesContainer.appendChild(row);
    return bubble;
  }

  function renderMarkdown(element, rawText) {
    if (window.marked) {
      element.innerHTML = marked.parse(rawText);
    } else {
      element.textContent = rawText;
    }

    // Add copy button to code blocks
    element.querySelectorAll('pre').forEach(pre => {
      if (!pre.querySelector('.btn-copy-code')) {
        const btnCopy = document.createElement('button');
        btnCopy.className = 'btn-copy-code';
        btnCopy.textContent = 'Kopyala';
        btnCopy.style.cssText = 'position:absolute; right:10px; top:10px; background:rgba(255,255,255,0.1); border:none; color:#fff; padding:4px 8px; border-radius:4px; font-size:0.75rem; cursor:pointer;';
        btnCopy.addEventListener('click', () => {
          const codeText = pre.querySelector('code')?.innerText || pre.innerText;
          navigator.clipboard.writeText(codeText);
          btnCopy.textContent = 'Kopyalandı!';
          setTimeout(() => btnCopy.textContent = 'Kopyala', 2000);
        });
        pre.style.position = 'relative';
        pre.appendChild(btnCopy);
      }
    });
  }

  function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // --- Search Threads Filter ---
  searchThreads.addEventListener('input', () => {
    const query = searchThreads.value.toLowerCase().trim();
    const filtered = allConversations.filter(c => (c.title || '').toLowerCase().includes(query));
    renderConversationsList(filtered);
  });
});
