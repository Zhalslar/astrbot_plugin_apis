function createPoolActionsManager(deps) {
  const {
    t,
    req,
    withButtonLoading,
    textValue,
    showNoticeModal,
    loadPool,
    getSites,
    getApis,
    setSites,
    setApis,
    renderSites,
    renderApis,
    testEditorPayloadAndRender,
    togglePendingDelete,
  } = deps;

  function getSiteOwnedApis(siteName) {
    const normalizedName = textValue(siteName).trim();
    if (!normalizedName) return [];
    const site = getSites().find((item) => textValue(item?.name) === normalizedName) || null;
    const siteUrl = textValue(site?.url).trim();
    return getApis().filter((api) => {
      const directSite = textValue(api?.site).trim();
      if (directSite) {
        return directSite === normalizedName;
      }
      const apiUrl = textValue(api?.url).trim();
      return Boolean(siteUrl) && Boolean(apiUrl) && apiUrl.startsWith(siteUrl);
    });
  }


  async function removeSite(_, name) {
    try {
      const decoded = decodeURIComponent(name || "");
      if (!decoded) return;
      const ownedApis = getSiteOwnedApis(decoded);
      const ownedApiNames = ownedApis.map((item) => textValue(item?.name)).filter(Boolean);
      togglePendingDelete("site", {
        name: decoded,
        cascadeApiNames: ownedApiNames,
      });
    } catch (err) {
      showNoticeModal(err.message || String(err));
    }
  }

  async function removeApi(_, name) {
    try {
      const decoded = decodeURIComponent(name || "");
      if (!decoded) return;
      togglePendingDelete("api", { name: decoded });
    } catch (err) {
      showNoticeModal(err.message || String(err));
    }
  }

  async function toggleSiteEnabled(btn, name, nextEnabled) {
    await withButtonLoading(btn, async () => {
      try {
        const decoded = decodeURIComponent(name);
        await req("/api/site/batch", {
          method: "PUT",
          body: JSON.stringify({
            items: [{ name: decoded, payload: { enabled: Boolean(nextEnabled) } }],
          }),
        });
        const nextSites = getSites().map((item) =>
          textValue(item?.name) === decoded
            ? { ...item, enabled: Boolean(nextEnabled) }
            : item
        );
        setSites(nextSites);
        renderSites();
        void loadPool({ includeLocalData: false, silent: true });
      } catch (err) {
        showNoticeModal(err.message || String(err));
      }
    });
  }

  async function toggleApiEnabled(btn, name, nextEnabled) {
    await withButtonLoading(btn, async () => {
      try {
        const decoded = decodeURIComponent(name);
        await req("/api/api/batch", {
          method: "PUT",
          body: JSON.stringify({
            items: [{ name: decoded, payload: { enabled: Boolean(nextEnabled) } }],
          }),
        });
        const nextApis = getApis().map((item) =>
          textValue(item?.name) === decoded
            ? { ...item, enabled: Boolean(nextEnabled) }
            : item
        );
        setApis(nextApis);
        renderApis();
        void loadPool({ includeLocalData: false, silent: true });
      } catch (err) {
        showNoticeModal(err.message || String(err));
      }
    });
  }

  async function testSingleApi(btn, name) {
    if (btn && btn.dataset.loading === "1") return;
    const originalText = btn ? textValue(btn.textContent) : "";
    const originalTitle = btn ? textValue(btn.title) : "";
    try {
      if (btn) {
        btn.dataset.loading = "1";
        btn.disabled = true;
        btn.classList.add("is-loading");
        btn.textContent = originalText || t("test");
        btn.title = t("test_running");
      }
      const decoded = decodeURIComponent(name);
      const payload = getApis().find((api) => textValue(api?.name) === decoded);
      if (!payload) {
        throw new Error(t("api_not_found"));
      }
      await testEditorPayloadAndRender(payload, { deferModalUntilDone: true });
      await loadPool({ includeLocalData: false });
    } catch (err) {
      showNoticeModal(err.message || String(err));
    } finally {
      if (btn) {
        btn.dataset.loading = "0";
        btn.disabled = false;
        btn.classList.remove("is-loading");
        btn.textContent = originalText || t("test");
        btn.title = originalTitle;
      }
    }
  }

  return {
    removeSite,
    removeApi,
    toggleSiteEnabled,
    toggleApiEnabled,
    testSingleApi,
  };
}
