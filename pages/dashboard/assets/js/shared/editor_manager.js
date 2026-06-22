function createEditorManager(deps) {
  const {
    t,
    req,
    getBridge,
    withButtonLoading,
    textValue,
    normalizeList,
    stringToLineList,
    mapToPairs,
    renderPairRows,
    renderListRows,
    pairsToMap,
    readListRows,
    refreshEditorI18n,
    bindEditorAddTriggers,
    loadPool,
    showNoticeModal,
    testEditorPayloadAndRender,
    getSites,
    setSites,
    renderSites,
    getApis,
    setApis,
    renderApis,
    setEditorState,
    getEditorState,
    getSiteTemplate,
    getApiTemplate,
  } = deps;

  const editorTemplates = { site: "", api: "" };

  async function loadEditorTemplate(kind) {
    if (editorTemplates[kind]) {
      return editorTemplates[kind];
    }
    const endpoint =
      kind === "site" ? "page/editor/site-form" : "page/editor/api-form";
    const html = await getBridge().apiGet(endpoint);
    if (typeof html !== "string" || !html.trim()) {
      throw new Error(`failed to load ${kind} form template`);
    }
    editorTemplates[kind] = html;
    return html;
  }

  function fillSiteForm(data) {
    const siteName = document.getElementById("siteName");
    const siteUrl = document.getElementById("siteUrl");
    const siteTimeout = document.getElementById("siteTimeout");
    if (siteName) siteName.value = textValue(data.name);
    if (siteUrl) siteUrl.value = textValue(data.url);
    if (siteTimeout) siteTimeout.value = String(Number(data.timeout || 60));
    renderPairRows("siteHeaders", mapToPairs(data.headers));
    renderPairRows("siteKeys", mapToPairs(data.keys));
  }

  function fillApiForm(data) {
    const apiName = document.getElementById("apiName");
    const apiUrl = document.getElementById("apiUrl");
    const apiType = document.getElementById("apiType");
    if (apiName) apiName.value = textValue(data.name);
    if (apiUrl) apiUrl.value = textValue(data.url);
    if (apiType) apiType.value = textValue(data.type || "text");
    renderListRows("apiParseList", stringToLineList(data.parse));
    renderListRows("apiScopeList", normalizeList(data.scope));
    renderListRows("apiKeywordsList", normalizeList(data.keywords));
    renderPairRows("apiParams", mapToPairs(data.params));
  }

  function parsePositiveInt(value) {
    const parsed = Number.parseInt(String(value), 10);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      throw new Error(t("timeout_invalid"));
    }
    return parsed;
  }

  function buildSitePayload() {
    const name = textValue(document.getElementById("siteName")?.value).trim();
    const url = textValue(document.getElementById("siteUrl")?.value).trim();
    if (!name) throw new Error(t("required_field", { field: t("name") }));
    if (!url) throw new Error(t("required_field", { field: t("url") }));
    return {
      name,
      url,
      timeout: parsePositiveInt(document.getElementById("siteTimeout")?.value),
      headers: pairsToMap("siteHeaders"),
      keys: pairsToMap("siteKeys"),
    };
  }

  function buildApiPayload() {
    const name = textValue(document.getElementById("apiName")?.value).trim();
    const url = textValue(document.getElementById("apiUrl")?.value).trim();
    if (!name) throw new Error(t("required_field", { field: t("name") }));
    if (!url) throw new Error(t("required_field", { field: t("url") }));
    return {
      name,
      url,
      type: textValue(document.getElementById("apiType")?.value).trim() || "text",
      params: pairsToMap("apiParams"),
      parse: readListRows("apiParseList").join("\n"),
      scope: readListRows("apiScopeList"),
      keywords: readListRows("apiKeywordsList"),
    };
  }

  async function openEditor(kind, data = null) {
    try {
      setEditorState({ kind, originalName: data?.name || "" });
      const action = data ? t("edit") : t("add");
      const target = kind === "site" ? t("site_upper") : t("api_upper");
      const source = data || (kind === "site" ? getSiteTemplate() : getApiTemplate());
      document.getElementById("editorTitle").textContent = t("editor_title", {
        action,
        target,
      });
      const form = document.getElementById("editorForm");
      form.innerHTML = await loadEditorTemplate(kind);
      bindEditorAddTriggers(form);
      if (kind === "site") {
        fillSiteForm(source);
      } else {
        fillApiForm(source);
      }
      const testBtn = document.getElementById("btnTestEditor");
      if (testBtn) {
        testBtn.style.display = kind === "api" ? "inline-flex" : "none";
      }
      refreshEditorI18n();
      document.getElementById("editorModal").classList.add("open");
    } catch (err) {
      showNoticeModal(err.message || String(err));
    }
  }

  function closeEditor() {
    document.getElementById("editorModal").classList.remove("open");
  }

  async function saveEditor() {
    try {
      const st = getEditorState();
      const kind = st.kind;
      const oldName = st.originalName;
      const payload = kind === "site" ? buildSitePayload() : buildApiPayload();
      if (!oldName && payload.enabled === undefined) {
        payload.enabled = true;
      }
      let saved = null;
      if (kind === "site") {
        if (oldName) {
          const result = await req("/api/site/batch", {
            method: "PUT",
            body: JSON.stringify({
              items: [{ name: oldName, payload }],
            }),
          });
          saved = Array.isArray(result?.items) ? result.items[0] : null;
        } else {
          const result = await req("/api/site/batch", {
            method: "POST",
            body: JSON.stringify({ items: [payload] }),
          });
          saved = Array.isArray(result?.items) ? result.items[0] : null;
        }
      } else if (kind === "api") {
        if (oldName) {
          const result = await req("/api/api/batch", {
            method: "PUT",
            body: JSON.stringify({
              items: [{ name: oldName, payload }],
            }),
          });
          saved = Array.isArray(result?.items) ? result.items[0] : null;
        } else {
          const result = await req("/api/api/batch", {
            method: "POST",
            body: JSON.stringify({ items: [payload] }),
          });
          saved = Array.isArray(result?.items) ? result.items[0] : null;
        }
      }

      if (kind === "site" && saved) {
        const prev = Array.isArray(getSites()) ? getSites() : [];
        const index = oldName
          ? prev.findIndex((item) => textValue(item?.name) === oldName)
          : -1;
        const next = [...prev];
        if (index >= 0) {
          next[index] = { ...next[index], ...saved };
        } else {
          next.push(saved);
        }
        setSites(next);
        renderSites();
      } else if (kind === "api" && saved) {
        const prev = Array.isArray(getApis()) ? getApis() : [];
        const index = oldName
          ? prev.findIndex((item) => textValue(item?.name) === oldName)
          : -1;
        const next = [...prev];
        if (index >= 0) {
          next[index] = { ...next[index], ...saved };
        } else {
          next.push(saved);
        }
        setApis(next);
        renderApis();
      }

      closeEditor();
      void loadPool({ includeLocalData: false, silent: true });
    } catch (err) {
      showNoticeModal(err.message || String(err));
    }
  }

  async function testEditorApi(btn) {
    await withButtonLoading(btn, async () => {
      const payload = buildApiPayload();
      await testEditorPayloadAndRender(payload);
    });
  }

  return {
    loadEditorTemplate,
    fillSiteForm,
    fillApiForm,
    parsePositiveInt,
    buildSitePayload,
    buildApiPayload,
    openEditor,
    closeEditor,
    saveEditor,
    testEditorApi,
  };
}
