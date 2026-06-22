function createEditorFormManager(deps) {
  const { t, textValue, escapeHtml } = deps;

  function renderPairRows(containerId, pairs) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const safePairs =
      Array.isArray(pairs) && pairs.length ? pairs : [{ key: "", value: "" }];
    container.innerHTML = safePairs
      .map(
        (item, idx) => `
          <div class="kv-row">
            <input data-kv="${containerId}" data-kv-role="key" data-kv-index="${idx}" class="text-input" placeholder="${escapeHtml(t("key_name"))}" value="${escapeHtml(textValue(item.key))}">
            <input data-kv="${containerId}" data-kv-role="value" data-kv-index="${idx}" class="text-input" placeholder="${escapeHtml(t("value_name"))}" value="${escapeHtml(textValue(item.value))}">
            <button type="button" class="local-close-btn" title="${escapeHtml(t("delete"))}" aria-label="${escapeHtml(t("delete"))}" onclick="removePairRow('${containerId}', ${idx})">x</button>
          </div>
        `
      )
      .join("");
  }

  function readPairRows(containerId) {
    const keyNodes = Array.from(
      document.querySelectorAll(`[data-kv='${containerId}'][data-kv-role='key']`)
    );
    const valueNodes = Array.from(
      document.querySelectorAll(
        `[data-kv='${containerId}'][data-kv-role='value']`
      )
    );
    return keyNodes.map((node, idx) => ({
      key: node.value || "",
      value: valueNodes[idx] ? valueNodes[idx].value || "" : "",
    }));
  }

  function addPairRow(containerId) {
    const pairs = readPairRows(containerId);
    pairs.push({ key: "", value: "" });
    renderPairRows(containerId, pairs);
  }

  function removePairRow(containerId, index) {
    const next = readPairRows(containerId).filter((_, idx) => idx !== index);
    renderPairRows(containerId, next);
  }

  function pairsToMap(containerId) {
    const result = {};
    readPairRows(containerId).forEach((item) => {
      const key = textValue(item.key).trim();
      if (key) {
        result[key] = textValue(item.value);
      }
    });
    return result;
  }

  function renderListRows(containerId, items) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.classList.add("list-collection");
    const values = Array.isArray(items)
      ? items.map((item) => textValue(item).trim())
      : [];
    const safeValues = values.length ? values : [""];
    container.innerHTML = safeValues
      .map(
        (value, idx) => `
          <div class="list-row" data-list-row="${containerId}" data-list-row-index="${idx}">
            <input data-list="${containerId}" data-list-index="${idx}" class="text-input" placeholder="${escapeHtml(t("value_name"))}" value="${escapeHtml(textValue(value))}" oninput="onListInputChange('${containerId}')">
            <button type="button" class="local-close-btn" title="${escapeHtml(t("delete"))}" aria-label="${escapeHtml(t("delete"))}" onclick="removeListRow('${containerId}', ${idx})">x</button>
          </div>
        `
      )
      .join("");
    applyListLayout(containerId);
  }

  function readListRows(containerId, keepEmpty = false) {
    const nodes = Array.from(
      document.querySelectorAll(`[data-list='${containerId}']`)
    );
    const values = nodes.map((node) => textValue(node.value).trim());
    return keepEmpty ? values : values.filter(Boolean);
  }

  function addListRow(containerId) {
    const items = readListRows(containerId, true);
    items.push("");
    renderListRows(containerId, items);
  }

  function removeListRow(containerId, index) {
    const next = readListRows(containerId).filter((_, idx) => idx !== index);
    renderListRows(containerId, next);
  }

  function applyListLayout(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const rows = Array.from(
      container.querySelectorAll(`[data-list-row='${containerId}']`)
    );
    if (!rows.length) return;
    const gap = 8;
    const width = Math.max(260, container.clientWidth || 680);
    const specs = rows.map((row, idx) => {
      const input = row.querySelector(
        `[data-list='${containerId}'][data-list-index='${idx}']`
      );
      return {
        idx,
        est: PageHelpers.estimateListItemWidth(input ? input.value : ""),
      };
    });

    const rowGroups = [];
    let current = [];
    let used = 0;
    specs.forEach((item) => {
      const needed = current.length === 0 ? item.est : item.est + gap;
      if (current.length > 0 && used + needed > width) {
        rowGroups.push(current);
        current = [item];
        used = item.est;
      } else {
        current.push(item);
        used += needed;
      }
    });
    if (current.length) rowGroups.push(current);

    rowGroups.forEach((group) => {
      const cols = group.length || 1;
      group.forEach((entry) => {
        rows[entry.idx].style.setProperty("--row-cols", String(cols));
      });
    });
  }

  function onListInputChange(containerId) {
    applyListLayout(containerId);
  }

  return {
    renderPairRows,
    readPairRows,
    addPairRow,
    removePairRow,
    pairsToMap,
    renderListRows,
    readListRows,
    addListRow,
    removeListRow,
    applyListLayout,
    onListInputChange,
  };
}
