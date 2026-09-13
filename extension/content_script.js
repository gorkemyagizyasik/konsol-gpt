window.addEventListener("message", (event) => {
  if (event.source === window && event.data && event.data.type === "KONSOL_GPT_TRACE") {
    const trace = event.data.trace;
    if (trace) {
      chrome.runtime.sendMessage({
        action: "log_trace",
        trace: trace
      }).catch(() => {});
    }
  }
});
