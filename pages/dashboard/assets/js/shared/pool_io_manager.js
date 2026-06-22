function createPoolIoManager(deps) {
  const {
    t,
    req,
    uploadReq,
    withButtonLoading,
    textValue,
    escapeHtml,
    showNoticeModal,
    loadPool,
    getDisplayedApiRows,
    getDisplayedSiteRows,
  } = deps;

  let poolIoState = { poolType: "site", mode: "export" };
  let defaultPoolIoPath = "pool_files";
  let defaultPoolIoFiles = [];
  let poolIoExternalFiles = [];
  let poolIoFileRows = [];
  let poolIoSelectedFileIds = new Set();
  let poolIoImporting = false;

  function getMenuNode(poolType) {
    return document.getElementById(poolType === "api" ? "apiPoolIoMenu" : "sitePoolIoMenu");
  }

  function closeMenus() {
    const menus = [
      document.getElementById("sitePoolIoMenu"),
      document.getElementById("apiPoolIoMenu"),
    ];
    menus.forEach((menu) => {
      if (!menu) return;
      menu.classList.remove("open");
      const dropdown = menu.querySelector(".pool-io-dropdown");
      if (dropdown) dropdown.classList.remove("open");
    });
  }

  function toggleMenu(event, poolType) {
    if (event && typeof event.stopPropagation === "function") {
      event.stopPropagation();
    }
    const menu = getMenuNode(poolType);
    if (!menu) return;
    const willOpen = !menu.classList.contains("open");
    closeMenus();
    if (willOpen) {
      menu.classList.add("open");
      const dropdown = menu.querySelector(".pool-io-dropdown");
      if (dropdown) dropdown.classList.add("open");
    }
  }

  function closeModal() {
    const modal = document.getElementById("poolIoModal");
    if (modal) modal.classList.remove("open");
    poolIoSelectedFileIds = new Set();
    poolIoExternalFiles = [];
    poolIoFileRows = [];
    poolIoImporting = false;
    renderDefaultFiles([]);
    updateImportProgress(0, 0);
  }

  async function listDefaultFiles() {
    const data = await req("/api/pool/files");
    const files = Array.isArray(data.files) ? data.files : [];
    const baseDir = textValue(data.base_dir).trim();
    if (baseDir) {
      defaultPoolIoPath = baseDir;
    }
    return files;
  }

  function renderDefaultFiles(files) {
    const listNode = document.getElementById("poolIoDefaultList");
    if (!listNode) return;
    const rows = Array.isArray(files) ? files : [];
    if (!rows.length) {
      listNode.innerHTML = `<div class="empty-cell">${t("import_default_files_empty")}</div>`;
      return;
    }
    listNode.innerHTML = rows
      .map((item, idx) => {
        const row = item && typeof item === "object" ? item : {};
        const id = textValue(row.id).trim() || `pool-io-${idx}`;
        const name = textValue(row.name).trim();
        const encoded = encodeURIComponent(id);
        const selected = poolIoSelectedFileIds.has(id) ? " is-selected" : "";
        const checked = poolIoSelectedFileIds.has(id) ? " checked" : "";
        const title = textValue(row.path || name).trim();
        return `
          <button
            type="button"
            class="pool-io-default-item${selected}"
            title="${escapeHtml(title)}"
            onclick='onPoolDefaultFileToggle(this, "${encoded}")'
          >
            <span class="pool-io-item-name">${escapeHtml(name)}</span>
            <input class="pool-io-item-check" type="checkbox"${checked} tabindex="-1" aria-hidden="true">
          </button>
        `;
      })
      .join("");
  }

  function onDefaultFileToggle(btn, encodedName) {
    if (poolIoImporting) return;
    const rowId = textValue(decodeURIComponent(encodedName || "")).trim();
    if (!rowId) return;
    if (poolIoSelectedFileIds.has(rowId)) {
      poolIoSelectedFileIds.delete(rowId);
    } else {
      poolIoSelectedFileIds.add(rowId);
    }
    if (btn) {
      const selected = poolIoSelectedFileIds.has(rowId);
      btn.classList.toggle("is-selected", selected);
      const check = btn.querySelector(".pool-io-item-check");
      if (check) check.checked = selected;
    }
  }

  function buildRows(defaultFiles, externalFiles) {
    const rows = [];
    const defaults = Array.isArray(defaultFiles) ? defaultFiles : [];
    defaults.forEach((item) => {
      const name = textValue(item?.name).trim();
      if (!name) return;
      rows.push({
        id: `default:${name}`,
        name,
        path: `${defaultPoolIoPath}\\${name}`,
        source: "default",
        fileName: name,
      });
    });
    const uploads = Array.isArray(externalFiles) ? externalFiles : [];
    uploads.forEach((file, index) => {
      if (!file || !file.name) return;
      const name = textValue(file.name).trim();
      if (!name) return;
      rows.push({
        id: `external:${index}:${name}:${Number(file.size || 0)}:${Number(file.lastModified || 0)}`,
        name,
        path: textValue(file.webkitRelativePath || file.name),
        source: "external",
        file,
      });
    });
    return rows;
  }

  function refreshRows() {
    poolIoFileRows = buildRows(defaultPoolIoFiles, poolIoExternalFiles);
    const validIds = new Set(poolIoFileRows.map((item) => textValue(item.id).trim()).filter(Boolean));
    poolIoSelectedFileIds = new Set(
      Array.from(poolIoSelectedFileIds).filter((id) => validIds.has(id))
    );
    renderDefaultFiles(poolIoFileRows);
  }

  function onPickDirClick() {
    if (poolIoImporting || poolIoState.mode !== "import") return;
    const input = document.getElementById("poolIoDirInput");
    if (!input) return;
    input.value = "";
    input.click();
  }

  function onDirChange(input) {
    if (!input) return;
    const files = Array.from(input.files || []).filter((file) =>
      textValue(file?.name).toLowerCase().endsWith(".json")
    );
    poolIoExternalFiles = files;
    refreshRows();
  }

  function updateImportProgress(current, total, stats = null) {
    const wrap = document.getElementById("poolIoProgressWrap");
    const fill = document.getElementById("poolIoProgressFill");
    const text = document.getElementById("poolIoProgressText");
    if (!wrap || !fill || !text) return;
    if (!total) {
      wrap.classList.remove("open");
      fill.style.width = "0%";
      text.textContent = "";
      return;
    }
    wrap.classList.add("open");
    const percent = Math.max(0, Math.min(100, Math.round((current / total) * 100)));
    fill.style.width = `${percent}%`;
    if (stats) {
      text.textContent = t("pool_import_progress_done", {
        current,
        total,
        success: Number(stats.success || 0),
        skipped: Number(stats.skipped || 0),
        failed: Number(stats.failed || 0),
      });
      return;
    }
    text.textContent = t("pool_import_progress", { current, total });
  }

  async function openModal(poolType, mode) {
    closeMenus();
    poolIoState = {
      poolType: poolType === "api" ? "api" : "site",
      mode: mode === "import" ? "import" : "export",
    };

    const modal = document.getElementById("poolIoModal");
    const title = document.getElementById("poolIoModalTitle");
    const exportCount = document.getElementById("poolIoExportCount");
    const message = document.getElementById("poolIoModalMessage");
    const fileWrap = document.getElementById("poolIoFileWrap");
    const pathText = document.getElementById("poolIoDirPath");
    const pickDirBtn = document.getElementById("btnPoolIoPickDir");
    const deleteBtn = document.getElementById("btnPoolIoDelete");
    const defaultList = document.getElementById("poolIoDefaultList");
    const pathWrap = document.getElementById("poolIoPathWrap");
    const pathInput = document.getElementById("poolIoExportPath");
    const nameInput = document.getElementById("poolIoExportName");
    const confirmBtn = document.getElementById("btnPoolIoConfirm");
    if (!modal || !title || !message || !fileWrap || !pathWrap || !confirmBtn) return;

    const poolLabel = poolIoState.poolType === "api" ? t("api_pool") : t("site_pool");
    title.textContent = t("pool_file_modal_title", { pool: poolLabel });

    if (poolIoState.mode === "import") {
      if (exportCount) {
        exportCount.style.display = "none";
        exportCount.textContent = "";
      }
      poolIoSelectedFileIds = new Set();
      poolIoExternalFiles = [];
      poolIoImporting = false;
      message.textContent = "";
      message.style.display = "none";
      fileWrap.style.display = "";
      pathWrap.style.display = "none";
      if (pathText) {
        pathText.style.display = "";
        pathText.textContent = t("import_default_dir", { path: defaultPoolIoPath });
      }
      if (pickDirBtn) pickDirBtn.style.display = "";
      if (deleteBtn) deleteBtn.style.display = "";
      if (defaultList) {
        defaultList.innerHTML = `<div class="empty-cell">${t("import_select_file_hint")}</div>`;
      }
      confirmBtn.textContent = t("import_file");
      updateImportProgress(0, 0);
      try {
        defaultPoolIoFiles = await listDefaultFiles();
        if (pathText) {
          pathText.textContent = t("import_default_dir", { path: defaultPoolIoPath });
        }
        refreshRows();
      } catch (err) {
        poolIoFileRows = [];
        renderDefaultFiles([]);
        showNoticeModal(err.message || String(err));
      }
    } else {
      if (exportCount) {
        const visibleCount = poolIoState.poolType === "api"
          ? getDisplayedApiRows().length
          : getDisplayedSiteRows().length;
        exportCount.style.display = "";
        exportCount.textContent = t("export_items_count", { count: visibleCount });
      }
      message.textContent = t("export_file_hint", { pool: poolLabel, path: defaultPoolIoPath });
      message.style.display = "";
      fileWrap.style.display = "none";
      pathWrap.style.display = "";
      if (pathText) {
        pathText.style.display = "none";
        pathText.textContent = "";
      }
      if (pickDirBtn) pickDirBtn.style.display = "none";
      if (deleteBtn) deleteBtn.style.display = "none";
      if (pathInput) {
        const normalized = normalizeExportInputs(
          textValue(pathInput.value).trim(),
          textValue(nameInput && nameInput.value).trim(),
          poolIoState.poolType
        );
        pathInput.value = normalized.dir;
        pathInput.placeholder = t("export_path_placeholder");
        if (nameInput) {
          nameInput.value = normalized.name;
          nameInput.placeholder = t("export_name_placeholder");
        }
      } else if (nameInput) {
        const normalized = normalizeExportInputs(
          "",
          textValue(nameInput.value).trim(),
          poolIoState.poolType
        );
        nameInput.value = normalized.name;
        nameInput.placeholder = t("export_name_placeholder");
      }
      confirmBtn.textContent = t("export_file");
    }

    modal.classList.add("open");
  }

  async function exportPoolToPath(poolType, targetPath, items = null) {
    return await req(`/api/pool/export/${encodeURIComponent(poolType)}`, {
      method: "POST",
      body: JSON.stringify({
        path: targetPath || "",
        items: Array.isArray(items) ? items : undefined,
      }),
    });
  }

  function joinExportTargetPath(dirPath, fileName) {
    const baseDir = textValue(dirPath).trim() || defaultPoolIoPath;
    let name = textValue(fileName).trim();
    if (!name) return baseDir;
    if (!name.toLowerCase().endsWith(".json")) {
      name = `${name}.json`;
    }
    const hasSep = baseDir.endsWith("/") || baseDir.endsWith("\\");
    return `${baseDir}${hasSep ? "" : "/"}${name}`;
  }

  function buildDefaultExportFileName(poolType) {
    const safeType = poolType === "api" ? "api" : "site";
    const now = new Date();
    const pad2 = (v) => String(v).padStart(2, "0");
    const stamp = `${now.getFullYear()}${pad2(now.getMonth() + 1)}${pad2(now.getDate())}_${pad2(now.getHours())}${pad2(now.getMinutes())}${pad2(now.getSeconds())}`;
    return `${safeType}_pool_${stamp}.json`;
  }

  function isGeneratedPoolFileName(name) {
    const text = textValue(name).trim().toLowerCase();
    return /^((api|site)_pool_\d{8}_\d{6}\.json)$/.test(text);
  }

  function normalizeExportInputs(dirValue, nameValue, poolType) {
    const defaultDir = textValue(defaultPoolIoPath).trim();
    let dir = textValue(dirValue).trim();
    let name = textValue(nameValue).trim();
    if (!dir) dir = defaultDir;
    if (dir.toLowerCase().endsWith(".json")) {
      const parts = dir.split(/[\\/]/).filter(Boolean);
      const baseName = parts.length ? parts[parts.length - 1] : "";
      if (!name && baseName) {
        name = baseName;
      }
      const cut = Math.max(dir.lastIndexOf("/"), dir.lastIndexOf("\\"));
      dir = cut >= 0 ? dir.slice(0, cut) : defaultDir;
      if (!dir) dir = defaultDir;
    }
    if (name.includes("/") || name.includes("\\")) {
      const parts = name.split(/[\\/]/).filter(Boolean);
      name = parts.length ? parts[parts.length - 1] : "";
    }
    if (!name) {
      name = buildDefaultExportFileName(poolType);
    } else {
      const lowerName = name.toLowerCase();
      const expectedPrefix = poolType === "api" ? "api_pool_" : "site_pool_";
      const hasPoolPrefix = lowerName.startsWith("api_pool_") || lowerName.startsWith("site_pool_");
      if (hasPoolPrefix && isGeneratedPoolFileName(name) && !lowerName.startsWith(expectedPrefix)) {
        name = buildDefaultExportFileName(poolType);
      }
    }
    if (!name.toLowerCase().endsWith(".json")) {
      name = `${name}.json`;
    }
    return { dir, name };
  }

  async function importPoolDefaultFile(poolType, fileName) {
    return await req(`/api/pool/import/${encodeURIComponent(poolType)}/path`, {
      method: "POST",
      body: JSON.stringify({ name: fileName || "" }),
    });
  }

  async function deletePoolDefaultFiles(names) {
    return await req("/api/pool/files/delete", {
      method: "POST",
      body: JSON.stringify({ names: Array.isArray(names) ? names : [] }),
    });
  }

  async function importPoolUploadedFile(poolType, file) {
    return await uploadReq(`/api/pool/import/${encodeURIComponent(poolType)}`, file);
  }

  async function onConfirmClick(btn) {
    await withButtonLoading(btn, async () => {
      const poolLabel = poolIoState.poolType === "api" ? t("api_pool") : t("site_pool");
      if (poolIoState.mode === "export") {
        const pathInput = document.getElementById("poolIoExportPath");
        const nameInput = document.getElementById("poolIoExportName");
        const targetPath = joinExportTargetPath(
          textValue(pathInput && pathInput.value).trim(),
          textValue(nameInput && nameInput.value).trim()
        );
        const visibleItems = poolIoState.poolType === "api"
          ? getDisplayedApiRows()
          : getDisplayedSiteRows();
        const result = await exportPoolToPath(poolIoState.poolType, targetPath, visibleItems);
        closeModal();
        showNoticeModal(
          t("pool_export_success", {
            pool: poolLabel,
            path: textValue(result && result.path),
          }),
          "success"
        );
        return;
      }
      const selectedRows = poolIoFileRows.filter((item) =>
        poolIoSelectedFileIds.has(textValue(item?.id).trim())
      );
      if (!selectedRows.length) {
        showNoticeModal(t("import_select_file_required"));
        return;
      }
      poolIoImporting = true;
      let finished = 0;
      const totals = { success: 0, skipped: 0, failed: 0 };
      updateImportProgress(finished, selectedRows.length);
      for (const row of selectedRows) {
        try {
          let result = {};
          if (row.source === "default") {
            result = await importPoolDefaultFile(poolIoState.poolType, textValue(row.fileName));
          } else if (row.source === "external" && row.file) {
            result = await importPoolUploadedFile(poolIoState.poolType, row.file);
          }
          totals.success += Number(result.imported || 0);
          totals.skipped += Number(result.skipped || 0);
          totals.failed += Number(result.failed || 0);
        } catch {
          totals.failed += 1;
        } finally {
          finished += 1;
          updateImportProgress(finished, selectedRows.length);
        }
      }
      poolIoImporting = false;
      updateImportProgress(finished, selectedRows.length, totals);
      await loadPool({ includeLocalData: false });
      showNoticeModal(
        t("pool_import_result_summary", {
          pool: poolLabel,
          success: totals.success,
          skipped: totals.skipped,
          failed: totals.failed,
        }),
        "success"
      );
    });
  }

  async function onDeleteClick(btn) {
    if (poolIoState.mode !== "import") return;
    await withButtonLoading(btn, async () => {
      const selectedRows = poolIoFileRows.filter((item) =>
        poolIoSelectedFileIds.has(textValue(item?.id).trim())
      );
      const defaultRows = selectedRows.filter((item) => item && item.source === "default");
      const names = defaultRows.map((item) => textValue(item.fileName).trim()).filter(Boolean);
      if (!names.length) {
        showNoticeModal(t("import_delete_select_required"));
        return;
      }
      const result = await deletePoolDefaultFiles(names);
      const deleted = Array.isArray(result.deleted) ? result.deleted : [];
      const failed = Array.isArray(result.failed) ? result.failed : [];
      defaultPoolIoFiles = await listDefaultFiles();
      refreshRows();
      showNoticeModal(
        t("pool_delete_result_summary", {
          deleted: deleted.length,
          failed: failed.length,
        }),
        failed.length ? "" : "success"
      );
    });
  }

  function setDefaultPath(path) {
    const normalized = textValue(path).trim();
    if (normalized) {
      defaultPoolIoPath = normalized;
    }
  }

  return {
    closeMenus,
    toggleMenu,
    closeModal,
    openModal,
    onPickDirClick,
    onDirChange,
    onDefaultFileToggle,
    onConfirmClick,
    onDeleteClick,
    setDefaultPath,
  };
}
