"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { NoirApiClient } from "@noir/api/client.js";
import { applyFontScale, applyTheme, getInitialFontScale, getInitialTheme } from "@noir/ui/theme.js";
import { classifyApiError, friendlyErrorMessage } from "@noir/ui/states.js";
import { LIMITS } from "@/config/ui.config";
import { useAssistant } from "@/hooks/useAssistant";
import {
  buildTaxRules,
  normalizeCart,
  normalizeOrder,
  normalizePaymentMethod,
  normalizeProduct,
} from "./normalizers";

const StoreContext = createContext(null);

const ACTOR_STORAGE_KEY = "noir_actor_token";
const SESSION_REFRESH_KEY = "noir_session_refresh";
const WISHLIST_STORAGE_KEY = "noir_wishlist";
const ANON_PERMISSIONS = ["catalog:read", "config:read"];

const EMPTY_CATALOG_META = {
  departments: [],
  categories: [],
  colors: [],
  color_families: [],
  materials: [],
  material_families: [],
  sort_options: [],
  price_tiers: [],
  order_statuses: [],
  refund_statuses: [],
  return_reasons: [],
  fit_feedback_options: [],
};

const DEFAULT_FILTERS = {
  q: "",
  department: "ALL",
  category: "",
  color: "",
  material: "",
  priceTier: "ALL",
  minPrice: null,
  maxPrice: null,
  inStockOnly: false,
  sort: "featured",
};

function readJson(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable */
  }
}

export function StoreProvider({ children, initialPage = "shop" }) {
  const [system, setSystem] = useState({ offline: false, unreachable: false, slow: false, sessionExpired: false });
  const [boot, setBoot] = useState({ status: "loading", error: null });
  const [config, setConfig] = useState({
    business: {},
    policies: [],
    paymentMethods: [],
    coupons: [],
    zones: [],
    staffRoles: [],
    demoMode: false,
  });
  const [catalogMeta, setCatalogMeta] = useState(EMPTY_CATALOG_META);
  const [agentRegistry, setAgentRegistry] = useState([]);
  const [availableRoles, setAvailableRoles] = useState([]);
  const [actors, setActors] = useState([]);
  const [actor, setActor] = useState(null);
  const [authUser, setAuthUser] = useState(null);
  const [permissions, setPermissions] = useState(ANON_PERMISSIONS);
  const [categories, setCategories] = useState([]);
  const [allProducts, setAllProducts] = useState([]);
  const [catalog, setCatalog] = useState({
    status: "loading",
    items: [],
    total: 0,
    interpretation: null,
    error: null,
  });
  const [filters, setFiltersState] = useState(DEFAULT_FILTERS);
  const [cart, setCart] = useState(null);
  // Applied coupon code. Mirrored in a ref so async cart loaders always use the latest value.
  const [couponCode, setCouponCodeState] = useState(null);
  const couponRef = useRef(null);
  const setCouponCode = useCallback((code) => {
    couponRef.current = code;
    setCouponCodeState(code);
  }, []);
  const [addresses, setAddresses] = useState([]);
  const [orders, setOrders] = useState({ status: "idle", items: [], error: null });
  const [wishlist, setWishlist] = useState([]);
  const [toasts, setToasts] = useState([]);
  const [theme, setThemeState] = useState("light");
  const [fontScale, setFontScaleState] = useState("default");
  const [ui, setUi] = useState({
    cartOpen: false,
    productId: null,
    menuOpen: false,
    accountOpen: false,
    authModalOpen: false,
    authModalMode: "login",
    chatOpen: false,
    returnOrderId: null,
    page: initialPage,
  });
  const [productDetail, setProductDetail] = useState({ status: "idle", product: null, recommendations: [], error: null });
  const [busyKey, setBusyKey] = useState(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  const handleNetworkEvent = useCallback((evt) => {
    setSystem((prev) => {
      switch (evt.type) {
        case "offline":
          return { ...prev, offline: true };
        case "network_unreachable":
          return { ...prev, unreachable: true, offline: typeof navigator !== "undefined" ? !navigator.onLine : prev.offline };
        case "slow_network":
          return { ...prev, slow: true };
        case "request_ok":
          return { ...prev, offline: false, unreachable: false, slow: Boolean(evt.slow) };
        case "session_expired":
          return { ...prev, sessionExpired: true };
        default:
          return prev;
      }
    });
  }, []);

  const buildActorFromUser = useCallback((user, accessToken = null) => {
    if (!user) return null;
    const isStaffUser = Boolean(user.is_staff || user.actor_type === "admin");
    const roleLabel = user.role_name || user.role;
    return {
      id: user.id,
      customerId: user.customer_id || (user.actor_type === "customer" ? user.id : null),
      staffId: user.staff_id || (isStaffUser ? user.id : null),
      token: accessToken || null,
      actor_type: user.actor_type,
      role: user.role,
      role_name: roleLabel,
      hierarchy_level: user.hierarchy_level || (isStaffUser ? 50 : 10),
      is_staff: isStaffUser,
      loyalty_tier: user.loyalty_tier || (isStaffUser ? "STAFF" : "STANDARD"),
      name: user.name,
      email: user.email,
      phone: user.phone || null,
      status: user.status || "active",
      label: `${user.name} · ${roleLabel}`,
    };
  }, []);

  const handleAuthSessionUpdate = useCallback(
    (refreshed) => {
      if (!refreshed || !refreshed.user) {
        setAuthUser(null);
        setActor(null);
        actorRef.current = null;
        setPermissions(ANON_PERMISSIONS);
        try {
          window.sessionStorage.removeItem(SESSION_REFRESH_KEY);
        } catch {
          /* storage unavailable */
        }
        return;
      }
      const nextActor = buildActorFromUser(refreshed.user, refreshed.tokens?.access_token);
      actorRef.current = nextActor;
      setAuthUser(refreshed.user);
      setActor(nextActor);
      setPermissions(Array.isArray(refreshed.permissions) ? refreshed.permissions : ANON_PERMISSIONS);
      if (refreshed.tokens?.refresh_token) {
        try {
          window.sessionStorage.setItem(SESSION_REFRESH_KEY, refreshed.tokens.refresh_token);
        } catch {
          /* storage unavailable */
        }
      }
    },
    [buildActorFromUser]
  );

  const apiRef = useRef(null);
  if (!apiRef.current) {
    apiRef.current = new NoirApiClient({
      onNetworkEvent: (evt) => handleNetworkEvent(evt),
      onAuthSessionUpdate: (data) => handleAuthSessionUpdate(data),
    });
  }
  const api = apiRef.current;
  api.onAuthSessionUpdate = handleAuthSessionUpdate;

  const filtersRef = useRef(filters);
  filtersRef.current = filters;
  const actorRef = useRef(actor);
  actorRef.current = actor;
  const catalogMetaRef = useRef(catalogMeta);
  catalogMetaRef.current = catalogMeta;
  const toastTimers = useRef(new Map());

  const orderStatusMap = useMemo(() => {
    const map = {};
    for (const row of catalogMeta.order_statuses || []) {
      map[row.code] = row;
    }
    return map;
  }, [catalogMeta.order_statuses]);
  const orderStatusMapRef = useRef(orderStatusMap);
  orderStatusMapRef.current = orderStatusMap;

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = toastTimers.current.get(id);
    if (timer) clearTimeout(timer);
    toastTimers.current.delete(id);
  }, []);

  const notify = useCallback(
    ({ tone = "success", type, title, message, description, action }) => {
      const resolvedTone = type || tone || "success";
      const resolvedMessage = message || description || "";
      const id = `t-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      setToasts((prev) => [...prev.slice(-2), { id, tone: resolvedTone, title, message: resolvedMessage, action }]);
      toastTimers.current.set(id, setTimeout(() => dismissToast(id), LIMITS.toastDurationMs));
      return id;
    },
    [dismissToast]
  );

  const isAuthenticated = Boolean(actor && actor.actor_type && actor.actor_type !== "anon");
  const isCustomer = actor?.role === "customer";
  const isStaff = Boolean(
    actor?.is_staff ||
      actor?.actor_type === "admin" ||
      (config.staffRoles || []).includes(actor?.role)
  );

  const permissionsSet = useMemo(() => new Set(permissions || []), [permissions]);

  const hasPermission = useCallback(
    (permCode) => {
      if (!isAuthenticated) return ANON_PERMISSIONS.includes(permCode);
      if (actor?.role === "super_admin") return true;
      return permissionsSet.has(permCode);
    },
    [actor?.role, isAuthenticated, permissionsSet]
  );

  const hasAnyPermission = useCallback(
    (...permCodes) => permCodes.some((code) => hasPermission(code)),
    [hasPermission]
  );

  const hasRole = useCallback(
    (...roleCodes) => {
      if (!isAuthenticated || !actor?.role) return false;
      if (actor.role === "super_admin") return true;
      return roleCodes.includes(actor.role);
    },
    [actor?.role, isAuthenticated]
  );

  const resolvePriceBounds = useCallback((nextFilters, meta = catalogMetaRef.current) => {
    let minPrice = nextFilters.minPrice;
    let maxPrice = nextFilters.maxPrice;
    if (nextFilters.priceTier && nextFilters.priceTier.toUpperCase() !== "ALL") {
      const tier = (meta?.price_tiers || []).find((t) => t.id === nextFilters.priceTier);
      if (tier) {
        if (minPrice == null) minPrice = tier.min_price ?? null;
        if (maxPrice == null) maxPrice = tier.max_price ?? null;
      }
    }
    return { minPrice, maxPrice };
  }, []);

  const pageSize = LIMITS.catalogPageSize || 24;

  const fetchProducts = useCallback(
    async (nextFilters = filtersRef.current, { silent = false } = {}) => {
      if (!silent) {
        setCatalog((prev) => ({
          ...prev,
          status: prev.items.length ? "refreshing" : "loading",
          error: null,
        }));
      }
      try {
        const { minPrice, maxPrice } = resolvePriceBounds(nextFilters);
        const res = await api.searchCatalog({
          q: nextFilters.q,
          category: nextFilters.category,
          department: nextFilters.department,
          color: nextFilters.color,
          material: nextFilters.material,
          minPrice,
          maxPrice,
          inStockOnly: nextFilters.inStockOnly,
          sort: nextFilters.sort || "featured",
          limit: pageSize,
          offset: 0,
        });
        const rawItems = Array.isArray(res) ? res : res?.items || [];
        const normalized = rawItems.map(normalizeProduct);
        setCatalog({
          status: "ready",
          items: normalized,
          total: typeof res?.total === "number" ? res.total : normalized.length,
          interpretation: res?.interpretation || null,
          error: null,
        });
        if (silent) {
          api
            .searchCatalog({ sort: DEFAULT_FILTERS.sort, limit: 100, offset: 0 })
            .then((arch) => {
              const rows = Array.isArray(arch) ? arch : arch?.items || [];
              if (rows.length) setAllProducts(rows.map(normalizeProduct));
            })
            .catch(() => {});
        }
        return normalized;
      } catch (error) {
        setCatalog((prev) => ({ ...prev, status: "error", error }));
        return null;
      }
    },
    [api, pageSize, resolvePriceBounds]
  );

  const catalogItemsRef = useRef([]);
  catalogItemsRef.current = catalog.items;

  const loadMoreProducts = useCallback(async () => {
    if (isLoadingMore) return null;
    const currentItems = catalogItemsRef.current;
    if (currentItems.length >= catalog.total) return currentItems;
    setIsLoadingMore(true);
    try {
      const nextFilters = filtersRef.current;
      const { minPrice, maxPrice } = resolvePriceBounds(nextFilters);
      const res = await api.searchCatalog({
        q: nextFilters.q,
        category: nextFilters.category,
        department: nextFilters.department,
        color: nextFilters.color,
        material: nextFilters.material,
        minPrice,
        maxPrice,
        inStockOnly: nextFilters.inStockOnly,
        sort: nextFilters.sort || "featured",
        limit: pageSize,
        offset: currentItems.length,
      });
      const rawItems = Array.isArray(res) ? res : res?.items || [];
      const incoming = rawItems.map(normalizeProduct);
      setCatalog((prev) => {
        const seen = new Set(prev.items.map((item) => item.product_id));
        const merged = [...prev.items, ...incoming.filter((item) => !seen.has(item.product_id))];
        return {
          ...prev,
          status: "ready",
          items: merged,
          total: typeof res?.total === "number" ? res.total : prev.total,
        };
      });
      return incoming;
    } catch (error) {
      notify({ tone: "error", title: "Unable to load more pieces", message: friendlyErrorMessage(error) });
      return null;
    } finally {
      setIsLoadingMore(false);
    }
  }, [api, catalog.total, isLoadingMore, notify, pageSize, resolvePriceBounds]);

  const refreshCatalogMeta = useCallback(async () => {
    try {
      const meta = await api.getCatalogMeta();
      const merged = { ...EMPTY_CATALOG_META, ...(meta || {}) };
      setCatalogMeta(merged);
      setCategories(Array.isArray(merged.categories) ? merged.categories : []);
      return merged;
    } catch {
      return catalogMetaRef.current;
    }
  }, [api]);

  const loadCart = useCallback(async () => {
    if (actorRef.current?.role !== "customer") return null;
    try {
      const next = normalizeCart(await api.getCart({ couponCode: couponRef.current }), couponRef.current);
      setCart(next);
      return next;
    } catch {
      return null;
    }
  }, [api]);

  /**
   * Store the cart returned by a mutation. Mutation endpoints price the cart
   * without a coupon, so when one is applied we re-fetch the coupon-priced cart.
   */
  const commitCart = useCallback(
    async (raw) => {
      if (couponRef.current) return loadCart();
      const next = normalizeCart(raw);
      setCart(next);
      return next;
    },
    [loadCart]
  );

  const loadOrders = useCallback(async () => {
    if (actorRef.current?.role !== "customer") {
      setOrders({ status: "ready", items: [], error: null });
      return [];
    }
    setOrders((prev) => ({ ...prev, status: prev.items.length ? "refreshing" : "loading", error: null }));
    try {
      const items = await api.listOrders();
      const map = orderStatusMapRef.current;
      setOrders({
        status: "ready",
        items: (Array.isArray(items) ? items : []).map((raw) => normalizeOrder(raw, map)),
        error: null,
      });
      return items;
    } catch (error) {
      setOrders((prev) => ({ ...prev, status: "error", error }));
      return null;
    }
  }, [api]);

  const loadAddresses = useCallback(async () => {
    const current = actorRef.current;
    if (current?.role !== "customer") {
      setAddresses([]);
      return [];
    }
    try {
      const list = await api.listCustomerAddresses(current.id);
      setAddresses(Array.isArray(list) ? list : []);
      return list;
    } catch {
      return [];
    }
  }, [api]);

  const loadAccountData = useCallback(async () => {
    await Promise.all([loadCart(), loadOrders(), loadAddresses()]);
  }, [loadCart, loadOrders, loadAddresses]);

  const bootstrap = useCallback(async () => {
    setBoot({ status: "loading", error: null });
    setCatalog((prev) => ({ ...prev, status: "loading", error: null }));
    try {
      const [cfg, meta, searchRes, fullArchiveRes, registry, health, rolesRes] = await Promise.all([
        api.getPoliciesAndConfig(),
        api.getCatalogMeta(),
        api.searchCatalog({ sort: DEFAULT_FILTERS.sort, limit: pageSize, offset: 0 }),
        api.searchCatalog({ sort: DEFAULT_FILTERS.sort, limit: 100, offset: 0 }).catch(() => null),
        api.getAgentsRegistry().catch(() => []),
        api.getHealth().catch(() => ({})),
        api.listRoles().catch(() => []),
      ]);

      const actorList = cfg.actors || [];
      setAvailableRoles(Array.isArray(rolesRes) ? rolesRes : []);

      // Restore active JWT session (via HttpOnly cookie or session refresh token) or saved demo persona
      let resolvedActor = null;
      let resolvedUser = null;
      let resolvedPerms = ANON_PERMISSIONS;

      const storedRefresh =
        typeof window !== "undefined" ? window.sessionStorage.getItem(SESSION_REFRESH_KEY) : null;
      const savedDemoToken =
        typeof window !== "undefined" ? window.localStorage.getItem(ACTOR_STORAGE_KEY) : null;

      if (storedRefresh) {
        api.setAuthTokens({ accessToken: api.token, refreshToken: storedRefresh });
      }

      // 1. Try restoring live JWT session via cookie or refresh token
      try {
        if (storedRefresh && !api.token) {
          const refreshed = await api.refreshAuthSession(storedRefresh);
          if (refreshed?.user) {
            resolvedUser = refreshed.user;
            resolvedPerms = refreshed.permissions || ANON_PERMISSIONS;
            resolvedActor = buildActorFromUser(refreshed.user, refreshed.tokens?.access_token);
            if (refreshed.tokens?.refresh_token) {
              window.sessionStorage.setItem(SESSION_REFRESH_KEY, refreshed.tokens.refresh_token);
            }
          }
        } else {
          const meRes = await api.getCurrentUser();
          if (meRes?.user) {
            resolvedUser = meRes.user;
            resolvedPerms = meRes.permissions || ANON_PERMISSIONS;
            resolvedActor = buildActorFromUser(meRes.user, api.token);
          }
        }
      } catch {
        if (storedRefresh) {
          try {
            const refreshed = await api.refreshAuthSession(storedRefresh);
            if (refreshed?.user) {
              resolvedUser = refreshed.user;
              resolvedPerms = refreshed.permissions || ANON_PERMISSIONS;
              resolvedActor = buildActorFromUser(refreshed.user, refreshed.tokens?.access_token);
              if (refreshed.tokens?.refresh_token) {
                window.sessionStorage.setItem(SESSION_REFRESH_KEY, refreshed.tokens.refresh_token);
              }
            }
          } catch {
            try {
              window.sessionStorage.removeItem(SESSION_REFRESH_KEY);
            } catch {
              /* ignore */
            }
            api.clearAuthTokens();
          }
        }
      }

      // 2. Fallback to explicitly chosen demo persona when in demo_mode
      if (!resolvedActor && savedDemoToken && Boolean(health?.demo_mode)) {
        const matchedDemo = actorList.find((a) => a.token === savedDemoToken);
        if (matchedDemo) {
          api.setToken(matchedDemo.token);
          try {
            const meRes = await api.getCurrentUser();
            if (meRes?.user) {
              resolvedUser = meRes.user;
              resolvedPerms = meRes.permissions || ANON_PERMISSIONS;
              resolvedActor = { ...buildActorFromUser(meRes.user, matchedDemo.token), token: matchedDemo.token };
            } else {
              resolvedActor = matchedDemo;
            }
          } catch {
            resolvedActor = matchedDemo;
          }
        }
      }

      actorRef.current = resolvedActor;
      setAuthUser(resolvedUser);
      setPermissions(resolvedPerms);
      setSystem((prev) => ({ ...prev, sessionExpired: false }));

      const mergedMeta = { ...EMPTY_CATALOG_META, ...(meta || {}) };
      catalogMetaRef.current = mergedMeta;
      setCatalogMeta(mergedMeta);
      setCategories(Array.isArray(mergedMeta.categories) ? mergedMeta.categories : []);
      setAgentRegistry(Array.isArray(registry) ? registry : []);

      setConfig({
        business: cfg.business_config || {},
        policies: cfg.policies || [],
        paymentMethods: (cfg.payment_methods || []).map(normalizePaymentMethod),
        coupons: cfg.coupons || [],
        zones: cfg.shipping_zones || [],
        staffRoles: cfg.staff_roles || [],
        demoMode: Boolean(health?.demo_mode),
      });
      setActors(actorList);
      setActor(resolvedActor);

      const rawProducts = Array.isArray(searchRes) ? searchRes : searchRes?.items || [];
      const normalizedProducts = rawProducts.map(normalizeProduct);
      const rawArchive = fullArchiveRes
        ? Array.isArray(fullArchiveRes)
          ? fullArchiveRes
          : fullArchiveRes?.items || []
        : rawProducts;
      setAllProducts(rawArchive.map(normalizeProduct));
      setCatalog({
        status: "ready",
        items: normalizedProducts,
        total: typeof searchRes?.total === "number" ? searchRes.total : normalizedProducts.length,
        interpretation: searchRes?.interpretation || null,
        error: null,
      });
      setBoot({ status: "ready", error: null });
      if (resolvedActor) {
        await loadAccountData();
      }
    } catch (error) {
      setBoot({ status: "error", error });
      setCatalog((prev) => ({ ...prev, status: "error", error }));
    }
  }, [api, buildActorFromUser, loadAccountData, pageSize]);

  useEffect(() => {
    setThemeState(getInitialTheme());
    applyTheme(getInitialTheme());
    const scale = getInitialFontScale();
    setFontScaleState(scale);
    applyFontScale(scale);
    setWishlist(readJson(WISHLIST_STORAGE_KEY, []));
    bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    const goOnline = () => {
      setSystem((prev) => ({ ...prev, offline: false, unreachable: false }));
      bootstrap();
    };
    const goOffline = () => setSystem((prev) => ({ ...prev, offline: true }));
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    if (typeof navigator !== "undefined" && navigator.onLine === false) goOffline();
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, [bootstrap]);

  const firstFilterRun = useRef(true);
  useEffect(() => {
    if (boot.status !== "ready") return undefined;
    if (firstFilterRun.current) {
      firstFilterRun.current = false;
      return undefined;
    }
    const timer = setTimeout(() => fetchProducts(filters), LIMITS.searchDebounceMs);
    return () => clearTimeout(timer);
  }, [
    filters.q,
    filters.department,
    filters.category,
    filters.color,
    filters.material,
    filters.priceTier,
    filters.minPrice,
    filters.maxPrice,
    filters.inStockOnly,
    filters.sort,
    boot.status,
    fetchProducts,
  ]);

  const setFilters = useCallback((patch) => setFiltersState((prev) => ({ ...prev, ...patch })), []);
  const resetFilters = useCallback(() => setFiltersState({ ...DEFAULT_FILTERS }), []);
  const hasActiveFilters = Boolean(
    filters.q ||
      filters.department !== "ALL" ||
      filters.category ||
      filters.color ||
      filters.material ||
      filters.priceTier !== "ALL" ||
      filters.minPrice != null ||
      filters.maxPrice != null ||
      filters.inStockOnly
  );
  const visibleProducts = catalog.items;

  const setOverlay = useCallback((patch) => setUi((prev) => ({ ...prev, ...patch })), []);

  const setTheme = useCallback((next) => {
    setThemeState(next);
    applyTheme(next);
  }, []);

  const setFontScale = useCallback((next) => {
    setFontScaleState(next);
    applyFontScale(next);
  }, []);

  const toggleWishlist = useCallback((productId) => {
    setWishlist((prev) => {
      const next = prev.includes(productId) ? prev.filter((id) => id !== productId) : [...prev, productId];
      writeJson(WISHLIST_STORAGE_KEY, next);
      return next;
    });
  }, []);

  const openAuthModal = useCallback((mode = "login") => {
    setUi((prev) => ({ ...prev, authModalOpen: true, authModalMode: mode }));
  }, []);

  const closeAuthModal = useCallback(() => {
    setUi((prev) => ({ ...prev, authModalOpen: false }));
  }, []);

  const applyAuthSession = useCallback(
    async (res, welcomeTitle = "Welcome to Noir Atelier") => {
      const user = res?.user;
      const tokens = res?.tokens;
      const perms = Array.isArray(res?.permissions) ? res.permissions : ANON_PERMISSIONS;
      const nextActor = buildActorFromUser(user, tokens?.access_token);

      if (tokens?.access_token) {
        api.setAuthTokens({
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token || null,
        });
      }
      try {
        window.localStorage.removeItem(ACTOR_STORAGE_KEY);
        if (tokens?.refresh_token) {
          window.sessionStorage.setItem(SESSION_REFRESH_KEY, tokens.refresh_token);
        }
      } catch {
        /* storage unavailable */
      }

      actorRef.current = nextActor;
      setAuthUser(user);
      setActor(nextActor);
      setPermissions(perms);
      setSystem((prev) => ({ ...prev, sessionExpired: false }));
      setUi((prev) => ({ ...prev, authModalOpen: false }));

      if (user?.actor_type === "customer") {
        await loadAccountData();
      } else {
        setCart(null);
        setOrders({ status: "idle", items: [], error: null });
        setAddresses([]);
      }

      notify({
        tone: "success",
        title: welcomeTitle,
        message: `Signed in as ${user?.name} (${user?.role_name || user?.role}).`,
      });
      return res;
    },
    [api, buildActorFromUser, loadAccountData, notify]
  );

  const login = useCallback(
    async ({ email, password, portal = "auto" }) => {
      const res = await api.login({ email, password, portal });
      return applyAuthSession(res, "Welcome back");
    },
    [api, applyAuthSession]
  );

  const registerCustomer = useCallback(
    async ({ name, email, password, phone = null, preferredDepartment = null }) => {
      const res = await api.registerCustomer({ name, email, password, phone, preferredDepartment });
      return applyAuthSession(res, "Maison Client Profile Created");
    },
    [api, applyAuthSession]
  );

  const registerAdmin = useCallback(
    async ({ name, email, password, roleCode = "manager", phone = null, departmentScope = null, inviteCode = null }) => {
      const res = await api.registerAdmin({
        name,
        email,
        password,
        roleCode,
        phone,
        departmentScope,
        inviteCode,
      });
      if (res?.tokens?.access_token) {
        return applyAuthSession(res, "Maison Staff Account Provisioned");
      }
      notify({
        tone: "success",
        title: "Staff Account Created",
        message: `${res?.user?.name} provisioned with role ${res?.user?.role_name || roleCode}.`,
      });
      return res;
    },
    [api, applyAuthSession, notify]
  );

  const logout = useCallback(async () => {
    const storedRefresh =
      typeof window !== "undefined" ? window.sessionStorage.getItem(SESSION_REFRESH_KEY) : null;
    try {
      await api.logout(storedRefresh);
    } catch {
      /* session already cleared server-side */
    }
    try {
      window.sessionStorage.removeItem(SESSION_REFRESH_KEY);
      window.localStorage.removeItem(ACTOR_STORAGE_KEY);
    } catch {
      /* storage unavailable */
    }
    actorRef.current = null;
    setAuthUser(null);
    setActor(null);
    setPermissions(ANON_PERMISSIONS);
    setCart(null);
    setOrders({ status: "idle", items: [], error: null });
    setAddresses([]);
    setUi((prev) => ({
      ...prev,
      cartOpen: false,
      page: ["admin", "orders", "account"].includes(prev.page) ? "shop" : prev.page,
    }));
    notify({
      tone: "info",
      title: "Signed out",
      message: "Your Noir Atelier session has been securely closed.",
    });
  }, [api, notify]);

  const logoutAll = useCallback(async () => {
    try {
      await api.logoutAllSessions();
    } catch {
      /* ignore */
    }
    try {
      window.sessionStorage.removeItem(SESSION_REFRESH_KEY);
      window.localStorage.removeItem(ACTOR_STORAGE_KEY);
    } catch {
      /* ignore */
    }
    actorRef.current = null;
    setAuthUser(null);
    setActor(null);
    setPermissions(ANON_PERMISSIONS);
    setCart(null);
    setOrders({ status: "idle", items: [], error: null });
    setAddresses([]);
    setUi((prev) => ({
      ...prev,
      cartOpen: false,
      page: ["admin", "orders", "account"].includes(prev.page) ? "shop" : prev.page,
    }));
    notify({
      tone: "info",
      title: "Signed out across all devices",
      message: "All active tokens and sessions for your account have been revoked.",
    });
  }, [api, notify]);

  const refreshProfile = useCallback(async () => {
    try {
      const meRes = await api.getCurrentUser();
      if (meRes?.user) {
        const nextActor = buildActorFromUser(meRes.user, api.token);
        actorRef.current = nextActor;
        setAuthUser(meRes.user);
        setActor(nextActor);
        setPermissions(meRes.permissions || ANON_PERMISSIONS);
      }
      return meRes;
    } catch {
      return null;
    }
  }, [api, buildActorFromUser]);

  const switchActor = useCallback(
    async (token) => {
      if (!token) {
        await logout();
        return;
      }
      const next = actors.find((a) => a.token === token);
      if (!next) return;
      api.setAuthTokens({ accessToken: next.token, refreshToken: null });
      try {
        window.sessionStorage.removeItem(SESSION_REFRESH_KEY);
        window.localStorage.setItem(ACTOR_STORAGE_KEY, next.token);
      } catch {
        /* storage unavailable */
      }
      let enrichedActor = next;
      try {
        const meRes = await api.getCurrentUser();
        if (meRes?.user) {
          setAuthUser(meRes.user);
          setPermissions(meRes.permissions || ANON_PERMISSIONS);
          enrichedActor = { ...buildActorFromUser(meRes.user, next.token), token: next.token };
        }
      } catch {
        setPermissions(ANON_PERMISSIONS);
      }
      actorRef.current = enrichedActor;
      setActor(enrichedActor);
      setSystem((prev) => ({ ...prev, sessionExpired: false }));
      setCart(null);
      setOrders({ status: "idle", items: [], error: null });
      await loadAccountData();
      notify({ tone: "info", title: "Account switched", message: `You're now browsing as ${enrichedActor.label}.` });
    },
    [actors, api, buildActorFromUser, loadAccountData, logout, notify]
  );

  const renewSession = useCallback(async () => {
    setSystem((prev) => ({ ...prev, sessionExpired: false }));
    if (actorRef.current) api.setToken(actorRef.current.token);
    await bootstrap();
  }, [api, bootstrap]);

  const openProduct = useCallback(
    async (productId) => {
      setUi((prev) => ({ ...prev, productId }));
      setProductDetail({ status: "loading", product: null, recommendations: [], error: null });
      try {
        const [product, recommendations] = await Promise.all([
          api.getProductDetails(productId),
          api.getRecommendations(productId).catch(() => []),
        ]);
        setProductDetail({
          status: "ready",
          product: normalizeProduct(product),
          recommendations: (Array.isArray(recommendations) ? recommendations : []).map(normalizeProduct),
          error: null,
        });
      } catch (error) {
        setProductDetail({ status: "error", product: null, recommendations: [], error });
      }
    },
    [api]
  );

  const closeProduct = useCallback(() => {
    setUi((prev) => ({ ...prev, productId: null }));
    setProductDetail({ status: "idle", product: null, recommendations: [], error: null });
  }, []);

  const submitReview = useCallback(
    async (productId, review) => {
      const updated = normalizeProduct(await api.addProductReview(productId, review));
      setProductDetail((prev) => ({ ...prev, product: updated }));
      fetchProducts(filtersRef.current, { silent: true });
      notify({ title: "Thanks for your review", message: "Your feedback helps other customers choose with confidence." });
      return updated;
    },
    [api, fetchProducts, notify]
  );

  const guardCustomer = useCallback(() => {
    if (actorRef.current?.role === "customer") return true;
    if (!actorRef.current || actorRef.current.actor_type === "anon") {
      setUi((prev) => ({ ...prev, authModalOpen: true, authModalMode: "login" }));
      notify({
        tone: "info",
        title: "Maison Sign-In Required",
        message: "Sign in or create your client profile to curate your shopping bag and place orders.",
      });
      return false;
    }
    notify({
      tone: "info",
      title: "Client Account Required",
      message: "Staff governance accounts cannot place personal orders. Sign in with a client profile to shop.",
    });
    return false;
  }, [notify]);

  const addToCart = useCallback(
    async ({ productId, size, quantity = 1, openCart = true, productName }) => {
      if (!guardCustomer()) return null;
      setBusyKey(`add:${productId}`);
      try {
        const next = await commitCart(await api.addToCart({ productId, size, quantity }));
        if (openCart) setUi((prev) => ({ ...prev, cartOpen: true, productId: null }));
        notify({
          title: "Added to your bag",
          message: `${quantity} × ${productName || productId} (size ${size})`,
        });
        return next;
      } catch (error) {
        notify({ tone: "error", title: "Couldn't add to bag", message: friendlyErrorMessage(error) });
        return null;
      } finally {
        setBusyKey(null);
      }
    },
    [api, commitCart, guardCustomer, notify]
  );

  const removeCartItem = useCallback(
    async (cartId) => {
      setBusyKey(`cart:${cartId}`);
      try {
        await commitCart(await api.removeCartItem(cartId));
      } catch (error) {
        notify({ tone: "error", title: "Couldn't update your bag", message: friendlyErrorMessage(error) });
      } finally {
        setBusyKey(null);
      }
    },
    [api, commitCart, notify]
  );

  const changeCartQuantity = useCallback(
    async (item, nextQuantity) => {
      if (nextQuantity < 1) return removeCartItem(item.cart_id);
      const delta = nextQuantity - Number(item.quantity);
      if (delta === 0) return null;
      setBusyKey(`cart:${item.cart_id}`);
      try {
        if (delta > 0) {
          await commitCart(await api.addToCart({ productId: item.product_id, size: item.size, quantity: delta }));
        } else {
          // No "set quantity" endpoint: remove the line, then re-add at the new quantity.
          await api.removeCartItem(item.cart_id);
          await commitCart(await api.addToCart({ productId: item.product_id, size: item.size, quantity: nextQuantity }));
        }
      } catch (error) {
        notify({ tone: "error", title: "Couldn't update quantity", message: friendlyErrorMessage(error) });
        await loadCart();
      } finally {
        setBusyKey(null);
      }
      return null;
    },
    [api, commitCart, loadCart, notify, removeCartItem]
  );

  const validateCoupon = useCallback(
    async (code) => {
      const subtotal = Number(cart?.subtotal_mrp_inr || 0);
      return api.validateCoupon(code, subtotal);
    },
    [api, cart]
  );

  /** Validates a code server-side, then re-prices the cart with it. Resolves to { ok, message }. */
  const applyCoupon = useCallback(
    async (rawCode) => {
      const code = String(rawCode || "").trim().toUpperCase();
      if (!code) return { ok: false, message: "Enter a promo code." };
      try {
        const result = await validateCoupon(code);
        if (result?.valid === false) return { ok: false, message: result.message || `"${code}" isn't valid.` };
        setCouponCode(code);
        await loadCart();
        return { ok: true, message: result?.message || `${code} applied.` };
      } catch (error) {
        return { ok: false, message: friendlyErrorMessage(error) };
      }
    },
    [loadCart, setCouponCode, validateCoupon]
  );

  const removeCoupon = useCallback(async () => {
    setCouponCode(null);
    await loadCart();
  }, [loadCart, setCouponCode]);

  const checkoutKeyRef = useRef(null);

  const placeOrder = useCallback(
    async ({ addressId, paymentMethod, couponCode = couponRef.current }) => {
      if (!checkoutKeyRef.current) checkoutKeyRef.current = `chk-${crypto.randomUUID()}`;
      const customerId = actorRef.current.id;

      const hold = await api.holdOrder({
        customerId,
        couponCode: couponCode || null,
        paymentMethod,
        shippingAddressId: addressId,
        requestKey: checkoutKeyRef.current,
      });

      let settled;
      try {
        settled = await api.payForOrder(hold.order_id);
      } catch (error) {
        await Promise.all([loadCart(), loadOrders()]);
        throw { ...error, stage: "payment", orderId: hold.order_id, holdSeconds: hold.expires_in_seconds };
      }

      checkoutKeyRef.current = null;
      setCouponCode(null); // the coupon has been redeemed on this order
      const order = settled.order || (await api.getOrder(hold.order_id));
      await Promise.all([loadCart(), loadOrders(), fetchProducts(filtersRef.current, { silent: true })]);
      return order;
    },
    [api, fetchProducts, loadCart, loadOrders, setCouponCode]
  );

  const payForOrder = useCallback(
    async (orderId) => {
      setBusyKey(`pay:${orderId}`);
      try {
        await api.payForOrder(orderId);
        await loadOrders();
        notify({ title: "Payment received", message: `Order ${orderId} is confirmed.` });
      } catch (error) {
        notify({ tone: "error", title: "Payment didn't go through", message: friendlyErrorMessage(error) });
        await loadOrders();
      } finally {
        setBusyKey(null);
      }
    },
    [api, loadOrders, notify]
  );

  const cancelOrder = useCallback(
    async (orderId) => {
      setBusyKey(`cancel:${orderId}`);
      try {
        const result = await api.cancelOrder(orderId, "Cancelled by customer");
        await Promise.all([loadOrders(), fetchProducts(filtersRef.current, { silent: true })]);
        notify({
          title: `Order ${orderId} cancelled`,
          message: result.refund_id
            ? "Your full refund has been issued to your original payment method."
            : "Your reserved items have been released.",
        });
      } catch (error) {
        notify({ tone: "error", title: "Couldn't cancel this order", message: friendlyErrorMessage(error) });
      } finally {
        setBusyKey(null);
      }
    },
    [api, fetchProducts, loadOrders, notify]
  );

  const refreshAfterAssistant = useCallback(
    async (res) => {
      await Promise.all([loadCart(), loadOrders(), fetchProducts(filtersRef.current, { silent: true })]);
      const feedback = res?.data?.action_feedback;
      const acted = ["action_completed", "pending_approval", "escalated"].includes(res?.status);
      if (feedback && acted) notify({ title: feedback.title, message: feedback.summary });
    },
    [fetchProducts, loadCart, loadOrders, notify]
  );

  // Business rules come from the backend config — never hard-coded in views.
  const business = config.business || {};
  const assistant = useAssistant({
    api,
    actor,
    businessConfig: business,
    agentRegistry,
    isStaff,
    onAfterAction: refreshAfterAssistant,
  });

  const askStylist = useCallback(
    (promptText = "") => {
      setUi((prev) => ({ ...prev, chatOpen: true, cartOpen: false, productId: null }));
      if (promptText && String(promptText).trim()) {
        assistant.send(String(promptText).trim());
      }
    },
    [assistant]
  );

  const hasMoreProducts = catalog.items.length < catalog.total;

  const taxRules = useMemo(() => buildTaxRules(business.tax), [business.tax]);
  const freeShippingMin = Number(business.shipping?.free_shipping_threshold_inr ?? 1999);
  const defaultShippingFee = Number(business.shipping?.default_shipping_fee_inr ?? 99);
  const cartItems = cart?.items || [];
  const cartCount = cartItems.reduce((sum, i) => sum + Number(i.quantity || 0), 0);

  // Cart totals come from the API (prices are GST-inclusive, so GST is shown, not added).
  // Fallbacks only cover the brief window before the first cart response.
  const cartSubtotal = Number(cart?.subtotal_mrp_inr ?? cartItems.reduce((sum, i) => sum + i.lineTotal, 0));
  const cartDiscount = Number(cart?.discount_inr ?? 0);
  const cartShipping = Number(
    cart?.shipping_fee_inr ?? (cartCount > 0 && cartSubtotal < freeShippingMin ? defaultShippingFee : 0)
  );
  const cartGrandTotal = Number(cart?.grand_total_inr ?? Math.max(0, cartSubtotal - cartDiscount + cartShipping));
  const cartTotals = {
    subtotal: cartSubtotal,
    discount: cartDiscount,
    gstLines: cart?.gstLines || [],
    gstTotal: Number(cart?.total_gst_inr ?? 0),
    shipping: cartShipping,
    grandTotal: cartGrandTotal,
  };

  // Dual-compatible catalog: supports both Array.isArray/iteration AND .items/.status/.error
  const catalogArray = [...visibleProducts];
  catalogArray.items = visibleProducts;
  catalogArray.status = catalog.status;
  catalogArray.error = catalog.error;
  catalogArray.total = catalog.total;
  catalogArray.interpretation = catalog.interpretation;

  // Dual-compatible cart
  const cartArray = [...cartItems];
  cartArray.items = cartItems;
  cartArray.coupon = cart?.coupon || null;

  // Dual-compatible orders
  const ordersItems = orders.items || [];
  const ordersArray = [...ordersItems];
  ordersArray.items = ordersItems;
  ordersArray.status = orders.status;
  ordersArray.error = orders.error;

  const currentActor = actor || {
    token: null,
    actor_type: "anon",
    role: "anon",
    role_name: "Guest Visitor",
    is_staff: false,
    label: "Guest Visitor",
    id: "anon",
    customerId: null,
  };

  const addCustomerAddress = async (addr) => {
    const custId = currentActor.id || currentActor.customerId || "CUS-001";
    const payload = {
      label: addr.label || "Home",
      street: addr.street,
      city: addr.city,
      state: addr.state || "Tamil Nadu",
      pin_code: addr.pin_code || addr.postal_code || addr.pinCode || "",
      is_primary: Boolean(addr.is_primary),
    };
    const res = await api.addCustomerAddress(custId, payload);
    setAddresses((prev) => [...prev, res]);
    return res;
  };

  const findCartLine = (productId, size) =>
    cartItems.find((i) => i.product_id === productId && i.size === size) || null;

  const addToBag = (product, size, qty = 1, { openCart = false } = {}) =>
    addToCart({
      productId: product.product_id,
      size: size || product.sizes_available?.[0],
      quantity: qty,
      productName: product.name,
      openCart,
    });

  const removeFromBag = async (productId, size) => {
    const line = findCartLine(productId, size);
    return line ? removeCartItem(line.cart_id) : null;
  };

  const updateQuantity = async (productId, size, qty) => {
    const line = findCartLine(productId, size);
    return line ? changeCartQuantity(line, qty) : null;
  };

  const value = {
    api,
    apiClient: api,
    system,
    isOffline: Boolean(system.offline || system.unreachable),
    isSlowNetwork: Boolean(system.slow),
    boot,
    bootstrap,
    config,
    business,
    businessConfig: business,
    storefrontConfig: business?.storefront_ui || {},
    freeShippingMin,
    taxRules,
    catalogMeta,
    refreshCatalogMeta,
    agentRegistry,
    actors,
    actorsList: actors,
    availableRoles,
    actor,
    authUser,
    currentActor,
    isAuthenticated,
    isCustomer,
    isStaff,
    permissions,
    hasPermission,
    hasAnyPermission,
    hasRole,
    login,
    registerCustomer,
    registerAdmin,
    logout,
    logoutAll,
    refreshProfile,
    openAuthModal,
    closeAuthModal,
    switchActor,
    renewSession,
    categories,
    allProducts,
    catalog: catalogArray,
    catalogTotal: catalog.total,
    hasMoreProducts,
    isLoadingMore,
    loadMoreProducts,
    searchInterpretation: catalog.interpretation,
    isLoadingCatalog: catalog.status === "loading",
    catalogError: catalog.error?.message || null,
    refreshCatalog: () => fetchProducts(filtersRef.current),
    filters,
    setFilters,
    resetFilters,
    activeDepartment: filters.department || "ALL",
    setActiveDepartment: (d) => setFilters({ department: d }),
    searchQuery: filters.q || "",
    setSearchQuery: (q) => setFilters({ q }),
    hasActiveFilters,
    reloadCatalog: () => fetchProducts(filtersRef.current),
    cart: cartArray,
    cartTotals,
    cartCount,
    addresses: addresses || [],
    customerAddresses: addresses || [],
    loadAddresses,
    addCustomerAddress,
    addToCart,
    addToBag,
    removeCartItem,
    removeFromBag,
    changeCartQuantity,
    updateQuantity,
    validateCoupon,
    appliedCoupon: cart?.coupon || null,
    applyCoupon,
    removeCoupon,
    paymentMethods: config.paymentMethods || [],
    placeOrder,
    orders: ordersArray,
    isLoadingOrders: orders.status === "loading",
    ordersError: orders.error?.message || null,
    loadOrders,
    refreshOrders: loadOrders,
    payForOrder,
    cancelOrder,
    wishlist,
    toggleWishlist,
    isWishlisted: (id) => wishlist.includes(id),
    productDetail,
    openProduct,
    closeProduct,
    submitReview,
    ui,
    setOverlay,
    activePage: ui.page || initialPage || "shop",
    navigateTo: (page) => setUi((prev) => ({ ...prev, page })),
    activeDrawer: ui.cartOpen ? "bag" : ui.chatOpen ? "ai" : null,
    openDrawer: (drawer) => setOverlay({ cartOpen: drawer === "bag", chatOpen: drawer === "ai" }),
    closeDrawer: () => setOverlay({ cartOpen: false, chatOpen: false }),
    theme,
    setTheme,
    fontScale,
    setFontScale,
    toasts,
    notify,
    dismissToast,
    removeToast: dismissToast,
    busyKey,
    assistant,
    askStylist,
    classifyApiError,
  };

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore() {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore must be used inside <StoreProvider>");
  return ctx;
}
