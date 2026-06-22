function createUiStateManager(deps) {
  const {
    textValue,
    siteSortRules,
    apiSortRules,
    localSortRules,
    getSortState,
    setSortState,
    getSitePage,
    setSitePage,
    getApiPage,
    setApiPage,
    getLocalPage,
    setLocalPage,
    getSiteSearchText,
    setSiteSearchText,
    getApiSearchText,
    setApiSearchText,
    getLocalSearchText,
    setLocalSearchText,
    getSitePageSize,
    setSitePageSize,
    getApiPageSize,
    setApiPageSize,
    getLocalPageSize,
    setLocalPageSize,
    setMainTab,
    getMainTab,
    loadPool,
    loadLocalData,
    refreshPoolView,
  } = deps;

  const rerenderPoolView =
    typeof refreshPoolView === "function"
      ? refreshPoolView
      : () => {
          void loadPool;
        };

  function persistPageState() {
    SafeStorage.set("api_aggregator_page_site", String(getSitePage()));
    SafeStorage.set("api_aggregator_page_api", String(getApiPage()));
    SafeStorage.set("api_aggregator_page_local", String(getLocalPage()));
  }

  function persistSortState() {
    SafeStorage.set("api_aggregator_sort", JSON.stringify(getSortState()));
  }

  function onSiteSortChange(rule) {
    setSortState({ ...getSortState(), site: rule || "name_asc" });
    setSitePage(1);
    persistPageState();
    persistSortState();
    rerenderPoolView();
  }

  function onApiSortChange(rule) {
    setSortState({ ...getSortState(), api: rule || "name_asc" });
    setApiPage(1);
    persistPageState();
    persistSortState();
    rerenderPoolView();
  }

  function onLocalSortChange(rule) {
    setSortState({ ...getSortState(), local: rule || "name_asc" });
    setLocalPage(1);
    persistPageState();
    persistSortState();
    loadLocalData();
  }

  function onSiteHeaderSort(field) {
    const rules = siteSortRules[field];
    if (!rules || !rules.length) return;
    const idx = rules.indexOf(getSortState().site);
    const next = idx < 0 ? rules[0] : rules[(idx + 1) % rules.length];
    onSiteSortChange(next);
  }

  function onApiHeaderSort(field) {
    const rules = apiSortRules[field];
    if (!rules || !rules.length) return;
    const idx = rules.indexOf(getSortState().api);
    const next = idx < 0 ? rules[0] : rules[(idx + 1) % rules.length];
    onApiSortChange(next);
  }

  function onLocalHeaderSort(field) {
    const rules = localSortRules[field];
    if (!rules || !rules.length) return;
    const idx = rules.indexOf(getSortState().local);
    const next = idx < 0 ? rules[0] : rules[(idx + 1) % rules.length];
    onLocalSortChange(next);
  }

  function onSiteSearchChange(value) {
    setSiteSearchText(textValue(value).trim());
    setSitePage(1);
    persistPageState();
    rerenderPoolView();
  }

  function onApiSearchChange(value) {
    setApiSearchText(textValue(value).trim());
    setApiPage(1);
    persistPageState();
    rerenderPoolView();
  }

  function onLocalSearchChange(value) {
    setLocalSearchText(textValue(value).trim());
    setLocalPage(1);
    persistPageState();
    loadLocalData();
  }

  function onSitePageChange(page) {
    const nextPage = Number(page || 1);
    if (!Number.isFinite(nextPage) || nextPage < 1) return;
    setSitePage(nextPage);
    persistPageState();
    rerenderPoolView();
  }

  function onApiPageChange(page) {
    const nextPage = Number(page || 1);
    if (!Number.isFinite(nextPage) || nextPage < 1) return;
    setApiPage(nextPage);
    persistPageState();
    rerenderPoolView();
  }

  function onLocalPageChange(page) {
    const nextPage = Number(page || 1);
    if (!Number.isFinite(nextPage) || nextPage < 1) return;
    setLocalPage(nextPage);
    persistPageState();
    loadLocalData();
  }

  function onSitePageSizeChange(value) {
    const raw = String(value || "").toLowerCase();
    if (raw === "all") {
      setSitePageSize("all");
    } else {
      const nextSize = Number.parseInt(raw, 10);
      if (![10, 20, 50, 100].includes(nextSize)) return;
      setSitePageSize(nextSize);
    }
    setSitePage(1);
    persistPageState();
    SafeStorage.set("api_aggregator_page_size_site", String(getSitePageSize()));
    rerenderPoolView();
  }

  function onApiPageSizeChange(value) {
    const raw = String(value || "").toLowerCase();
    if (raw === "all") {
      setApiPageSize("all");
    } else {
      const nextSize = Number.parseInt(raw, 10);
      if (![10, 20, 50, 100].includes(nextSize)) return;
      setApiPageSize(nextSize);
    }
    setApiPage(1);
    persistPageState();
    SafeStorage.set("api_aggregator_page_size_api", String(getApiPageSize()));
    rerenderPoolView();
  }

  function onLocalPageSizeChange(value) {
    const raw = String(value || "").toLowerCase();
    if (raw === "all") {
      setLocalPageSize("all");
    } else {
      const nextSize = Number.parseInt(raw, 10);
      if (![10, 20, 50, 100].includes(nextSize)) return;
      setLocalPageSize(nextSize);
    }
    setLocalPage(1);
    persistPageState();
    SafeStorage.set("api_aggregator_page_size_local", String(getLocalPageSize()));
    loadLocalData();
  }

  function switchMainTab(tab) {
    const next = tab === "site" || tab === "api" || tab === "local" ? tab : "api";
    setMainTab(next);
    SafeStorage.set("api_aggregator_main_tab", getMainTab());

    const panels = {
      site: document.getElementById("panelSite"),
      api: document.getElementById("panelApi"),
      local: document.getElementById("panelLocal"),
    };
    const buttons = {
      site: document.getElementById("tabBtnSite"),
      api: document.getElementById("tabBtnApi"),
      local: document.getElementById("tabBtnLocal"),
    };

    Object.keys(panels).forEach((key) => {
      const active = key === getMainTab();
      panels[key]?.classList.toggle("is-active", active);
      buttons[key]?.classList.toggle("is-active", active);
    });
  }

  return {
    persistSortState,
    onSiteSortChange,
    onApiSortChange,
    onLocalSortChange,
    onSiteHeaderSort,
    onApiHeaderSort,
    onLocalHeaderSort,
    onSiteSearchChange,
    onApiSearchChange,
    onLocalSearchChange,
    onSitePageChange,
    onApiPageChange,
    onLocalPageChange,
    onSitePageSizeChange,
    onApiPageSizeChange,
    onLocalPageSizeChange,
    switchMainTab,
  };
}
