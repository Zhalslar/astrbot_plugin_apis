const PageHelpers = (window.PageHelpers = {
  getDefaultLang(I18NRef) {
    const htmlLang = String(document.documentElement.lang || "").toLowerCase();
    if (htmlLang.startsWith("zh") && I18NRef.zh) {
      return "zh";
    }
    if (htmlLang.startsWith("en") && I18NRef.en) {
      return "en";
    }
    const navLang = (navigator.language || "en").toLowerCase();
    const fallback = navLang.startsWith("zh") ? "zh" : "en";
    return I18NRef[fallback] ? fallback : "en";
  },

  getDefaultTheme() {
    const htmlTheme = String(
      document.documentElement.getAttribute("data-theme") || ""
    ).toLowerCase();
    return htmlTheme === "light" || htmlTheme === "dark" ? htmlTheme : "";
  },

  getDefaultSortState() {
    const raw = SafeStorage.get("api_aggregator_sort");
    if (!raw) {
      return { site: "name_asc", api: "name_asc", local: "name_asc" };
    }
    try {
      const parsed = JSON.parse(raw);
      return {
        site: typeof parsed?.site === "string" ? parsed.site : "name_asc",
        api: typeof parsed?.api === "string" ? parsed.api : "name_asc",
        local: typeof parsed?.local === "string" ? parsed.local : "name_asc",
      };
    } catch {
      return { site: "name_asc", api: "name_asc", local: "name_asc" };
    }
  },

  getDefaultPageSize(storageKey) {
    const key = textValue(storageKey).trim() || "api_aggregator_page_size_api";
    const raw = String(SafeStorage.get(key, "all") || "all").toLowerCase();
    if (raw === "all") {
      return "all";
    }
    const numeric = Number.parseInt(raw, 10);
    if ([10, 20, 50, 100].includes(numeric)) {
      return numeric;
    }
    return "all";
  },

  getDefaultPage(storageKey) {
    const key = textValue(storageKey).trim();
    if (!key) return 1;
    const raw = SafeStorage.get(key);
    const parsed = Number.parseInt(String(raw || "1"), 10);
    if (!Number.isFinite(parsed) || parsed < 1) {
      return 1;
    }
    return parsed;
  },

  getDefaultMainTab() {
    const saved = SafeStorage.get("api_aggregator_main_tab");
    if (saved === "site" || saved === "api" || saved === "local") {
      return saved;
    }
    return "api";
  },

  getSortIndicator(currentRule, rules) {
    if (!Array.isArray(rules) || !rules.length) return "";
    if (currentRule === rules[0]) return "▲";
    if (rules.length > 1 && currentRule === rules[1]) return "▼";
    return "";
  },

  paginateItems(items, currentPage, sizeSetting) {
    const safeItems = Array.isArray(items) ? items : [];
    const total = safeItems.length;
    const useAll = sizeSetting === "all";
    const pageSize = useAll ? Math.max(1, total || 1) : Number(sizeSetting || 10);
    const totalPages = useAll ? 1 : Math.max(1, Math.ceil(total / pageSize));
    const page = Math.min(Math.max(1, Number(currentPage || 1)), totalPages);
    const startIndex = useAll ? 0 : (page - 1) * pageSize;
    const pageItems = useAll
      ? safeItems
      : safeItems.slice(startIndex, startIndex + pageSize);
    return { total, page, totalPages, startIndex, pageItems };
  },

  filterSites(items, query) {
    const q = textValue(query).trim().toLowerCase();
    if (!q) return Array.isArray(items) ? items : [];
    return (Array.isArray(items) ? items : []).filter((site) => {
      const name = textValue(site?.name).toLowerCase();
      const url = textValue(site?.url).toLowerCase();
      const headers = Object.keys(site?.headers || {}).map((k) =>
        textValue(k).toLowerCase()
      );
      const keys = Object.keys(site?.keys || {}).map((k) =>
        textValue(k).toLowerCase()
      );
      return (
        name.includes(q) ||
        url.includes(q) ||
        headers.some((k) => k.includes(q)) ||
        keys.some((k) => k.includes(q))
      );
    });
  },

  filterApis(items, query) {
    const q = textValue(query).trim().toLowerCase();
    if (!q) return Array.isArray(items) ? items : [];
    return (Array.isArray(items) ? items : []).filter((api) => {
      const name = textValue(api?.name).toLowerCase();
      const url = textValue(api?.url).toLowerCase();
      const keywords = Array.isArray(api?.keywords)
        ? api.keywords.map((k) => textValue(k).toLowerCase())
        : [];
      return (
        name.includes(q) ||
        url.includes(q) ||
        keywords.some((k) => k.includes(q))
      );
    });
  },

  filterLocalCollections(items, query) {
    const q = textValue(query).trim().toLowerCase();
    if (!q) return Array.isArray(items) ? items : [];
    return (Array.isArray(items) ? items : []).filter((item) => {
      const name = textValue(item?.name).toLowerCase();
      const type = textValue(item?.type).toLowerCase();
      return name.includes(q) || type.includes(q);
    });
  },

  getSortedLocalCollections(items, sortRule) {
    const data = Array.isArray(items) ? [...items] : [];
    const rule = textValue(sortRule).toLowerCase();
    const byName = (x) => textValue(x?.name).toLowerCase();
    const byType = (x) => textValue(x?.type).toLowerCase();
    const byCount = (x) => Number(x?.count || 0);
    const bySize = (x) => Number(x?.size_bytes || 0);
    const byUpdated = (x) => Number(x?.updated_at || 0);

    if (rule === "name_desc")
      return data.sort((a, b) => byName(b).localeCompare(byName(a)));
    if (rule === "type_asc")
      return data.sort(
        (a, b) =>
          byType(a).localeCompare(byType(b)) || byName(a).localeCompare(byName(b))
      );
    if (rule === "type_desc")
      return data.sort(
        (a, b) =>
          byType(b).localeCompare(byType(a)) || byName(a).localeCompare(byName(b))
      );
    if (rule === "count_asc")
      return data.sort(
        (a, b) => byCount(a) - byCount(b) || byName(a).localeCompare(byName(b))
      );
    if (rule === "count_desc")
      return data.sort(
        (a, b) => byCount(b) - byCount(a) || byName(a).localeCompare(byName(b))
      );
    if (rule === "size_asc")
      return data.sort(
        (a, b) => bySize(a) - bySize(b) || byName(a).localeCompare(byName(b))
      );
    if (rule === "size_desc")
      return data.sort(
        (a, b) => bySize(b) - bySize(a) || byName(a).localeCompare(byName(b))
      );
    if (rule === "updated_asc")
      return data.sort(
        (a, b) => byUpdated(a) - byUpdated(b) || byName(a).localeCompare(byName(b))
      );
    if (rule === "updated_desc")
      return data.sort(
        (a, b) => byUpdated(b) - byUpdated(a) || byName(a).localeCompare(byName(b))
      );
    return data.sort((a, b) => byName(a).localeCompare(byName(b)));
  },

  estimateListItemWidth(text) {
    const len = textValue(text).trim().length;
    return Math.max(140, Math.min(360, 84 + len * 10));
  },
});
