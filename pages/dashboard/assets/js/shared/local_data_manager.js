function createLocalDataManager(deps) {
  const {
    t,
    req,
    withButtonLoading,
    textValue,
    escapeHtml,
    formatBytes,
    formatTimestamp,
    formatLocalType,
    renderPager,
    formatItems,
    showNoticeModal,
    getLocalCollections,
    setLocalCollections,
    getLocalPagination,
    setLocalPagination,
    getLocalSearchText,
    getLocalPage,
    setLocalPage,
    getLocalPageSize,
    getLocalTypeFilterValues,
    getSortState,
    localSortRules,
    getLocalViewerState,
    setLocalViewerState,
    isPendingDelete,
    togglePendingDelete,
  } = deps;
  const mediaObjectUrls = new Map();

  function revokeMediaUrl(path) {
    const key = textValue(path).trim();
    if (!key) return;
    const existing = mediaObjectUrls.get(key);
    if (existing) {
      URL.revokeObjectURL(existing);
      mediaObjectUrls.delete(key);
    }
  }

  function revokeAllMediaUrls() {
    Array.from(mediaObjectUrls.keys()).forEach((key) => {
      revokeMediaUrl(key);
    });
  }

  function decodeBase64ToUint8Array(base64Text) {
    const normalized = textValue(base64Text).trim();
    const binary = window.atob(normalized);
    const length = binary.length;
    const bytes = new Uint8Array(length);
    for (let i = 0; i < length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }

  async function ensureMediaObjectUrl(path) {
    const normalizedPath = textValue(path).trim();
    if (!normalizedPath) {
      throw new Error("missing local file path");
    }
    const cached = mediaObjectUrls.get(normalizedPath);
    if (cached) {
      return cached;
    }
    const result = await req(`/api/local-file/content?path=${encodeURIComponent(normalizedPath)}`);
    const bytes = decodeBase64ToUint8Array(result?.content_base64);
    const blob = new Blob([bytes], {
      type: textValue(result?.content_type).trim() || "application/octet-stream",
    });
    const objectUrl = URL.createObjectURL(blob);
    mediaObjectUrls.set(normalizedPath, objectUrl);
    return objectUrl;
  }

  async function hydrateLocalMediaItems(detail) {
    const type = textValue(detail?.type).trim().toLowerCase();
    if (type !== "image" && type !== "video" && type !== "audio") {
      return detail;
    }
    const items = Array.isArray(detail?.items) ? detail.items : [];
    if (!items.length) {
      return detail;
    }
    const nextItems = await Promise.all(
      items.map(async (item) => {
        const path = textValue(item?.path).trim();
        if (!path) {
          return { ...item, preview_url: "" };
        }
        try {
          const previewUrl = await ensureMediaObjectUrl(path);
          return { ...item, preview_url: previewUrl };
        } catch {
          return { ...item, preview_url: "" };
        }
      })
    );
    return { ...detail, items: nextItems };
  }

  function getPendingDeleteSet() {
    const state = getLocalViewerState();
    if (!(state.pendingDeletes instanceof Set)) {
      state.pendingDeletes = new Set();
      setLocalViewerState(state);
    }
    return state.pendingDeletes;
  }

  function makePendingDeleteKey(type, index, path) {
    const normalizedType = textValue(type).trim().toLowerCase();
    if (normalizedType === "text" && Number(index) >= 0) {
      return `idx:${Number(index)}`;
    }
    return `path:${textValue(path)}`;
  }

  function updateLocalDeleteConfirmButton() {
    const btn = document.getElementById("btnConfirmLocalDataDelete");
    if (!btn) return;
    const pendingCount = getPendingDeleteSet().size;
    btn.disabled = pendingCount <= 0;
    btn.textContent =
      pendingCount > 0
        ? t("confirm_delete_count", { count: pendingCount })
        : t("confirm_delete");
  }

  function tuneLocalDataModalLayout(type, count) {
    const dialog = document.getElementById("localDataDialog");
    const list = document.getElementById("localDataItems");
    if (!dialog || !list) return;

    const n = Math.max(0, Number(count || 0));
    const isMedia = type === "image" || type === "video";
    const isAudio = type === "audio";

    let width = "min(860px, 96vw)";
    if (isMedia) {
      width =
        n <= 2 ? "min(760px, 96vw)" : n <= 6 ? "min(980px, 96vw)" : "min(1120px, 98vw)";
    } else if (isAudio) {
      width = n <= 4 ? "min(900px, 96vw)" : "min(1020px, 98vw)";
    } else {
      width =
        n <= 6 ? "min(760px, 94vw)" : n <= 20 ? "min(900px, 96vw)" : "min(1020px, 98vw)";
    }

    const maxHeight = n <= 4 ? "50vh" : n <= 12 ? "62vh" : "72vh";
    const minHeight = n === 0 ? "120px" : n <= 3 ? "180px" : "260px";

    dialog.style.width = width;
    list.style.maxHeight = maxHeight;
    list.style.minHeight = minHeight;
  }

  function renderLocalDataItems(detail) {
    const list = document.getElementById("localDataItems");
    const hint = document.getElementById("localDataModalHint");
    if (!list || !hint) return;

    const type = textValue(detail?.type).toLowerCase();
    const items = Array.isArray(detail?.items) ? detail.items : [];
    const pendingDeletes = getPendingDeleteSet();
    hint.textContent = `${t("items_count", { count: items.length })} | ${formatBytes(
      detail?.size_bytes || 0
    )}`;
    tuneLocalDataModalLayout(type, items.length);
    updateLocalDeleteConfirmButton();

    if (items.length === 0) {
      list.innerHTML = `<div class="empty-cell">${t("no_data")}</div>`;
      return;
    }

    if (type === "text") {
      list.innerHTML = `
          <div class="local-list-compact">
            ${items
              .map((item) => {
                const text = textValue(item?.text);
                const itemIndex = Number(item?.index ?? -1);
                const pendingKey = makePendingDeleteKey(type, itemIndex, "");
                const isPending = pendingDeletes.has(pendingKey);
                return `
                <div class="local-row-compact ${isPending ? "is-pending-delete" : ""}">
                  <button
                    class="local-close-btn ${isPending ? "is-pending-delete" : ""}"
                    title="${escapeHtml(t("delete"))}"
                    aria-label="${escapeHtml(t("delete"))}"
                    onclick='removeLocalItem(this, "${encodeURIComponent(type)}", "${encodeURIComponent(
                  textValue(detail.name)
                )}", ${itemIndex}, "")'
                  >x</button>
                  <div class="local-row-main">
                    <span class="local-row-index">${itemIndex + 1}</span>
                    <span class="local-row-text" title="${escapeHtml(text)}">${escapeHtml(text)}</span>
                  </div>
                </div>
              `;
              })
              .join("")}
          </div>
        `;
      return;
    }

    if (type === "audio") {
      list.innerHTML = `
          <div class="local-list-compact">
            ${items
              .map((item) => {
                const path = textValue(item?.path);
                const pendingKey = makePendingDeleteKey(type, -1, path);
                const isPending = pendingDeletes.has(pendingKey);
                const fileUrl = textValue(item?.preview_url);
                return `
                <div class="local-row-compact local-row-audio ${isPending ? "is-pending-delete" : ""}">
                  <button
                    class="local-close-btn ${isPending ? "is-pending-delete" : ""}"
                    title="${escapeHtml(t("delete"))}"
                    aria-label="${escapeHtml(t("delete"))}"
                    onclick='removeLocalItem(this, "${encodeURIComponent(type)}", "${encodeURIComponent(
                  textValue(detail.name)
                )}", -1, "${encodeURIComponent(path)}")'
                  >x</button>
                  <div class="local-row-main">
                    <span class="local-row-label">${escapeHtml(textValue(item?.name))}</span>
                    ${
                      fileUrl
                        ? `<audio class="local-audio-inline" src="${escapeHtml(fileUrl)}" controls preload="metadata"></audio>`
                        : `<span class="hint">${escapeHtml(t("test_failed"))}</span>`
                    }
                  </div>
                </div>
              `;
              })
              .join("")}
          </div>
        `;
      return;
    }

    list.innerHTML = `
        <div class="local-media-grid">
          ${items
            .map((item) => {
              const path = textValue(item?.path);
              const pendingKey = makePendingDeleteKey(type, -1, path);
              const isPending = pendingDeletes.has(pendingKey);
              const fileUrl = textValue(item?.preview_url);
              const media =
                !fileUrl
                  ? `<div class="empty-cell">${escapeHtml(t("test_failed"))}</div>`
                  : type === "image"
                    ? `<img class="test-saved-media test-saved-image" src="${escapeHtml(fileUrl)}" alt="saved image">`
                    : `<video class="test-saved-media" src="${escapeHtml(fileUrl)}" controls preload="metadata"></video>`;
              return `
              <div class="local-media-card ${isPending ? "is-pending-delete" : ""}">
                <button
                  class="local-close-btn ${isPending ? "is-pending-delete" : ""}"
                  title="${escapeHtml(t("delete"))}"
                  aria-label="${escapeHtml(t("delete"))}"
                  onclick='removeLocalItem(this, "${encodeURIComponent(type)}", "${encodeURIComponent(
                textValue(detail.name)
              )}", -1, "${encodeURIComponent(path)}")'
                >x</button>
                <div class="local-item-meta">${escapeHtml(textValue(item?.name))}</div>
                ${media}
              </div>
            `;
            })
            .join("")}
        </div>
      `;
  }

  function renderLocalData() {
    const table = document.getElementById("localDataTable");
    if (!table) return;

    const pageItems = Array.isArray(getLocalCollections()) ? getLocalCollections() : [];
    const meta = getLocalPagination() || {};
    const pagination = {
      page: Math.max(1, Number(meta.page || getLocalPage() || 1)),
      page_size: meta.page_size ?? getLocalPageSize(),
      total: Math.max(0, Number(meta.total || pageItems.length || 0)),
      total_pages: Math.max(1, Number(meta.total_pages || 1)),
      start: Math.max(0, Number(meta.start || 0)),
      end: Math.max(0, Number(meta.end || 0)),
    };
    setLocalPage(pagination.page);
    SafeStorage.set("api_aggregator_page_local", String(getLocalPage()));

    const countNode = document.getElementById("localDataCount");
    if (countNode) {
      countNode.textContent = formatItems(pagination.total);
    }

    renderPager({
      pagerId: "localPagerTop",
      page: getLocalPage(),
      totalPages: pagination.total_pages,
      total: pagination.total,
      start: pagination.total > 0 ? pagination.start : 0,
      end: pagination.total > 0 ? pagination.end : 0,
      onPageChange: "onLocalPageChange",
    });

    const serialBase = pagination.total > 0 ? Math.max(1, Number(pagination.start || 1)) : 0;

    const rows = pageItems
      .map(
        (item, index) => `
        <tr class="${
          isPendingDelete("local_collection", {
            type: textValue(item.type),
            name: textValue(item.name),
          })
            ? "is-pending-delete-row"
            : ""
        }">
          <td>${serialBase + index}</td>
          <td><code class="name-code">${escapeHtml(textValue(item.name))}</code></td>
          <td>${formatLocalType(item.type)}</td>
          <td>${Number(item.count || 0)}</td>
          <td>${escapeHtml(formatBytes(item.size_bytes))}</td>
          <td>${escapeHtml(formatTimestamp(item.updated_at))}</td>
          <td class="actions-cell">
            <button onclick='openLocalDataViewer(this, "${encodeURIComponent(
              textValue(item.type)
            )}", "${encodeURIComponent(textValue(item.name))}")'>${t("view")}</button>
            <button class="danger ${
              isPendingDelete("local_collection", {
                type: textValue(item.type),
                name: textValue(item.name),
              })
                ? "is-pending-delete"
                : ""
            }" onclick='removeLocalCollection(this, "${encodeURIComponent(
              textValue(item.type)
            )}", "${encodeURIComponent(textValue(item.name))}")'>${t("delete")}</button>
          </td>
        </tr>
      `
      )
      .join("");

    const sortState = getSortState();
    table.innerHTML = `
        <thead>
          <tr>
            <th>${t("serial_no")}</th>
            <th class="sortable-head" onclick="onLocalHeaderSort('name')">${t("name")}<span class="sort-indicator">${PageHelpers.getSortIndicator(sortState.local, localSortRules.name)}</span></th>
            <th class="sortable-head" onclick="onLocalHeaderSort('type')">${t("type")}<span class="sort-indicator">${PageHelpers.getSortIndicator(sortState.local, localSortRules.type)}</span></th>
            <th class="sortable-head" onclick="onLocalHeaderSort('count')">${t("items_count_short")}<span class="sort-indicator">${PageHelpers.getSortIndicator(sortState.local, localSortRules.count)}</span></th>
            <th class="sortable-head" onclick="onLocalHeaderSort('size')">${t("size")}<span class="sort-indicator">${PageHelpers.getSortIndicator(sortState.local, localSortRules.size)}</span></th>
            <th class="sortable-head" onclick="onLocalHeaderSort('updated')">${t("updated_at")}<span class="sort-indicator">${PageHelpers.getSortIndicator(sortState.local, localSortRules.updated)}</span></th>
            <th>${t("actions")}</th>
          </tr>
        </thead>
        <tbody>
          ${rows || `<tr><td colspan="7" class="empty-cell">${t("no_data")}</td></tr>`}
        </tbody>
      `;
  }

  function closeLocalDataModal() {
    const modal = document.getElementById("localDataModal");
    if (modal) {
      modal.classList.remove("open");
    }
    revokeAllMediaUrls();
    const state = getLocalViewerState();
    state.pendingDeletes = new Set();
    setLocalViewerState(state);
    updateLocalDeleteConfirmButton();
  }

  async function loadLocalData() {
    try {
      const params = new URLSearchParams({
        page: String(Math.max(1, Number(getLocalPage() || 1))),
        page_size: String(getLocalPageSize()),
        search: textValue(getLocalSearchText()).trim(),
        sort: textValue(getSortState().local || "name_asc"),
      });
      const typeValues = Array.isArray(getLocalTypeFilterValues?.())
        ? getLocalTypeFilterValues()
        : [];
      if (typeValues.length) {
        params.set("types", typeValues.join(","));
      }
      const data = await req(`/api/local-data?${params.toString()}`);
      const collections = Array.isArray(data?.collections) ? data.collections : [];
      setLocalCollections(collections);
      const pagination = data?.pagination && typeof data.pagination === "object" ? data.pagination : {};
      setLocalPagination({
        page: Math.max(1, Number(pagination.page || getLocalPage() || 1)),
        page_size: pagination.page_size ?? getLocalPageSize(),
        total: Math.max(0, Number(pagination.total || collections.length || 0)),
        total_pages: Math.max(1, Number(pagination.total_pages || 1)),
        start: Math.max(0, Number(pagination.start || 0)),
        end: Math.max(0, Number(pagination.end || 0)),
      });
      renderLocalData();
    } catch (err) {
      showNoticeModal(err.message || String(err));
    }
  }

  async function onRefreshLocalDataClick(btn) {
    await withButtonLoading(btn, async () => {
      await loadLocalData();
    });
  }

  async function openLocalDataViewer(btn, type, name) {
    await withButtonLoading(btn, async () => {
      try {
        const decodedType = decodeURIComponent(type || "");
        const decodedName = decodeURIComponent(name || "");
        const result = await req("/api/local-data/items/batch", {
          method: "POST",
          body: JSON.stringify({
            targets: [{ type: decodedType, name: decodedName }],
          }),
        });
        const detail = Array.isArray(result?.success) && result.success.length
          ? result.success[0].detail
          : null;
        if (!detail) {
          throw new Error(t("no_data"));
        }
        const hydratedDetail = await hydrateLocalMediaItems(detail);
        setLocalViewerState({
          type: decodedType,
          name: decodedName,
          detail: hydratedDetail,
          pendingDeletes: new Set(),
        });
        document.getElementById("localDataModalTitle").textContent = `${decodedName} (${decodedType})`;
        renderLocalDataItems(hydratedDetail);
        const modal = document.getElementById("localDataModal");
        if (modal) modal.classList.add("open");
      } catch (err) {
        showNoticeModal(err.message || String(err));
      }
    });
  }

  async function removeLocalCollection(btn, type, name) {
    void btn;
    try {
      const decodedType = decodeURIComponent(type || "");
      const decodedName = decodeURIComponent(name || "");
      if (!decodedType || !decodedName) return;
      togglePendingDelete("local_collection", {
        type: decodedType,
        name: decodedName,
      });
    } catch (err) {
      showNoticeModal(err.message || String(err));
    }
  }

  function removeLocalItem(_, type, __, index, path) {
    const state = getLocalViewerState();
    const decodedType = decodeURIComponent(type || "");
    const decodedPath = path ? decodeURIComponent(path || "") : "";
    const pendingKey = makePendingDeleteKey(decodedType, Number(index), decodedPath);
    const pendingDeletes = getPendingDeleteSet();
    if (pendingDeletes.has(pendingKey)) {
      pendingDeletes.delete(pendingKey);
    } else {
      pendingDeletes.add(pendingKey);
    }
    renderLocalDataItems(state.detail || {});
  }

  async function onConfirmLocalDataDeleteClick(btn) {
    await withButtonLoading(btn, async () => {
      try {
        const state = getLocalViewerState();
        const decodedType = textValue(state.type);
        const decodedName = textValue(state.name);
        const pendingDeletes = getPendingDeleteSet();
        if (!decodedType || !decodedName || pendingDeletes.size <= 0) {
          updateLocalDeleteConfirmButton();
          return;
        }

        const items = Array.from(pendingDeletes).map((key) => {
          if (key.startsWith("idx:")) {
            return { index: Number(key.slice(4)) };
          }
          return { path: key.startsWith("path:") ? key.slice(5) : key };
        });

        await req("/api/local-data-item/batch", {
          method: "DELETE",
          body: JSON.stringify({
            targets: [{ type: decodedType, name: decodedName, items }],
          }),
        });

        const result = await req("/api/local-data/items/batch", {
          method: "POST",
          body: JSON.stringify({
            targets: [{ type: decodedType, name: decodedName }],
          }),
        });
        const detail = Array.isArray(result?.success) && result.success.length
          ? result.success[0].detail
          : null;
        if (!detail) {
          throw new Error(t("no_data"));
        }
        const hydratedDetail = await hydrateLocalMediaItems(detail);
        revokeAllMediaUrls();
        setLocalViewerState({
          ...state,
          detail: hydratedDetail,
          pendingDeletes: new Set(),
        });
        renderLocalDataItems(hydratedDetail);
        await loadLocalData();
      } catch (err) {
        const msg = textValue(err?.message);
        if (msg.includes("not found")) {
          closeLocalDataModal();
          await loadLocalData();
          return;
        }
        showNoticeModal(msg || String(err));
      }
    });
  }

  return {
    renderLocalData,
    closeLocalDataModal,
    getPendingDeleteSet,
    makePendingDeleteKey,
    updateLocalDeleteConfirmButton,
    tuneLocalDataModalLayout,
    renderLocalDataItems,
    loadLocalData,
    onRefreshLocalDataClick,
    openLocalDataViewer,
    removeLocalCollection,
    removeLocalItem,
    onConfirmLocalDataDeleteClick,
    revokeAllMediaUrls,
  };
}

