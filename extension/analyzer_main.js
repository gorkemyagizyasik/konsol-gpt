(function () {
  if (window.__konsol_gpt_analyzer_injected) return;
  window.__konsol_gpt_analyzer_injected = true;

  console.log("🔍 Konsol-GPT Network Analyzer Interceptor Active");

  const origFetch = window.fetch;

  window.fetch = async function (resource, options) {
    const url = typeof resource === "string" ? resource : (resource ? resource.url : "");
    const method = (options && options.method) ? options.method.toUpperCase() : "GET";

    if (url && (url.includes("/backend-api/") || url.includes("/sentinel/"))) {
      let rawHeaders = {};
      if (options && options.headers) {
        if (options.headers instanceof Headers) {
          options.headers.forEach((val, key) => rawHeaders[key] = val);
        } else if (Array.isArray(options.headers)) {
          options.headers.forEach(([key, val]) => rawHeaders[key] = val);
        } else if (typeof options.headers === "object") {
          rawHeaders = { ...options.headers };
        }
      }

      let parsedBody = null;
      if (options && options.body) {
        try {
          parsedBody = typeof options.body === "string" ? JSON.parse(options.body) : options.body;
        } catch (e) {
          parsedBody = options.body;
        }
      }

      const traceData = {
        url: url,
        method: method,
        headers: rawHeaders,
        body: parsedBody,
        timestamp: new Date().toISOString()
      };

      try {
        window.postMessage({
          type: "KONSOL_GPT_TRACE",
          trace: traceData
        }, "*");
      } catch (e) {}
    }

    return origFetch.apply(this, arguments);
  };
})();
