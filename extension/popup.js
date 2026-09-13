document.addEventListener("DOMContentLoaded", async () => {
  const serverUrlInput = document.getElementById("serverUrl");
  const syncBtn = document.getElementById("syncBtn");
  const statusDot = document.getElementById("statusDot");
  const statusTitle = document.getElementById("statusTitle");
  const statusText = document.getElementById("statusText");

  // Load saved state
  const data = await chrome.storage.local.get(["serverUrl", "lastSyncStatus", "lastSyncMessage", "lastSyncTime"]);
  if (data.serverUrl) {
    serverUrlInput.value = data.serverUrl;
  }

  updateStatusUI(data.lastSyncStatus, data.lastSyncMessage || "Henüz senkronize edilmedi.");

  // Save server URL on change
  serverUrlInput.addEventListener("change", async () => {
    const newUrl = serverUrlInput.value.trim().replace(/\/+$/, "");
    await chrome.storage.local.set({ serverUrl: newUrl });
  });

  // Sync button click
  syncBtn.addEventListener("click", async () => {
    syncBtn.disabled = true;
    statusTitle.textContent = "Senkronize Ediliyor...";
    statusDot.className = "status-dot";

    chrome.runtime.sendMessage({ action: "sync_now" }, (response) => {
      syncBtn.disabled = false;
      if (response && response.success) {
        updateStatusUI("success", response.message);
      } else {
        updateStatusUI("error", response ? response.message : "Senkronizasyon başarısız.");
      }
    });
  });

  function updateStatusUI(status, message) {
    statusDot.className = "status-dot";
    if (status === "success") {
      statusDot.classList.add("success");
      statusTitle.textContent = "Bağlandı & Senkronize";
    } else if (status === "error") {
      statusDot.classList.add("error");
      statusTitle.textContent = "Bağlantı/Senkronizasyon Hatası";
    } else {
      statusTitle.textContent = "Beklemede";
    }
    statusText.textContent = message || "-";
  }
});
