function unwrapBridgeResponse(response) {
  if (
    response &&
    typeof response === "object" &&
    !Array.isArray(response) &&
    Object.prototype.hasOwnProperty.call(response, "status") &&
    Object.prototype.hasOwnProperty.call(response, "data")
  ) {
    if (String(response.status).toLowerCase() !== "ok") {
      throw new Error(response.message || t("request_failed"));
    }
    return response.data;
  }
  return response;
}

function getBridge() {
  const bridge = window.AstrBotPluginPage;
  if (!bridge) {
    throw new Error("Plugin page bridge is unavailable");
  }
  return bridge;
}

function normalizeEndpoint(url) {
  const text = String(url || "").trim();
  if (!text) {
    throw new Error("missing endpoint");
  }
  if (text.startsWith("/api/")) {
    return `page/${text.slice(5)}`;
  }
  if (text.startsWith("/editor/")) {
    return `page${text}`;
  }
  if (text.startsWith("/")) {
    return text.slice(1);
  }
  return text;
}

async function req(url, options = {}) {
  const rawUrl = String(url || "").trim();
  const [pathPart, queryString = ""] = rawUrl.split("?", 2);
  const endpoint = normalizeEndpoint(pathPart);
  const method = String(options.method || "GET").toUpperCase();
  const params = { ...(options.params || {}) };
  if (queryString) {
    const searchParams = new URLSearchParams(queryString);
    for (const [key, value] of searchParams.entries()) {
      if (Object.prototype.hasOwnProperty.call(params, key)) {
        const existing = params[key];
        params[key] = Array.isArray(existing)
          ? [...existing, value]
          : [existing, value];
      } else {
        params[key] = value;
      }
    }
  }
  try {
    if (method === "GET") {
      return unwrapBridgeResponse(await getBridge().apiGet(endpoint, params));
    }
    const body = options.body ? JSON.parse(options.body) : {};
    const payload = { ...body, _method: method };
    return unwrapBridgeResponse(await getBridge().apiPost(endpoint, payload));
  } catch (err) {
    throw new Error(err?.message || t("request_failed"));
  }
}

async function uploadReq(url, file) {
  try {
    return await getBridge().upload(normalizeEndpoint(url), file);
  } catch (err) {
    throw new Error(err?.message || t("request_failed"));
  }
}

async function downloadReq(url, params = {}, filename = "") {
  try {
    return await getBridge().download(
      normalizeEndpoint(url),
      params,
      filename || undefined
    );
  } catch (err) {
    throw new Error(err?.message || t("request_failed"));
  }
}

async function subscribeReq(url, handlers = {}, params = {}) {
  return getBridge().subscribeSSE(normalizeEndpoint(url), handlers, params);
}

async function unsubscribeReq(subscriptionId) {
  return getBridge().unsubscribeSSE(subscriptionId);
}

async function withButtonLoading(btn, task) {
  if (!btn) {
    return task();
  }
  if (btn.dataset.loading === "1") {
    return;
  }
  btn.dataset.loading = "1";
  btn.disabled = true;
  btn.classList.add("is-loading");
  try {
    return await task();
  } finally {
    btn.dataset.loading = "0";
    btn.disabled = false;
    btn.classList.remove("is-loading");
  }
}
