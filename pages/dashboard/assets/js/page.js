if (typeof I18N === "undefined") {
  throw new Error("i18n resource not loaded");
}

let currentLang = PageHelpers.getDefaultLang(I18N);
let currentTheme = PageHelpers.getDefaultTheme();
let sortState = PageHelpers.getDefaultSortState();
let siteSearchText = "";
let apiSearchText = "";
let localSearchText = "";
let apiSiteFilterSelected = new Set();
let apiSiteFilterOptionNames = [];
let apiSiteFilterInitialized = false;
let apiTypeFilterSelected = new Set();
let apiTypeFilterOptionValues = [];
let apiTypeFilterInitialized = false;
let localTypeFilterSelected = new Set();
let localTypeFilterOptionValues = [];
let localTypeFilterInitialized = false;
const PAGE_QUERY_PARAMS = Object.freeze({
  site: "sp",
  api: "ap",
  local: "lp",
});

function readPageFromUrl(paramName, fallback) {
  try {
    const raw = new URLSearchParams(window.location.search).get(paramName);
    const parsed = Number.parseInt(String(raw || ""), 10);
    if (Number.isFinite(parsed) && parsed >= 1) return parsed;
  } catch {}
  return fallback;
}

function getBridge() {
  return window.AstrBotPluginPage || null;
}

async function waitForBridge(timeoutMs = 3000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const bridge = getBridge();
    if (bridge) {
      if (typeof bridge.ready === "function") {
        await bridge.ready();
      }
      return bridge;
    }
    await new Promise((resolve) => {
      window.setTimeout(resolve, 16);
    });
  }
  return null;
}

let sitePage = readPageFromUrl(PAGE_QUERY_PARAMS.site, PageHelpers.getDefaultPage("api_aggregator_page_site"));
let apiPage = readPageFromUrl(PAGE_QUERY_PARAMS.api, PageHelpers.getDefaultPage("api_aggregator_page_api"));
let localPage = readPageFromUrl(PAGE_QUERY_PARAMS.local, PageHelpers.getDefaultPage("api_aggregator_page_local"));
let sitePageSize = PageHelpers.getDefaultPageSize("api_aggregator_page_size_site");
let apiPageSize = PageHelpers.getDefaultPageSize("api_aggregator_page_size_api");
let localPageSize = PageHelpers.getDefaultPageSize("api_aggregator_page_size_local");
let mainTab = PageHelpers.getDefaultMainTab();
let state = { sites: [], apis: [] };
let localCollections = [];
let allSiteNames = [];
const DEFAULT_POOL_FILE_BY_TYPE = Object.freeze({
  site: "site_pool_default.json",
  api: "api_pool_default.json",
});
const poolDefaultAutoImportTried = { site: false, api: false };
let sitePagination = { page: sitePage, page_size: sitePageSize, total: 0, total_pages: 1, start: 0, end: 0 };
let apiPagination = { page: apiPage, page_size: apiPageSize, total: 0, total_pages: 1, start: 0, end: 0 };
let localPagination = { page: localPage, page_size: localPageSize, total: 0, total_pages: 1, start: 0, end: 0 };
let hasPoolLoaded = false;
let editorState = { kind: "", originalName: "" };
let localViewerState = { type: "", name: "", detail: null, pendingDeletes: new Set() };
let activeTestTaskId = "";
const SITE_SORT_RULES = {
  name: ["name_asc", "name_desc"],
  url: ["url_asc", "url_desc"],
  timeout: ["timeout_asc", "timeout_desc"],
  api_count: ["api_count_asc", "api_count_desc"]
};
const API_SORT_RULES = {
  name: ["name_asc", "name_desc"],
  url: ["url_asc", "url_desc"],
  type: ["type_asc", "type_desc"],
  valid: ["valid_first", "invalid_first"],
  keywords: ["keywords_desc", "name_asc"]
};
const LOCAL_SORT_RULES = {
  name: ["name_asc", "name_desc"],
  type: ["type_asc", "type_desc"],
  count: ["count_asc", "count_desc"],
  size: ["size_asc", "size_desc"],
  updated: ["updated_desc", "updated_asc"]
};
const DATA_TYPE_OPTIONS = ["text", "image", "video", "audio"];
const pendingDeleteState = {
  site: new Map(),
  api: new Map(),
  localCollection: new Map(),
};
const PENDING_DELETE_KIND_MAP = Object.freeze({
  site: "site",
  api: "api",
  local_collection: "localCollection",
});

function normalizeDeleteValue(value) {
  return textValue(value).trim();
}

function getPendingDeleteMap(kind) {
  const mapKey = PENDING_DELETE_KIND_MAP[kind];
  return mapKey ? pendingDeleteState[mapKey] : null;
}

function rerenderAfterPendingDeleteChange() {
  refreshPendingDeletePanel();
  renderSites();
  renderApis();
  renderLocalData();
}

function makePendingDeleteKey(kind, payload) {
  if (kind === "site" || kind === "api") {
    return normalizeDeleteValue(payload?.name);
  }
  if (kind === "local_collection") {
    return `${normalizeDeleteValue(payload?.type)}::${normalizeDeleteValue(payload?.name)}`;
  }
  return "";
}

function isPendingDelete(kind, payload) {
  const key = makePendingDeleteKey(kind, payload);
  const map = getPendingDeleteMap(kind);
  return Boolean(key && map && map.has(key));
}

function buildPendingDeleteEntry(kind, key, payload) {
  if (kind === "site") {
    const cascadeApiNames = Array.isArray(payload?.cascadeApiNames)
      ? payload.cascadeApiNames.map((item) => normalizeDeleteValue(item)).filter(Boolean)
      : [];
    return { name: key, cascadeApiNames };
  }
  if (kind === "api") {
    return { name: key };
  }
  if (kind === "local_collection") {
    return {
      type: normalizeDeleteValue(payload?.type),
      name: normalizeDeleteValue(payload?.name),
    };
  }
  return null;
}

function togglePendingDelete(kind, payload) {
  const key = makePendingDeleteKey(kind, payload);
  const map = getPendingDeleteMap(kind);
  if (!key || !map) return;

  if (map.has(key)) {
    map.delete(key);
  } else {
    const entry = buildPendingDeleteEntry(kind, key, payload);
    if (!entry) return;
    map.set(key, entry);
  }

  rerenderAfterPendingDeleteChange();
}

function clearPendingDeleteSelection() {
  pendingDeleteState.site.clear();
  pendingDeleteState.api.clear();
  pendingDeleteState.localCollection.clear();
  rerenderAfterPendingDeleteChange();
}

function getPendingDeleteSnapshot() {
  const sites = Array.from(pendingDeleteState.site.values());
  const directApis = Array.from(pendingDeleteState.api.values()).map((item) => item.name);
  const apiSet = new Set(directApis);
  sites.forEach((site) => {
    (Array.isArray(site.cascadeApiNames) ? site.cascadeApiNames : []).forEach((name) => {
      const normalized = normalizeDeleteValue(name);
      if (normalized) apiSet.add(normalized);
    });
  });
  return {
    sites,
    apis: Array.from(apiSet),
    localTargets: Array.from(pendingDeleteState.localCollection.values()).map((item) => ({
      type: normalizeDeleteValue(item?.type),
      name: normalizeDeleteValue(item?.name),
    })),
    selectedCount: Object.values(pendingDeleteState).reduce((sum, map) => sum + map.size, 0),
  };
}

function refreshPendingDeletePanel() {
  const bar = document.getElementById("deleteConfirmBar");
  const text = document.getElementById("deleteConfirmText");
  const confirmBtn = document.getElementById("btnPendingDeleteConfirm");
  const clearBtn = document.getElementById("btnPendingDeleteClear");
  if (!bar || !text || !confirmBtn || !clearBtn) return;

  const snapshot = getPendingDeleteSnapshot();
  if (snapshot.selectedCount <= 0) {
    bar.classList.remove("open");
    text.textContent = "";
    confirmBtn.textContent = t("confirm_delete");
    clearBtn.textContent = t("cancel");
    return;
  }

  text.textContent = t("confirm_delete_count", { count: snapshot.selectedCount });

  const finalDeleteCount =
    snapshot.sites.length + snapshot.apis.length + snapshot.localTargets.length;
  confirmBtn.textContent = t("confirm_delete_count", { count: finalDeleteCount });
  clearBtn.textContent = t("cancel");
  bar.classList.add("open");
}

function persistPageQueryState() {
  try {
    const url = new URL(window.location.href);
    url.searchParams.set(PAGE_QUERY_PARAMS.site, String(Math.max(1, Number(sitePage || 1))));
    url.searchParams.set(PAGE_QUERY_PARAMS.api, String(Math.max(1, Number(apiPage || 1))));
    url.searchParams.set(PAGE_QUERY_PARAMS.local, String(Math.max(1, Number(localPage || 1))));
    window.history.replaceState(null, "", url.toString());
  } catch {}
}

function getByPath(source, key) {
  if (!source || typeof source !== "object" || !key) {
    return undefined;
  }
  return String(key)
    .split(".")
    .reduce((current, part) => {
      if (!current || typeof current !== "object" || !(part in current)) {
        return undefined;
      }
      return current[part];
    }, source);
}

function formatTemplate(template, vars = {}) {
  return String(template || "").replace(/\{(\w+)\}/g, (_, name) => {
    const value = vars[name];
    return value === undefined || value === null ? "" : String(value);
  });
}

function normalizeLocale(locale) {
  return String(locale || "").toLowerCase().startsWith("zh") ? "zh" : "en";
}

function toHtmlLang(locale) {
  return normalizeLocale(locale) === "zh" ? "zh-CN" : "en-US";
}

function getBridgeMessage(key) {
  const bridge = getBridge();
  if (!bridge || typeof bridge.getI18n !== "function") {
    return "";
  }
  const messages = bridge.getI18n();
  const locale = typeof bridge.getLocale === "function" ? bridge.getLocale() : "";
  const locales = [];
  const pushLocale = (value) => {
    const text = String(value || "").trim();
    if (text && !locales.includes(text)) {
      locales.push(text);
    }
  };
  pushLocale(locale);
  pushLocale(normalizeLocale(locale) === "zh" ? "zh-CN" : "en-US");
  pushLocale("zh-CN");
  pushLocale("en-US");
  const path = `pages.dashboard.ui.${key}`;
  for (const candidate of locales) {
    const value = getByPath(messages?.[candidate], path);
    if (value !== undefined && value !== null && String(value).length > 0) {
      return String(value);
    }
  }
  return "";
}

function t(key, vars = {}) {
  const dict = I18N[currentLang] || I18N.en;
  const fallback = I18N.en[key] || key;
  const template = getBridgeMessage(key) || dict[key] || fallback;
  return formatTemplate(template, vars);
}

function setLanguage(locale) {
  currentLang = normalizeLocale(locale);
  document.documentElement.lang = toHtmlLang(locale);
}

function setTheme(theme) {
  currentTheme = theme === "light" || theme === "dark" ? theme : "";
  if (!currentTheme) return;
  document.documentElement.setAttribute("data-theme", currentTheme);
  document.documentElement.style.colorScheme = currentTheme;
}

function resolveThemeFromContext(context) {
  if (context?.theme === "light" || context?.theme === "dark") {
    return context.theme;
  }
  if (typeof context?.isDark === "boolean") {
    return context.isDark ? "dark" : "light";
  }
  const htmlTheme = String(
    document.documentElement.getAttribute("data-theme") || ""
  ).toLowerCase();
  if (htmlTheme === "light" || htmlTheme === "dark") {
    return htmlTheme;
  }
  return currentTheme;
}

function syncPageContext(context = null, options = {}) {
  const force = Boolean(options.force);
  const nextLocale = context?.locale || getBridge()?.getLocale?.() || currentLang;
  const nextTheme = resolveThemeFromContext(context);
  const langChanged = normalizeLocale(nextLocale) !== currentLang;
  const themeChanged = nextTheme !== currentTheme;
  setLanguage(nextLocale);
  setTheme(nextTheme);
  if (force || langChanged || themeChanged) {
    applyI18n();
    if (hasPoolLoaded) {
      render();
    }
  }
}

function getDisplayedSiteRows() {
  const filteredSites = PageHelpers.filterSites(
    Array.isArray(state.sites) ? state.sites : [],
    siteSearchText
  );
  const sortedSites = sortSites(filteredSites, sortState.site);
  const paged = PageHelpers.paginateItems(sortedSites, sitePage, sitePageSize);
  const pageItems = Array.isArray(paged.pageItems) ? paged.pageItems : [];
  return pageItems.map((item) => ({ ...item }));
}

function getDisplayedApiRows() {
  const searchedApis = PageHelpers.filterApis(
    Array.isArray(state.apis) ? state.apis : [],
    apiSearchText
  );
  const siteFilteredApis = filterApisBySite(searchedApis);
  const typeFilteredApis = filterApisByType(siteFilteredApis);
  const sortedApis = sortApis(typeFilteredApis, sortState.api);
  const paged = PageHelpers.paginateItems(sortedApis, apiPage, apiPageSize);
  const pageItems = Array.isArray(paged.pageItems) ? paged.pageItems : [];
  return pageItems.map((item) => ({ ...item }));
}

function normalizePoolType(poolType) {
  return poolType === "api" ? "api" : "site";
}

function getDefaultPoolFileName(poolType) {
  const safeType = normalizePoolType(poolType);
  return DEFAULT_POOL_FILE_BY_TYPE[safeType];
}

async function listDefaultPoolFileNames() {
  const data = await req("/api/pool/files");
  const files = Array.isArray(data.files) ? data.files : [];
  return new Set(
    files
      .map((item) => textValue(item?.name).trim())
      .filter(Boolean)
  );
}

async function importDefaultPoolFile(poolType, options = {}) {
  const safeType = normalizePoolType(poolType);
  const silent = Boolean(options.silent);
  const defaultFileName = getDefaultPoolFileName(safeType);
  const externalNames = options.fileNames instanceof Set ? options.fileNames : null;
  const fileNames = externalNames || (await listDefaultPoolFileNames());
  if (!fileNames.has(defaultFileName)) {
    if (!silent) {
      showNoticeModal(t("quick_import_default_missing", { file: defaultFileName }));
    }
    return null;
  }
  const result = await req(`/api/pool/import/${encodeURIComponent(safeType)}/path`, {
    method: "POST",
    body: JSON.stringify({ name: defaultFileName }),
  });
  if (!silent) {
    const poolLabel = safeType === "api" ? t("api_pool") : t("site_pool");
    showNoticeModal(
      t("pool_import_result_summary", {
        pool: poolLabel,
        success: Number(result.imported || 0),
        skipped: Number(result.skipped || 0),
        failed: Number(result.failed || 0),
      }),
      "success"
    );
  }
  return result;
}

function buildEmptyPoolHintCell(poolType, colspan) {
  const safeType = normalizePoolType(poolType);
  return `
    <tr>
      <td colspan="${colspan}" class="empty-cell">
        <div class="empty-pool-actions">
          <span>${escapeHtml(t("import_empty_hint"))}</span>
          <button
            type="button"
            class="quick-import-btn"
            onclick='onQuickImportDefaultPoolClick(this, "${safeType}")'
          >${escapeHtml(t("quick_import_default"))}</button>
        </div>
      </td>
    </tr>
  `;
}

function buildNoDataHintCell(colspan) {
  return `
    <tr>
      <td colspan="${colspan}" class="empty-cell">${escapeHtml(t("no_data"))}</td>
    </tr>
  `;
}

async function tryAutoImportDefaultPools() {
  const pendingTypes = [];
  if (!Array.isArray(state.sites) || state.sites.length === 0) {
    if (!poolDefaultAutoImportTried.site) pendingTypes.push("site");
  }
  if (!Array.isArray(state.apis) || state.apis.length === 0) {
    if (!poolDefaultAutoImportTried.api) pendingTypes.push("api");
  }
  if (!pendingTypes.length) return false;

  let fileNames = new Set();
  try {
    fileNames = await listDefaultPoolFileNames();
  } catch {
    pendingTypes.forEach((type) => {
      poolDefaultAutoImportTried[type] = true;
    });
    return false;
  }

  let importedAny = false;
  for (const poolType of pendingTypes) {
    poolDefaultAutoImportTried[poolType] = true;
    try {
      const result = await importDefaultPoolFile(poolType, {
        silent: true,
        fileNames,
      });
      if (Number(result?.imported || 0) > 0) {
        importedAny = true;
      }
    } catch {}
  }
  return importedAny;
}

function applyPoolData(data) {
  const resolvedDefaultPath = textValue(data.pool_io_default_dir).trim();
  if (resolvedDefaultPath) {
    setPoolIoDefaultPath(resolvedDefaultPath);
  }
  state = {
    sites: Array.isArray(data.sites) ? data.sites : [],
    apis: Array.isArray(data.apis) ? data.apis : []
  };
  allSiteNames = Array.from(
    new Set(
      state.sites
        .map((item) => textValue(item?.name).trim())
        .filter(Boolean)
    )
  );
  sitePage = Math.max(1, Number(sitePage || 1));
  apiPage = Math.max(1, Number(apiPage || 1));
  SafeStorage.set("api_aggregator_page_site", String(sitePage));
  SafeStorage.set("api_aggregator_page_api", String(apiPage));
  persistPageQueryState();
}

async function onQuickImportDefaultPoolClick(btn, poolType) {
  await withButtonLoading(btn, async () => {
    const safeType = normalizePoolType(poolType);
    const result = await importDefaultPoolFile(safeType, { silent: false });
    if (result) {
      if (safeType === "api") {
        // Reset API filter state so freshly imported entries are visible immediately.
        apiSiteFilterInitialized = false;
        apiSiteFilterOptionNames = [];
        apiSiteFilterSelected = new Set();
        apiTypeFilterInitialized = false;
        apiTypeFilterOptionValues = [];
        apiTypeFilterSelected = new Set();
        setApiPageToFirst();
      }
      await loadPool({ includeLocalData: false, silent: true });
    }
  });
}

const editorFormManager = createEditorFormManager({ t, textValue, escapeHtml });
const {
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
} = editorFormManager;

const { show: showNoticeModal, close: closeNoticeModal } = createNoticeManager({
  t,
  textValue,
});
let testManager = null;
const runningTasksManager = createRunningTasksManager({
  t,
  escapeHtml,
  getActiveTestTaskId: () => activeTestTaskId,
  onViewTaskClick: (taskId) => testManager?.onViewTaskClick(taskId),
});
const {
  updateTestStats,
  createRunningTask,
  getRunningTask,
  patchRunningTask,
  finishRunningTask,
  renderRunningTasks,
  onToggleRunningTasksPanel,
} = runningTasksManager;
testManager = createTestManager({
  t,
  textValue,
  escapeHtml,
  normalizeList,
  setActiveTestTaskId: (taskId) => {
    activeTestTaskId = taskId;
  },
  getRunningTask,
  updateTestStats,
  createRunningTask,
  patchRunningTask,
  finishRunningTask,
  getApis: () => state.apis,
  setApis: (apis) => {
    state.apis = apis;
  },
  renderApis,
  loadPool,
  withButtonLoading,
  req,
  subscribeReq,
  unsubscribeReq,
  showNoticeModal,
  getBatchTestNames: () => getDisplayedApiNames(),
  getBatchTestRange: () => {
    const query = textValue(apiSearchText).trim();
    const selectedNames = Array.from(apiSiteFilterSelected).filter((name) =>
      textValue(name).trim()
    );
    const totalOptions = Array.isArray(apiSiteFilterOptionNames)
      ? apiSiteFilterOptionNames.length
      : 0;
    const useSiteFilter =
      totalOptions > 0 && selectedNames.length > 0 && selectedNames.length < totalOptions;
    return {
      query,
      site_names: useSiteFilter ? selectedNames : [],
    };
  },
});
const {
  refreshSingleRepeatButtonLabel,
  onToggleSingleRepeatPauseClick,
  onToggleSingleTestParamSheetClick,
  onToggleBatchPauseClick,
  onStopBatchTestClick,
  testEditorPayloadAndRender,
  closeTestModal,
  onViewTaskClick,
  testApisStream: streamApiTests,
  onToggleSingleRepeatClick: runToggleSingleRepeat,
} = testManager;
const editorManager = createEditorManager({
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
  getSites: () => state.sites,
  setSites: (sites) => {
    state.sites = Array.isArray(sites) ? sites : [];
  },
  renderSites,
  getApis: () => state.apis,
  setApis: (apis) => {
    state.apis = Array.isArray(apis) ? apis : [];
  },
  renderApis,
  setEditorState: (nextState) => {
    editorState = { ...editorState, ...nextState };
  },
  getEditorState: () => editorState,
  getSiteTemplate: siteTemplate,
  getApiTemplate: apiTemplate,
});
const {
  openEditor,
  closeEditor,
  saveEditor,
  testEditorApi,
} = editorManager;
const localDataManager = createLocalDataManager({
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
  getLocalCollections: () => localCollections,
  setLocalCollections: (collections) => {
    localCollections = Array.isArray(collections) ? collections : [];
  },
  getLocalPagination: () => localPagination,
  setLocalPagination: (meta) => {
    localPagination = {
      page: Math.max(1, Number(meta?.page || localPage || 1)),
      page_size: meta?.page_size ?? localPageSize,
      total: Math.max(0, Number(meta?.total || 0)),
      total_pages: Math.max(1, Number(meta?.total_pages || 1)),
      start: Math.max(0, Number(meta?.start || 0)),
      end: Math.max(0, Number(meta?.end || 0)),
    };
  },
  getLocalSearchText: () => localSearchText,
  getLocalPage: () => localPage,
  setLocalPage: (page) => {
    localPage = page;
    persistPageQueryState();
  },
  getLocalPageSize: () => localPageSize,
  getSortState: () => sortState,
  localSortRules: LOCAL_SORT_RULES,
  getLocalTypeFilterValues: () => {
    const selected = Array.from(localTypeFilterSelected).filter((value) =>
      textValue(value).trim()
    );
    const total = Array.isArray(localTypeFilterOptionValues)
      ? localTypeFilterOptionValues.length
      : 0;
    if (total <= 0 || selected.length >= total) {
      return [];
    }
    return selected;
  },
  getLocalViewerState: () => localViewerState,
  setLocalViewerState: (nextState) => {
    localViewerState = nextState || { type: "", name: "", detail: null, pendingDeletes: new Set() };
  },
  isPendingDelete,
  togglePendingDelete,
});
const {
  closeLocalDataModal,
  updateLocalDeleteConfirmButton,
  tuneLocalDataModalLayout,
  renderLocalDataItems,
  loadLocalData,
  onRefreshLocalDataClick,
  openLocalDataViewer,
  removeLocalCollection,
  removeLocalItem,
  onConfirmLocalDataDeleteClick,
} = localDataManager;
const poolActionsManager = createPoolActionsManager({
  t,
  req,
  withButtonLoading,
  textValue,
  showNoticeModal,
  loadPool,
  getSites: () => state.sites,
  getApis: () => state.apis,
  setSites: (sites) => {
    state.sites = Array.isArray(sites) ? sites : [];
  },
  setApis: (apis) => {
    state.apis = Array.isArray(apis) ? apis : [];
  },
  renderSites,
  renderApis,
  testEditorPayloadAndRender,
  togglePendingDelete,
});
const {
  removeSite,
  removeApi,
  toggleSiteEnabled,
  toggleApiEnabled,
  testSingleApi,
} = poolActionsManager;
const uiStateManager = createUiStateManager({
  textValue,
  siteSortRules: SITE_SORT_RULES,
  apiSortRules: API_SORT_RULES,
  localSortRules: LOCAL_SORT_RULES,
  getSortState: () => sortState,
  setSortState: (nextState) => {
    sortState = nextState;
  },
  getSitePage: () => sitePage,
  setSitePage: (page) => {
    sitePage = page;
    persistPageQueryState();
  },
  getApiPage: () => apiPage,
  setApiPage: (page) => {
    apiPage = page;
    persistPageQueryState();
  },
  getLocalPage: () => localPage,
  setLocalPage: (page) => {
    localPage = page;
    persistPageQueryState();
  },
  getSiteSearchText: () => siteSearchText,
  setSiteSearchText: (text) => {
    siteSearchText = text;
  },
  getApiSearchText: () => apiSearchText,
  setApiSearchText: (text) => {
    apiSearchText = text;
  },
  getLocalSearchText: () => localSearchText,
  setLocalSearchText: (text) => {
    localSearchText = text;
  },
  getSitePageSize: () => sitePageSize,
  setSitePageSize: (size) => {
    sitePageSize = size;
  },
  getApiPageSize: () => apiPageSize,
  setApiPageSize: (size) => {
    apiPageSize = size;
  },
  getLocalPageSize: () => localPageSize,
  setLocalPageSize: (size) => {
    localPageSize = size;
  },
  getMainTab: () => mainTab,
  setMainTab: (tab) => {
    mainTab = tab;
  },
  loadPool,
  loadLocalData,
  refreshPoolView: () => {
    renderSites();
    renderApis();
  },
});
const {
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
} = uiStateManager;
const poolIoManager = createPoolIoManager({
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
});
const {
  closeMenus: closePoolIoMenus,
  toggleMenu: togglePoolIoMenu,
  closeModal: closePoolIoModal,
  openModal: openPoolIoModal,
  onPickDirClick: onPoolIoPickDirClick,
  onDirChange: onPoolIoDirChange,
  onDefaultFileToggle: onPoolDefaultFileToggle,
  onConfirmClick: onPoolIoConfirmClick,
  onDeleteClick: onPoolIoDeleteClick,
  setDefaultPath: setPoolIoDefaultPath,
} = poolIoManager;

function applyI18n() {
  const setNodeText = (id, text) => {
    const node = document.getElementById(id);
    if (node) {
      node.textContent = text;
    }
  };

  document.title =
    getBridge()?.getContext?.()?.pageTitle || t("page_title");
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.getAttribute("data-i18n");
    if (key) {
      node.textContent = t(key);
    }
  });
  setNodeText("btnTestAll", t("test_all_apis"));
  const siteSearch = document.getElementById("siteSearch");
  if (siteSearch) {
    siteSearch.placeholder = t("site_search_placeholder");
  }
  const apiSearch = document.getElementById("apiSearch");
  if (apiSearch) {
    apiSearch.placeholder = t("api_search_placeholder");
  }
  const apiSiteFilterToggleAllText = document.querySelector(
    "#apiSiteFilterDropdown [data-i18n='all_sites']"
  );
  if (apiSiteFilterToggleAllText) {
    apiSiteFilterToggleAllText.textContent = t("all_sites");
  }
  const apiTypeFilterToggleAllText = document.querySelector(
    "#apiTypeFilterDropdown [data-i18n='all_types']"
  );
  if (apiTypeFilterToggleAllText) {
    apiTypeFilterToggleAllText.textContent = t("all_types");
  }
  const localSearch = document.getElementById("localSearch");
  if (localSearch) {
    localSearch.placeholder = t("local_search_placeholder");
  }
  const localTypeFilterToggleAllText = document.querySelector(
    "#localTypeFilterDropdown [data-i18n='all_types']"
  );
  if (localTypeFilterToggleAllText) {
    localTypeFilterToggleAllText.textContent = t("all_types");
  }
  const sitePageSizePicker = document.getElementById("sitePageSize");
  if (sitePageSizePicker) {
    sitePageSizePicker.value = String(sitePageSize);
  }
  const apiPageSizePicker = document.getElementById("apiPageSize");
  if (apiPageSizePicker) {
    apiPageSizePicker.value = String(apiPageSize);
  }
  const localPageSizePicker = document.getElementById("localPageSize");
  if (localPageSizePicker) {
    localPageSizePicker.value = String(localPageSize);
  }
  setNodeText("btnAddSite", t("add_site"));
  setNodeText("btnAddApi", t("add_api"));
  const sitePoolIoMenuBtn = document.getElementById("sitePoolIoMenuBtn");
  if (sitePoolIoMenuBtn) {
    const label = t("import_export");
    sitePoolIoMenuBtn.title = label;
    sitePoolIoMenuBtn.setAttribute("aria-label", label);
  }
  const apiPoolIoMenuBtn = document.getElementById("apiPoolIoMenuBtn");
  if (apiPoolIoMenuBtn) {
    const label = t("import_export");
    apiPoolIoMenuBtn.title = label;
    apiPoolIoMenuBtn.setAttribute("aria-label", label);
  }
  const poolIoModalTitle = document.getElementById("poolIoModalTitle");
  if (poolIoModalTitle && !document.getElementById("poolIoModal")?.classList.contains("open")) {
    poolIoModalTitle.textContent = t("pool_file_modal_title", { pool: t("site_pool") });
  }
  const poolIoExportCount = document.getElementById("poolIoExportCount");
  if (poolIoExportCount && !document.getElementById("poolIoModal")?.classList.contains("open")) {
    poolIoExportCount.style.display = "none";
    poolIoExportCount.textContent = "";
  }
  const btnPoolIoConfirm = document.getElementById("btnPoolIoConfirm");
  if (btnPoolIoConfirm && !document.getElementById("poolIoModal")?.classList.contains("open")) {
    btnPoolIoConfirm.textContent = t("export_file");
  }
  const btnPoolIoCancel = document.getElementById("btnPoolIoCancel");
  if (btnPoolIoCancel) {
    btnPoolIoCancel.textContent = t("cancel");
  }
  const poolIoExportPath = document.getElementById("poolIoExportPath");
  if (poolIoExportPath) {
    poolIoExportPath.placeholder = t("export_path_placeholder");
  }
  const poolIoExportName = document.getElementById("poolIoExportName");
  if (poolIoExportName) {
    poolIoExportName.placeholder = t("export_name_placeholder");
  }
  const btnPoolIoPickDir = document.getElementById("btnPoolIoPickDir");
  if (btnPoolIoPickDir) {
    btnPoolIoPickDir.textContent = t("import_pick_other_dir");
  }
  const btnPoolIoDelete = document.getElementById("btnPoolIoDelete");
  if (btnPoolIoDelete) {
    btnPoolIoDelete.textContent = t("delete_file");
  }
  setNodeText("btnTestEditor", t("test_params"));
  setNodeText("btnSave", t("save"));
  setNodeText("btnCancel", t("cancel"));
  setNodeText("btnCloseTestModal", t("close"));
  setNodeText("btnCloseLocalDataModal", t("close"));
  setNodeText("btnRefreshLocalData", t("refresh"));
  setNodeText("btnUpdateConfirm", t("update_confirm_button"));
  setNodeText("btnUpdateCancel", t("cancel"));
  setNodeText("btnUpdateClose", t("close"));
  const tabSiteLabel = document.getElementById("tabBtnSiteLabel");
  if (tabSiteLabel) tabSiteLabel.textContent = t("site_pool");
  const tabApiLabel = document.getElementById("tabBtnApiLabel");
  if (tabApiLabel) tabApiLabel.textContent = t("api_pool");
  const tabLocalLabel = document.getElementById("tabBtnLocalLabel");
  if (tabLocalLabel) tabLocalLabel.textContent = t("local_data_pool");
  setNodeText("testModalTitle", t("test_all_title"));
  setNodeText("editorHint", t("json_object"));
  setNodeText("localDataModalTitle", t("local_data_detail_title"));
  const statsTask = activeTestTaskId ? getRunningTask(activeTestTaskId) : null;
  updateTestStats(statsTask);
  renderRunningTasks();
  refreshSingleRepeatButtonLabel();
  updateLocalDeleteConfirmButton();
  refreshPendingDeletePanel();
  refreshEditorI18n();
  updateApiSiteFilterButtonLabel();
  updateApiTypeFilterButtonLabel();
  updateLocalTypeFilterButtonLabel();
  renderLocalData();
}

function boolText(value) {
  return value ? t("true_text") : t("false_text");
}

function formatItems(count) {
  return t("items_count", { count });
}

function getTypeOptionLabel(type) {
  const normalized = textValue(type).trim().toLowerCase();
  if (!normalized) return "";
  const key = `data_type_${normalized}`;
  const value = t(key);
  return value === key ? normalized : value;
}

function getFieldValue(id) {
  const node = document.getElementById(id);
  if (!node) return "";
  if (node.type === "checkbox") return Boolean(node.checked);
  return node.value || "";
}

function refreshEditorI18n() {
  const form = document.getElementById("editorForm");
  if (!form || !form.children.length) return;
  form.querySelectorAll("[data-editor-i18n]").forEach((node) => {
    const key = node.getAttribute("data-editor-i18n");
    if (key) {
      node.textContent = t(key);
    }
  });
  form.querySelectorAll("[data-editor-i18n-placeholder]").forEach((node) => {
    const key = node.getAttribute("data-editor-i18n-placeholder");
    if (key) {
      node.placeholder = t(key);
    }
  });
  form.querySelectorAll("[data-kv-role='key']").forEach((node) => {
    node.placeholder = t("key_name");
  });
  form.querySelectorAll("[data-kv-role='value']").forEach((node) => {
    node.placeholder = t("value_name");
  });
  form.querySelectorAll("[data-list]").forEach((node) => {
    node.placeholder = t("value_name");
  });
  const apiType = form.querySelector("#apiType");
  if (apiType) {
    Array.from(apiType.options || []).forEach((option) => {
      const value = textValue(option?.value).trim().toLowerCase();
      option.textContent = getTypeOptionLabel(value) || value;
    });
  }
}

function bindEditorAddTriggers(form) {
  if (!form) return;
  form.querySelectorAll("[data-add-action][data-add-target]").forEach((node) => {
    node.classList.add("field-add-trigger");
    const triggerAdd = () => {
      const action = textValue(node.getAttribute("data-add-action")).trim().toLowerCase();
      const target = textValue(node.getAttribute("data-add-target")).trim();
      if (!target) return;
      if (action === "pair") {
        addPairRow(target);
        return;
      }
      addListRow(target);
    };
    node.addEventListener("click", triggerAdd);
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        triggerAdd();
      }
    });
  });
}

function closeDropdown(dropdownId) {
  const dropdown = document.getElementById(dropdownId);
  if (dropdown) {
    dropdown.classList.remove("open");
  }
}

function toggleDropdown(event, dropdownId) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  const dropdown = document.getElementById(dropdownId);
  if (!dropdown) return;
  const shouldOpen = !dropdown.classList.contains("open");
  dropdown.classList.toggle("open", shouldOpen);
}

function setApiPageToFirst() {
  apiPage = 1;
  SafeStorage.set("api_aggregator_page_api", String(apiPage));
  persistPageQueryState();
}

function resetApiPageAndRender() {
  setApiPageToFirst();
  renderApis();
}

function resetLocalPageAndReload() {
  localPage = 1;
  persistPageQueryState();
  void loadLocalData();
}

function closeApiSiteFilterDropdown() {
  closeDropdown("apiSiteFilterDropdown");
}

function toggleApiSiteFilterDropdown(event) {
  toggleDropdown(event, "apiSiteFilterDropdown");
}

function getApiSiteFilterNames() {
  return (Array.isArray(allSiteNames) ? allSiteNames : [])
    .map((name) => textValue(name).trim())
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b, currentLang === "zh" ? "zh-CN" : "en"));
}

function syncApiSiteFilterSelection(nextOptionNames) {
  const optionNames = Array.isArray(nextOptionNames) ? nextOptionNames : [];
  const optionSet = new Set(optionNames);
  const wasAllSelected =
    apiSiteFilterInitialized &&
    apiSiteFilterOptionNames.length > 0 &&
    apiSiteFilterSelected.size === apiSiteFilterOptionNames.length;

  if (!apiSiteFilterInitialized) {
    apiSiteFilterSelected = new Set(optionNames);
    apiSiteFilterInitialized = true;
    apiSiteFilterOptionNames = optionNames;
    return;
  }

  const nextSelected = new Set(
    Array.from(apiSiteFilterSelected).filter((name) => optionSet.has(name))
  );
  if (wasAllSelected) {
    optionNames.forEach((name) => nextSelected.add(name));
  }
  apiSiteFilterSelected = nextSelected;
  apiSiteFilterOptionNames = optionNames;
}

function updateApiSiteFilterButtonLabel() {
  const btn = document.getElementById("apiSiteFilterBtn");
  if (!btn) return;
  const total = apiSiteFilterOptionNames.length;
  const selected = apiSiteFilterSelected.size;
  const label = t("api_site_filter");
  if (!total) {
    btn.textContent = `${label} (0/0)`;
    return;
  }
  btn.textContent = `${label} (${selected}/${total})`;
}

function renderCheckboxFilter({
  optionsWrapId,
  toggleAllId,
  optionValues,
  selectedSet,
  getOptionLabel,
  onOptionChange,
  onAfterRender,
}) {
  const optionsWrap = document.getElementById(optionsWrapId);
  const toggleAll = document.getElementById(toggleAllId);
  if (!optionsWrap || !toggleAll) return;

  const values = Array.isArray(optionValues) ? optionValues : [];
  const safeSelectedSet = selectedSet instanceof Set ? selectedSet : new Set();
  const toLabel = typeof getOptionLabel === "function" ? getOptionLabel : (value) => value;
  const onChange = typeof onOptionChange === "function" ? onOptionChange : () => {};

  optionsWrap.innerHTML = "";
  values.forEach((value) => {
    const row = document.createElement("label");
    row.className = "site-filter-option";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = safeSelectedSet.has(value);
    input.addEventListener("change", () => {
      onChange(value, input.checked);
    });
    const text = document.createElement("span");
    text.textContent = textValue(toLabel(value));
    row.appendChild(input);
    row.appendChild(text);
    optionsWrap.appendChild(row);
  });

  const selected = safeSelectedSet.size;
  const total = values.length;
  toggleAll.checked = total > 0 && selected === total;
  toggleAll.indeterminate = selected > 0 && selected < total;
  if (typeof onAfterRender === "function") {
    onAfterRender({ selected, total });
  }
}

function renderApiSiteFilter() {
  const optionNames = getApiSiteFilterNames();
  syncApiSiteFilterSelection(optionNames);
  const optionSet = new Set(optionNames);
  apiSiteFilterSelected = new Set(
    Array.from(apiSiteFilterSelected).filter((name) => optionSet.has(name))
  );

  renderCheckboxFilter({
    optionsWrapId: "apiSiteFilterOptions",
    toggleAllId: "apiSiteFilterToggleAll",
    optionValues: optionNames,
    selectedSet: apiSiteFilterSelected,
    getOptionLabel: (value) => value,
    onOptionChange: onApiSiteFilterOptionChange,
    onAfterRender: () => {
      updateApiSiteFilterButtonLabel();
    },
  });
}

function onApiSiteFilterToggleAll(checked) {
  apiSiteFilterSelected = checked ? new Set(apiSiteFilterOptionNames) : new Set();
  resetApiPageAndRender();
}

function onApiSiteFilterOptionChange(siteName, checked) {
  const normalized = textValue(siteName).trim();
  if (!normalized) return;
  if (checked) {
    apiSiteFilterSelected.add(normalized);
  } else {
    apiSiteFilterSelected.delete(normalized);
  }
  resetApiPageAndRender();
}

function closeApiTypeFilterDropdown() {
  closeDropdown("apiTypeFilterDropdown");
}

function toggleApiTypeFilterDropdown(event) {
  toggleDropdown(event, "apiTypeFilterDropdown");
}

function getApiTypeFilterValues() {
  const typeSet = new Set();
  (Array.isArray(state.apis) ? state.apis : []).forEach((api) => {
    const type = textValue(api?.type).trim().toLowerCase() || "text";
    if (DATA_TYPE_OPTIONS.includes(type)) {
      typeSet.add(type);
    }
  });
  return DATA_TYPE_OPTIONS.filter((type) => typeSet.has(type));
}

function syncApiTypeFilterSelection(nextOptionValues) {
  const optionValues = Array.isArray(nextOptionValues) ? nextOptionValues : [];
  const optionSet = new Set(optionValues);
  const wasAllSelected =
    apiTypeFilterInitialized &&
    apiTypeFilterOptionValues.length > 0 &&
    apiTypeFilterSelected.size === apiTypeFilterOptionValues.length;

  if (!apiTypeFilterInitialized) {
    apiTypeFilterSelected = new Set(optionValues);
    apiTypeFilterInitialized = true;
    apiTypeFilterOptionValues = optionValues;
    return;
  }

  const nextSelected = new Set(
    Array.from(apiTypeFilterSelected).filter((value) => optionSet.has(value))
  );
  if (wasAllSelected) {
    optionValues.forEach((value) => nextSelected.add(value));
  }
  apiTypeFilterSelected = nextSelected;
  apiTypeFilterOptionValues = optionValues;
}

function updateApiTypeFilterButtonLabel() {
  const btn = document.getElementById("apiTypeFilterBtn");
  if (!btn) return;
  const total = apiTypeFilterOptionValues.length;
  const selected = apiTypeFilterSelected.size;
  const label = t("api_type_filter");
  if (!total) {
    btn.textContent = `${label} (0/0)`;
    return;
  }
  btn.textContent = `${label} (${selected}/${total})`;
}

function renderApiTypeFilter() {
  const optionValues = getApiTypeFilterValues();
  syncApiTypeFilterSelection(optionValues);
  const optionSet = new Set(optionValues);
  apiTypeFilterSelected = new Set(
    Array.from(apiTypeFilterSelected).filter((value) => optionSet.has(value))
  );

  renderCheckboxFilter({
    optionsWrapId: "apiTypeFilterOptions",
    toggleAllId: "apiTypeFilterToggleAll",
    optionValues,
    selectedSet: apiTypeFilterSelected,
    getOptionLabel: getTypeOptionLabel,
    onOptionChange: onApiTypeFilterOptionChange,
    onAfterRender: () => {
      updateApiTypeFilterButtonLabel();
    },
  });
}

function onApiTypeFilterToggleAll(checked) {
  apiTypeFilterSelected = checked ? new Set(apiTypeFilterOptionValues) : new Set();
  resetApiPageAndRender();
}

function onApiTypeFilterOptionChange(typeValue, checked) {
  const normalized = textValue(typeValue).trim().toLowerCase();
  if (!normalized) return;
  if (checked) {
    apiTypeFilterSelected.add(normalized);
  } else {
    apiTypeFilterSelected.delete(normalized);
  }
  resetApiPageAndRender();
}

function openApiPoolBySite(siteName) {
  const normalized = textValue(decodeURIComponent(siteName || "")).trim();
  if (!normalized) return;
  const optionNames = getApiSiteFilterNames();
  apiSiteFilterOptionNames = optionNames;
  apiSiteFilterInitialized = true;
  apiSiteFilterSelected = optionNames.includes(normalized)
    ? new Set([normalized])
    : new Set();
  setApiPageToFirst();
  closeApiSiteFilterDropdown();
  switchMainTab("api");
  renderApis();
}

function resolveApiSiteName(api) {
  const direct = textValue(api?.site).trim();
  if (direct) return direct;
  const url = textValue(api?.url).trim();
  if (!url) return "";
  let matchedName = "";
  let matchedLen = -1;
  (Array.isArray(state.sites) ? state.sites : []).forEach((site) => {
    const siteUrl = textValue(site?.url).trim();
    if (!siteUrl) return;
    if (url.startsWith(siteUrl) && siteUrl.length > matchedLen) {
      matchedLen = siteUrl.length;
      matchedName = textValue(site?.name).trim();
    }
  });
  return matchedName;
}

function filterApisBySite(items) {
  const safeItems = Array.isArray(items) ? items : [];
  const totalSiteOptions = apiSiteFilterOptionNames.length;
  if (!totalSiteOptions) {
    return safeItems;
  }
  if (apiSiteFilterSelected.size >= totalSiteOptions) {
    return safeItems;
  }
  if (apiSiteFilterSelected.size <= 0) {
    return [];
  }
  return safeItems.filter((api) =>
    apiSiteFilterSelected.has(resolveApiSiteName(api))
  );
}

function filterApisByType(items) {
  const safeItems = Array.isArray(items) ? items : [];
  const totalTypeOptions = apiTypeFilterOptionValues.length;
  if (!totalTypeOptions) {
    return safeItems;
  }
  if (apiTypeFilterSelected.size >= totalTypeOptions) {
    return safeItems;
  }
  if (apiTypeFilterSelected.size <= 0) {
    return [];
  }
  return safeItems.filter((api) => {
    const type = textValue(api?.type).trim().toLowerCase() || "text";
    return apiTypeFilterSelected.has(type);
  });
}

function getDisplayedApiNames() {
  return getDisplayedApiRows()
    .map((api) => textValue(api?.name).trim())
    .filter(Boolean);
}

function closeLocalTypeFilterDropdown() {
  closeDropdown("localTypeFilterDropdown");
}

function toggleLocalTypeFilterDropdown(event) {
  toggleDropdown(event, "localTypeFilterDropdown");
}

function getLocalTypeFilterValues() {
  return [...DATA_TYPE_OPTIONS];
}

function syncLocalTypeFilterSelection(nextOptionValues) {
  const optionValues = Array.isArray(nextOptionValues) ? nextOptionValues : [];
  const optionSet = new Set(optionValues);
  const wasAllSelected =
    localTypeFilterInitialized &&
    localTypeFilterOptionValues.length > 0 &&
    localTypeFilterSelected.size === localTypeFilterOptionValues.length;

  if (!localTypeFilterInitialized) {
    localTypeFilterSelected = new Set(optionValues);
    localTypeFilterInitialized = true;
    localTypeFilterOptionValues = optionValues;
    return;
  }

  const nextSelected = new Set(
    Array.from(localTypeFilterSelected).filter((value) => optionSet.has(value))
  );
  if (wasAllSelected) {
    optionValues.forEach((value) => nextSelected.add(value));
  }
  localTypeFilterSelected = nextSelected;
  localTypeFilterOptionValues = optionValues;
}

function updateLocalTypeFilterButtonLabel() {
  const btn = document.getElementById("localTypeFilterBtn");
  if (!btn) return;
  const total = localTypeFilterOptionValues.length;
  const selected = localTypeFilterSelected.size;
  const label = t("local_type_filter");
  if (!total) {
    btn.textContent = `${label} (0/0)`;
    return;
  }
  btn.textContent = `${label} (${selected}/${total})`;
}

function renderLocalTypeFilter() {
  const optionValues = getLocalTypeFilterValues();
  syncLocalTypeFilterSelection(optionValues);
  const optionSet = new Set(optionValues);
  localTypeFilterSelected = new Set(
    Array.from(localTypeFilterSelected).filter((value) => optionSet.has(value))
  );

  renderCheckboxFilter({
    optionsWrapId: "localTypeFilterOptions",
    toggleAllId: "localTypeFilterToggleAll",
    optionValues,
    selectedSet: localTypeFilterSelected,
    getOptionLabel: getTypeOptionLabel,
    onOptionChange: onLocalTypeFilterOptionChange,
    onAfterRender: () => {
      updateLocalTypeFilterButtonLabel();
    },
  });
}

function onLocalTypeFilterToggleAll(checked) {
  localTypeFilterSelected = checked ? new Set(localTypeFilterOptionValues) : new Set();
  resetLocalPageAndReload();
}

function onLocalTypeFilterOptionChange(typeValue, checked) {
  const normalized = textValue(typeValue).trim().toLowerCase();
  if (!normalized) return;
  if (checked) {
    localTypeFilterSelected.add(normalized);
  } else {
    localTypeFilterSelected.delete(normalized);
  }
  resetLocalPageAndReload();
}

function compareTextAsc(a, b) {
  return String(a || "").localeCompare(String(b || ""), currentLang === "zh" ? "zh-CN" : "en");
}

function sortSites(items, rule) {
  const safeItems = Array.isArray(items) ? [...items] : [];
  const safeRule = textValue(rule).trim().toLowerCase();
  return safeItems.sort((left, right) => {
    const leftName = textValue(left?.name).toLowerCase();
    const rightName = textValue(right?.name).toLowerCase();
    const leftUrl = textValue(left?.url).toLowerCase();
    const rightUrl = textValue(right?.url).toLowerCase();
    const leftTimeout = Number(left?.timeout || 0);
    const rightTimeout = Number(right?.timeout || 0);
    const leftApiCount = Number(left?.api_count || 0);
    const rightApiCount = Number(right?.api_count || 0);
    const leftEnabled = Boolean(left?.enabled) ? 1 : 0;
    const rightEnabled = Boolean(right?.enabled) ? 1 : 0;

    if (safeRule === "name_desc") return compareTextAsc(rightName, leftName);
    if (safeRule === "url_asc") return compareTextAsc(leftUrl, rightUrl) || compareTextAsc(leftName, rightName);
    if (safeRule === "url_desc") return compareTextAsc(rightUrl, leftUrl) || compareTextAsc(leftName, rightName);
    if (safeRule === "timeout_asc") return leftTimeout - rightTimeout || compareTextAsc(leftName, rightName);
    if (safeRule === "timeout_desc") return rightTimeout - leftTimeout || compareTextAsc(leftName, rightName);
    if (safeRule === "api_count_asc") return leftApiCount - rightApiCount || compareTextAsc(leftName, rightName);
    if (safeRule === "api_count_desc") return rightApiCount - leftApiCount || compareTextAsc(leftName, rightName);
    if (safeRule === "enabled_first") return rightEnabled - leftEnabled || compareTextAsc(leftName, rightName);
    if (safeRule === "disabled_first") return leftEnabled - rightEnabled || compareTextAsc(leftName, rightName);
    return compareTextAsc(leftName, rightName);
  });
}

function sortApis(items, rule) {
  const safeItems = Array.isArray(items) ? [...items] : [];
  const safeRule = textValue(rule).trim().toLowerCase();
  return safeItems.sort((left, right) => {
    const leftName = textValue(left?.name).toLowerCase();
    const rightName = textValue(right?.name).toLowerCase();
    const leftUrl = textValue(left?.url).toLowerCase();
    const rightUrl = textValue(right?.url).toLowerCase();
    const leftType = textValue(left?.type).toLowerCase();
    const rightType = textValue(right?.type).toLowerCase();
    const leftValid = Boolean(left?.valid) ? 1 : 0;
    const rightValid = Boolean(right?.valid) ? 1 : 0;
    const leftKeywords = Array.isArray(left?.keywords) ? left.keywords.length : 0;
    const rightKeywords = Array.isArray(right?.keywords) ? right.keywords.length : 0;

    if (safeRule === "name_desc") return compareTextAsc(rightName, leftName);
    if (safeRule === "url_asc") return compareTextAsc(leftUrl, rightUrl) || compareTextAsc(leftName, rightName);
    if (safeRule === "url_desc") return compareTextAsc(rightUrl, leftUrl) || compareTextAsc(leftName, rightName);
    if (safeRule === "type_asc") return compareTextAsc(leftType, rightType) || compareTextAsc(leftName, rightName);
    if (safeRule === "type_desc") return compareTextAsc(rightType, leftType) || compareTextAsc(leftName, rightName);
    if (safeRule === "valid_first") return rightValid - leftValid || compareTextAsc(leftName, rightName);
    if (safeRule === "invalid_first") return leftValid - rightValid || compareTextAsc(leftName, rightName);
    if (safeRule === "keywords_desc") return rightKeywords - leftKeywords || compareTextAsc(leftName, rightName);
    return compareTextAsc(leftName, rightName);
  });
}

function renderSiteUrlCell(url) {
  const rawUrl = textValue(url).trim();
  const safeUrl = escapeHtml(rawUrl);
  if (!rawUrl) {
    return `<div class="url-scroll"></div>`;
  }
  if (!/^https?:\/\//i.test(rawUrl)) {
    return `<div class="url-scroll" title="${safeUrl}">${safeUrl}</div>`;
  }
  return `
    <a
      class="url-scroll site-url-link"
      href="${safeUrl}"
      target="_blank"
      rel="noopener noreferrer"
      title="${safeUrl}"
    >${safeUrl}</a>
  `;
}

function renderSites() {
  const filteredSites = PageHelpers.filterSites(
    Array.isArray(state.sites) ? state.sites : [],
    siteSearchText
  );
  const sortedSites = sortSites(filteredSites, sortState.site);
  const paged = PageHelpers.paginateItems(sortedSites, sitePage, sitePageSize);
  const pageItems = Array.isArray(paged.pageItems) ? paged.pageItems : [];
  sitePage = Math.max(1, Number(paged.page || sitePage || 1));
  SafeStorage.set("api_aggregator_page_site", String(sitePage));
  persistPageQueryState();

  const total = Math.max(0, Number(paged.total || 0));
  const start = total > 0 ? Math.max(0, Number(paged.startIndex || 0)) + 1 : 0;
  const end = total > 0 ? Math.min(total, Math.max(0, Number(paged.startIndex || 0)) + pageItems.length) : 0;
  sitePagination = {
    page: sitePage,
    page_size: sitePageSize,
    total,
    total_pages: Math.max(1, Number(paged.totalPages || 1)),
    start: Math.max(0, Number(paged.startIndex || 0)),
    end,
  };
  document.getElementById("siteCount").textContent = formatItems(total);
  renderPager({
    pagerId: "sitePagerTop",
    page: sitePage,
    totalPages: sitePagination.total_pages,
    total,
    start,
    end,
    onPageChange: "onSitePageChange"
  });

  const rows = pageItems.map((s, i) => `
        <tr class="${
          isPendingDelete("site", { name: textValue(s.name) }) ? "is-pending-delete-row" : ""
        }">
          <td>${Math.max(0, Number(sitePagination.start || 0)) + i + 1}</td>
          <td><code class="name-code">${escapeHtml(s.name || "")}</code></td>
          <td class="url-cell">${renderSiteUrlCell(s.url || "")}</td>
          <td>${Number(s.timeout || 60)}</td>
          <td>
            <button
              type="button"
              class="table-link-btn"
              onclick='openApiPoolBySite("${encodeURIComponent(s.name || "")}")'
            >${Math.max(0, Number(s.api_count || 0))}</button>
          </td>
          <td class="actions-cell">
            <label class="switch-toggle table-switch" title="${Boolean(s.enabled) ? t("disable_action") : t("enable_action")}">
              <input
                type="checkbox"
                ${Boolean(s.enabled) ? "checked" : ""}
                onclick='toggleSiteEnabled(this, "${encodeURIComponent(s.name || "")}", this.checked)'
              >
              <span class="switch-slider"></span>
            </label>
            <button onclick='openSiteEditorByName("${encodeURIComponent(s.name || "")}")'>${t("edit")}</button>
            <button class="danger ${
              isPendingDelete("site", { name: textValue(s.name) }) ? "is-pending-delete" : ""
            }" onclick='removeSite(this, "${encodeURIComponent(s.name || "")}")'>${t("delete")}</button>
          </td>
        </tr>
      `).join("");
  const emptySiteRow = Array.isArray(state.sites) && state.sites.length === 0
    ? buildEmptyPoolHintCell("site", 6)
    : buildNoDataHintCell(6);
  document.getElementById("siteTable").innerHTML = `
        <thead>
          <tr>
            <th>${t("serial_no")}</th>
            <th class="sortable-head" onclick="onSiteHeaderSort('name')">${t("name")}<span class="sort-indicator">${PageHelpers.getSortIndicator(sortState.site, SITE_SORT_RULES.name)}</span></th>
            <th class="sortable-head" onclick="onSiteHeaderSort('url')">${t("url")}<span class="sort-indicator">${PageHelpers.getSortIndicator(sortState.site, SITE_SORT_RULES.url)}</span></th>
            <th class="sortable-head" onclick="onSiteHeaderSort('timeout')">${t("timeout")}<span class="sort-indicator">${PageHelpers.getSortIndicator(sortState.site, SITE_SORT_RULES.timeout)}</span></th>
            <th class="sortable-head" onclick="onSiteHeaderSort('api_count')">${t("api_count")}<span class="sort-indicator">${PageHelpers.getSortIndicator(sortState.site, SITE_SORT_RULES.api_count)}</span></th>
            <th>${t("actions")}</th>
          </tr>
        </thead>
        <tbody>
          ${rows || emptySiteRow}
        </tbody>
      `;
}

function renderApis() {
  renderApiSiteFilter();
  renderApiTypeFilter();
  const searchedApis = PageHelpers.filterApis(
    Array.isArray(state.apis) ? state.apis : [],
    apiSearchText
  );
  const siteFilteredApis = filterApisBySite(searchedApis);
  const typeFilteredApis = filterApisByType(siteFilteredApis);
  const sortedApis = sortApis(typeFilteredApis, sortState.api);
  const paged = PageHelpers.paginateItems(sortedApis, apiPage, apiPageSize);
  const pageItems = Array.isArray(paged.pageItems) ? paged.pageItems : [];
  apiPage = Math.max(1, Number(paged.page || apiPage || 1));
  SafeStorage.set("api_aggregator_page_api", String(apiPage));
  persistPageQueryState();

  const total = Math.max(0, Number(paged.total || 0));
  const start = total > 0 ? Math.max(0, Number(paged.startIndex || 0)) + 1 : 0;
  const end = total > 0 ? Math.min(total, Math.max(0, Number(paged.startIndex || 0)) + pageItems.length) : 0;
  apiPagination = {
    page: apiPage,
    page_size: apiPageSize,
    total,
    total_pages: Math.max(1, Number(paged.totalPages || 1)),
    start: Math.max(0, Number(paged.startIndex || 0)),
    end,
  };
  document.getElementById("apiCount").textContent = formatItems(total);
  renderPager({
    pagerId: "apiPagerTop",
    page: apiPage,
    totalPages: apiPagination.total_pages,
    total,
    start,
    end,
    onPageChange: "onApiPageChange"
  });

  const rows = pageItems.map((a, i) => `
        <tr class="${
          isPendingDelete("api", { name: textValue(a.name) }) ? "is-pending-delete-row" : ""
        }">
          <td>${Math.max(0, Number(apiPagination.start || 0)) + i + 1}</td>
          <td><code class="name-code">${escapeHtml(a.name || "")}</code></td>
          <td class="url-cell"><div class="url-scroll" title="${escapeHtml(a.url || "")}">${escapeHtml(a.url || "")}</div></td>
          <td>${formatTypeCell(a.type)}</td>
          <td>
            <span class="status-dot ${Boolean(a.valid) ? "is-valid" : ""}">
              ${boolText(Boolean(a.valid))}
            </span>
          </td>
          <td class="keywords-cell">${formatKeywordsCell(a.keywords)}</td>
          <td class="actions-cell">
            <label class="switch-toggle table-switch" title="${Boolean(a.enabled) ? t("disable_action") : t("enable_action")}">
              <input
                type="checkbox"
                ${Boolean(a.enabled) ? "checked" : ""}
                onclick='toggleApiEnabled(this, "${encodeURIComponent(a.name || "")}", this.checked)'
              >
              <span class="switch-slider"></span>
            </label>
            <button class="warn" onclick='testSingleApi(this, "${encodeURIComponent(a.name || "")}")'>${t("test")}</button>
            <button onclick='openApiEditorByName("${encodeURIComponent(a.name || "")}")'>${t("edit")}</button>
            <button class="danger ${
              isPendingDelete("api", { name: textValue(a.name) }) ? "is-pending-delete" : ""
            }" onclick='removeApi(this, "${encodeURIComponent(a.name || "")}")'>${t("delete")}</button>
          </td>
        </tr>
      `).join("");
  const emptyApiRow = Array.isArray(state.apis) && state.apis.length === 0
    ? buildEmptyPoolHintCell("api", 7)
    : buildNoDataHintCell(7);
  document.getElementById("apiTable").innerHTML = `
        <thead>
          <tr>
            <th>${t("serial_no")}</th>
            <th class="sortable-head" onclick="onApiHeaderSort('name')">${t("name")}<span class="sort-indicator">${PageHelpers.getSortIndicator(sortState.api, API_SORT_RULES.name)}</span></th>
            <th class="sortable-head" onclick="onApiHeaderSort('url')">${t("url")}<span class="sort-indicator">${PageHelpers.getSortIndicator(sortState.api, API_SORT_RULES.url)}</span></th>
            <th class="sortable-head" onclick="onApiHeaderSort('type')">${t("type")}<span class="sort-indicator">${PageHelpers.getSortIndicator(sortState.api, API_SORT_RULES.type)}</span></th>
            <th class="sortable-head" onclick="onApiHeaderSort('valid')">${t("valid")}<span class="sort-indicator">${PageHelpers.getSortIndicator(sortState.api, API_SORT_RULES.valid)}</span></th>
            <th class="sortable-head" onclick="onApiHeaderSort('keywords')">${t("keywords")}<span class="sort-indicator">${PageHelpers.getSortIndicator(sortState.api, API_SORT_RULES.keywords)}</span></th>
            <th>${t("actions")}</th>
          </tr>
        </thead>
        <tbody>
          ${rows || emptyApiRow}
        </tbody>
      `;
}

function renderPager({ pagerId, page, totalPages, total, start, end, onPageChange }) {
  const pager = document.getElementById(pagerId);
  if (!pager) return;
  const safeTotal = Math.max(0, Number(total || 0));
  const safeTotalPages = Math.max(1, Number(totalPages || 1));
  const safePage = Math.min(Math.max(1, Number(page || 1)), safeTotalPages);
  const rangeText = safeTotal > 0
    ? `${Math.max(1, Number(start || 1))}-${Math.max(1, Number(end || 1))} / ${safeTotal}`
    : "0-0 / 0";
  const firstDisabled = safePage <= 1 ? "disabled" : "";
  const prevDisabled = safePage <= 1 ? "disabled" : "";
  const nextDisabled = safePage >= safeTotalPages ? "disabled" : "";
  const lastDisabled = safePage >= safeTotalPages ? "disabled" : "";
  const prevPage = Math.max(1, safePage - 1);
  const nextPage = Math.min(safeTotalPages, safePage + 1);
  pager.innerHTML = `
        <button type="button" class="pager-icon-btn" title="${escapeHtml(t("page_first"))}" ${firstDisabled} onclick="${onPageChange}(1)">&lt;&lt;</button>
        <button type="button" class="pager-icon-btn" title="${escapeHtml(t("page_prev"))}" ${prevDisabled} onclick="${onPageChange}(${prevPage})">&lt;</button>
        <span class="pager-range">${escapeHtml(rangeText)}</span>
        <button type="button" class="pager-icon-btn" title="${escapeHtml(t("page_next"))}" ${nextDisabled} onclick="${onPageChange}(${nextPage})">&gt;</button>
        <button type="button" class="pager-icon-btn" title="${escapeHtml(t("page_last"))}" ${lastDisabled} onclick="${onPageChange}(${safeTotalPages})">&gt;&gt;</button>
      `;
}

function formatKeywordsCell(keywords) {
  if (!Array.isArray(keywords) || keywords.length === 0) {
    return "0";
  }
  const full = keywords
    .map((item) => textValue(item).trim())
    .filter(Boolean)
    .join(", ");
  const safe = escapeHtml(full || "0");
  return `<div class="keywords-scroll" title="${safe}">${safe}</div>`;
}

function formatTypeCell(type) {
  const raw = textValue(type).trim().toLowerCase() || "text";
  const typeMap = {
    text: { symbol: "T" },
    image: { symbol: "I" },
    video: { symbol: "V" },
    audio: { symbol: "A" }
  };
  const fallbackLabel = raw || "unknown";
  const localizedLabel = getTypeOptionLabel(raw) || fallbackLabel;
  const meta = typeMap[raw] || { symbol: "?" };
  return `
        <span class="type-chip type-${escapeHtml(raw)}" title="${escapeHtml(localizedLabel)}">
          <span class="type-chip-symbol">${escapeHtml(meta.symbol)}</span>
          <span>${escapeHtml(localizedLabel)}</span>
        </span>
      `;
}

function formatLocalType(type) {
  return formatTypeCell(type);
}

function renderLocalData() {
  renderLocalTypeFilter();
  localDataManager.renderLocalData();
}

function render() {
  renderSites();
  renderApis();
  renderLocalData();
}

function siteTemplate() {
  return {
    name: "my_site",
    url: "https://example.com",
    enabled: true,
    headers: {},
    keys: {},
    timeout: 60
  };
}

function apiTemplate() {
  return {
    name: "my_api",
    url: "https://example.com/api",
    type: "text",
    params: {},
    parse: "",
    enabled: true,
    scope: [],
    keywords: ["my_api"],
    valid: true
  };
}

function openSiteEditorByName(name) {
  const decoded = decodeURIComponent(name || "");
  const target = state.sites.find((site) => textValue(site?.name) === decoded) || null;
  openEditor("site", target);
}

function openApiEditorByName(name) {
  const decoded = decodeURIComponent(name || "");
  const target = state.apis.find((api) => textValue(api?.name) === decoded) || null;
  openEditor("api", target);
}

async function onConfirmPendingDeleteClick(btn) {
  const snapshot = getPendingDeleteSnapshot();
  if (snapshot.selectedCount <= 0) {
    refreshPendingDeletePanel();
    return;
  }
  await withButtonLoading(btn, async () => {
    try {
      if (snapshot.apis.length > 0) {
        await req("/api/api/batch", {
          method: "DELETE",
          body: JSON.stringify({ names: snapshot.apis }),
        });
      }
      if (snapshot.sites.length > 0) {
        await req("/api/site/batch", {
          method: "DELETE",
          body: JSON.stringify({ names: snapshot.sites.map((item) => item.name) }),
        });
      }
      if (snapshot.localTargets.length > 0) {
        await req("/api/local-data/batch", {
          method: "DELETE",
          body: JSON.stringify({ targets: snapshot.localTargets }),
        });
        const viewingType = textValue(localViewerState?.type).trim();
        const viewingName = textValue(localViewerState?.name).trim();
        const removedViewingCollection = snapshot.localTargets.some(
          (item) =>
            textValue(item?.type).trim() === viewingType &&
            textValue(item?.name).trim() === viewingName
        );
        if (removedViewingCollection) {
          closeLocalDataModal();
        }
      }
      clearPendingDeleteSelection();
      await loadPool({ includeLocalData: false });
      await loadLocalData();
    } catch (err) {
      showNoticeModal(err.message || String(err));
    }
  });
}

async function onTestAllClick(btn) {
  await withButtonLoading(btn, async () => {
    const visibleNames = getDisplayedApiNames();
    if (!visibleNames.length) {
      showNoticeModal(t("import_empty_hint"));
      return;
    }
    await streamApiTests(
      visibleNames,
      createRunningTask("batch", t("test_all_title")),
      null
    );
  });
}

async function onSaveClick(btn) {
  await withButtonLoading(btn, async () => {
    await saveEditor();
  });
}

async function onEditorTestClick(btn) {
  if (editorState.kind !== "api") {
    return;
  }
  try {
    await testEditorApi(btn);
  } catch (err) {
    showNoticeModal(err.message || String(err));
  }
}

async function loadPool(options = {}) {
  const includeLocalData = options.includeLocalData !== false;
  const silent = Boolean(options.silent);
  try {
    const data = await req("/api/pool");
    applyPoolData(data);
    const importedAny = await tryAutoImportDefaultPools();
    if (importedAny) {
      const refreshed = await req("/api/pool");
      applyPoolData(refreshed);
    }
    hasPoolLoaded = true;
    renderSites();
    renderApis();
    if (includeLocalData) {
      await loadLocalData();
    }
  } catch (err) {
    if (!silent) {
      showNoticeModal(err.message || String(err));
    }
  }
}

window.addEventListener("resize", () => {
  document.querySelectorAll(".list-collection[id]").forEach((node) => {
    applyListLayout(node.id);
  });
});

document.addEventListener("click", (event) => {
  const target = event.target;
  const apiSiteWrap = document.getElementById("apiSiteFilterWrap");
  const apiTypeWrap = document.getElementById("apiTypeFilterWrap");
  const localTypeWrap = document.getElementById("localTypeFilterWrap");
  if (apiSiteWrap && target instanceof Node && !apiSiteWrap.contains(target)) {
    closeApiSiteFilterDropdown();
  }
  if (apiTypeWrap && target instanceof Node && !apiTypeWrap.contains(target)) {
    closeApiTypeFilterDropdown();
  }
  if (localTypeWrap && target instanceof Node && !localTypeWrap.contains(target)) {
    closeLocalTypeFilterDropdown();
  }

  const siteMenu = document.getElementById("sitePoolIoMenu");
  const siteBtn = document.getElementById("sitePoolIoMenuBtn");
  const apiMenu = document.getElementById("apiPoolIoMenu");
  const apiBtn = document.getElementById("apiPoolIoMenuBtn");
  const inSiteMenu = target instanceof Node && (
    (siteMenu && siteMenu.contains(target)) ||
    (siteBtn && siteBtn.contains(target))
  );
  const inApiMenu = target instanceof Node && (
    (apiMenu && apiMenu.contains(target)) ||
    (apiBtn && apiBtn.contains(target))
  );
  if (!inSiteMenu && !inApiMenu) {
    closePoolIoMenus();
  }
});

async function bootstrapPage() {
  try {
    const bridge = await waitForBridge();
    syncPageContext(bridge?.getContext?.(), { force: true });
    if (bridge && typeof bridge.onContext === "function") {
      bridge.onContext((context) => {
        syncPageContext(context, { force: true });
      });
    }
    switchMainTab(mainTab);
    persistSortState();
    await loadPool();
  } catch (err) {
    showNoticeModal(err?.message || String(err));
  }
}

Object.assign(window, {
  addListRow,
  addPairRow,
  clearPendingDeleteSelection,
  closeEditor,
  closeLocalDataModal,
  closeNoticeModal,
  closePoolIoModal,
  closeTestModal,
  onApiHeaderSort,
  onApiPageSizeChange,
  onApiPageChange,
  onApiSearchChange,
  onApiSiteFilterToggleAll,
  onApiTypeFilterToggleAll,
  onConfirmLocalDataDeleteClick,
  onConfirmPendingDeleteClick,
  onEditorTestClick,
  onListInputChange,
  onLocalHeaderSort,
  onLocalPageSizeChange,
  onLocalPageChange,
  onLocalSearchChange,
  onLocalTypeFilterToggleAll,
  onPoolDefaultFileToggle,
  onPoolIoConfirmClick,
  onPoolIoDeleteClick,
  onPoolIoDirChange,
  onPoolIoPickDirClick,
  onRefreshLocalDataClick,
  onSaveClick,
  onSiteHeaderSort,
  onSitePageChange,
  onSitePageSizeChange,
  onSiteSearchChange,
  onStopBatchTestClick,
  onTestAllClick,
  onToggleBatchPauseClick,
  onToggleRunningTasksPanel,
  onToggleSingleRepeatClick: async () => {
    await runToggleSingleRepeat();
  },
  onToggleSingleRepeatPauseClick,
  onToggleSingleTestParamSheetClick,
  onViewTaskClick,
  openEditor,
  openApiEditorByName,
  openApiPoolBySite,
  openLocalDataViewer,
  openSiteEditorByName,
  openPoolIoModal,
  onQuickImportDefaultPoolClick,
  removeApi,
  removeListRow,
  removeLocalCollection,
  removeLocalItem,
  removePairRow,
  removeSite,
  switchMainTab,
  testSingleApi,
  toggleApiSiteFilterDropdown,
  toggleApiTypeFilterDropdown,
  toggleApiEnabled,
  toggleLocalTypeFilterDropdown,
  togglePoolIoMenu,
  toggleSiteEnabled,
});

void bootstrapPage();






