function textValue(value) {
  return value === undefined || value === null ? "" : String(value);
}

const SafeStorage = (window.SafeStorage = {
  get(key, fallback = null) {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return fallback;
    }
  },

  set(key, value) {
    try {
      window.localStorage.setItem(key, value);
      return true;
    } catch {
      return false;
    }
  },
});

function normalizeList(items) {
  if (!Array.isArray(items)) return [];
  return items.map((item) => textValue(item).trim()).filter(Boolean);
}

function stringToLineList(value) {
  return textValue(value)
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeMap(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    return {};
  }
  const result = {};
  Object.entries(input).forEach(([key, value]) => {
    const keyText = textValue(key).trim();
    if (keyText) {
      result[keyText] = textValue(value);
    }
  });
  return result;
}

function mapToPairs(mapObj) {
  const obj = normalizeMap(mapObj);
  const pairs = Object.entries(obj).map(([key, value]) => ({ key, value }));
  return pairs.length ? pairs : [{ key: "", value: "" }];
}

function formatBytes(sizeBytes) {
  const size = Math.max(0, Number(sizeBytes || 0));
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  return `${(size / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

function formatTimestamp(ts) {
  const value = Number(ts || 0);
  if (!Number.isFinite(value) || value <= 0) {
    return "-";
  }
  try {
    return new Date(value * 1000).toLocaleString();
  } catch {
    return "-";
  }
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
