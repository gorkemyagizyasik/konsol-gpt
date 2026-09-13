const DEFAULT_SERVER_URL = "http://localhost:8023";

async function getTargetServerUrl() {
  const data = await chrome.storage.local.get("serverUrl");
  return data.serverUrl || DEFAULT_SERVER_URL;
}

async function syncCookies() {
  try {
    const serverUrl = await getTargetServerUrl();
    const cookies = await chrome.cookies.getAll({ url: "https://chatgpt.com" });

    if (!cookies || cookies.length === 0) {
      await chrome.storage.local.set({
        lastSyncStatus: "error",
        lastSyncMessage: "ChatGPT çerezi bulunamadı. Lütfen chatgpt.com'a giriş yapın."
      });
      return { success: false, message: "ChatGPT çerezi bulunamadı." };
    }

    const cookieParts = cookies.map(c => `${c.name}=${c.value}`);
    const cookieString = cookieParts.join("; ");

    let deviceId = null;
    const didCookie = cookies.find(c => c.name === "oai-did");
    if (didCookie) {
      deviceId = didCookie.value;
    }

    const payload = { cookie: cookieString };
    if (deviceId) {
      payload.device_id = deviceId;
    }

    const res = await fetch(`${serverUrl}/api/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const timestamp = new Date().toLocaleTimeString("tr-TR");
      await chrome.storage.local.set({
        lastSyncStatus: "success",
        lastSyncTime: timestamp,
        lastSyncMessage: `Başarıyla senkronize edildi (${timestamp})`
      });
      await chrome.action.setBadgeText({ text: "OK" });
      await chrome.action.setBadgeBackgroundColor({ color: "#10B981" });
      return { success: true, message: `Başarıyla senkronize edildi (${timestamp})` };
    } else {
      const errText = await res.text();
      await chrome.storage.local.set({
        lastSyncStatus: "error",
        lastSyncMessage: `Sunucu hatası (${res.status}): ${errText.slice(0, 50)}`
      });
      await chrome.action.setBadgeText({ text: "ERR" });
      await chrome.action.setBadgeBackgroundColor({ color: "#EF4444" });
      return { success: false, message: `Sunucu hatası (${res.status})` };
    }
  } catch (err) {
    await chrome.storage.local.set({
      lastSyncStatus: "error",
      lastSyncMessage: `Bağlantı hatası: ${err.message}`
    });
    await chrome.action.setBadgeText({ text: "OFF" });
    await chrome.action.setBadgeBackgroundColor({ color: "#6B7280" });
    return { success: false, message: `Bağlantı hatası: ${err.message}` };
  }
}

// Cookie değişikliklerini dinle (Debounce 3sn)
let syncTimeout = null;
chrome.cookies.onChanged.addListener((changeInfo) => {
  if (changeInfo.cookie.domain.includes("chatgpt.com")) {
    if (syncTimeout) clearTimeout(syncTimeout);
    syncTimeout = setTimeout(() => {
      syncCookies();
    }, 3000);
  }
});

// Popup veya başka scriptlerden gelen mesajları işle
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "sync_now") {
    syncCookies().then(res => sendResponse(res));
    return true; // async response
  }
});
