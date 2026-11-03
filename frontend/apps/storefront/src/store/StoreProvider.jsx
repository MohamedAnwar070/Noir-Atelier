"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { NoirApiClient } from "@noir/api/client.js";
import { applyFontScale, applyTheme, getInitialFontScale, getInitialTheme } from "@noir/ui/theme.js";
import { classifyApiError, friendlyErrorMessage } from "@noir/ui/states.js";
import { LIMITS, STAFF_ROLES } from "@/config/ui.config";
import { useAssistant } from "@/hooks/useAssistant";

const StoreContext = createContext(null);

const ACTOR_STORAGE_KEY = "noir_actor_token";
const WISHLIST_STORAGE_KEY = "noir_wishlist";
const DEFAULT_FILTERS = { q: "", department: "ALL", maxPrice: null, inStockOnly: false, sort: "featured" };

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

function sortProducts(items, sort) {
  const list = [...items];
  if (sort === "price_asc") list.sort((a, b) => Number(a.mrp_inr) - Number(b.mrp_inr));
  else if (sort === "price_desc") list.sort((a, b) => Number(b.mrp_inr) - Number(a.mrp_inr));
  else if (sort === "rating") list.sort((a, b) => Number(b.average_rating || 0) - Number(a.average_rating || 0));
  return list;
}

export function StoreProvider({ children, initialPage = "shop" }) {
  const [system, setSystem] = useState({ offline: false, unreachable: false, slow: false, sessionExpired: false });
  const [boot, setBoot] = useState({ status: "loading", error: null });
  const [config, setConfig] = useState({ business: {}, policies: [], paymentMethods: [], coupons: [], zones: [], demoMode: false });
  const [actors, setActors] = useState([]);
  const [actor, setActor] = useState(null);
  const [categories, setCategories] = useState([]);
  const [allProducts, setAllProducts] = useState([]);
  const [catalog, setCatalog] = useState({ status: "loading", items: [], error: null });
  const [filters, setFiltersState] = useState(DEFAULT_FILTERS);
  const [cart, setCart] = useState(null);
  const [addresses, setAddresses] = useState([]);
  const [orders, setOrders] = useState({ status: "idle", items: [], error: null });
  const [wishlist, setWishlist] = useState([]);
  const [toasts, setToasts] = useState([]);
  const [theme, setThemeState] = useState("light");
  const [fontScale, setFontScaleState] = useState("default");
  const [ui, setUi] = useState({ cartOpen: false, productId: null, menuOpen: false, accountOpen: false, chatOpen: false, returnOrderId: null, page: initialPage });
  const [productDetail, setProductDetail] = useState({ status: "idle", product: null, recommendations: [], error: null });
  const [busyKey, setBusyKey] = useState(null);

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

  const apiRef = useRef(null);
  if (!apiRef.current) apiRef.current = new NoirApiClient({ onNetworkEvent: (evt) => handleNetworkEvent(evt) });
  const api = apiRef.current;

  const filtersRef = useRef(filters);
  filtersRef.current = filters;
  const actorRef = useRef(actor);
  actorRef.current = actor;
  const toastTimers = useRef(new Map());

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = toastTimers.current.get(id);
    if (timer) clearTimeout(timer);
    toastTimers.current.delete(id);
  }, []);

  const notify = useCallback(
    ({ tone = "success", title, message, action }) => {
      const id = `t-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      setToasts((prev) => [...prev.slice(-2), { id, tone, title, message, action }]);
      toastTimers.current.set(id, setTimeout(() => dismissToast(id), LIMITS.toastDurationMs));
      return id;
    },
    [dismissToast]
  );

  const isCustomer = actor?.role === "customer";
  const isStaff = STAFF_ROLES.includes(actor?.role);

  const fetchProducts = useCallback(
    async (nextFilters = filtersRef.current, { silent = false } = {}) => {
      if (!silent) setCatalog((prev) => ({ ...prev, status: prev.items.length ? "refreshing" : "loading", error: null }));
      try {
        const items = await api.searchProducts({
          q: nextFilters.q,
          department: nextFilters.department,
          maxPrice: nextFilters.maxPrice,
          inStockOnly: nextFilters.inStockOnly,
        });
        setCatalog({ status: "ready", items: Array.isArray(items) ? items : [], error: null });
        return items;
      } catch (error) {
        setCatalog((prev) => ({ ...prev, status: "error", error }));
        return null;
      }
    },
    [api]
  );

  const loadCart = useCallback(async () => {
    if (actorRef.current?.role !== "customer") return null;
    try {
      const next = await api.getCart();
      setCart(next);
      return next;
    } catch {
      return null;
    }
  }, [api]);

  const loadOrders = useCallback(async () => {
    if (actorRef.current?.role !== "customer") {
      setOrders({ status: "ready", items: [], error: null });
      return [];
    }
    setOrders((prev) => ({ ...prev, status: prev.items.length ? "refreshing" : "loading", error: null }));
    try {
      const items = await api.listOrders();
      setOrders({ status: "ready", items: Array.isArray(items) ? items : [], error: null });
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
      const [cfg, cats, products, health] = await Promise.all([
        api.getPoliciesAndConfig(),
        api.listCategories(),
        api.searchProducts({}),
        api.getHealth().catch(() => ({})),
      ]);

      const actorList = cfg.actors || [];
      const savedToken = typeof window !== "undefined" ? window.localStorage.getItem(ACTOR_STORAGE_KEY) : null;
      const resolved = actorList.find((a) => a.token === savedToken) || actorList.find((a) => a.role === "customer") || actorList[0] || null;

      if (resolved) {
        api.setToken(resolved.token);
        actorRef.current = resolved;
      }

      setConfig({
        business: cfg.business_config || {},
        policies: cfg.policies || [],
        paymentMethods: cfg.payment_methods || [],
        coupons: cfg.coupons || [],
        zones: cfg.shipping_zones || [],
        demoMode: Boolean(health?.demo_mode),
      });
      setActors(actorList);
      setActor(resolved);
      setCategories(Array.isArray(cats) ? cats : []);
      setAllProducts(Array.isArray(products) ? products : []);
      setCatalog({ status: "ready", items: Array.isArray(products) ? products : [], error: null });
      setBoot({ status: "ready", error: null });
      await loadAccountData();
    } catch (error) {
      setBoot({ status: "error", error });
      setCatalog((prev) => ({ ...prev, status: "error", error }));
    }
  }, [api, loadAccountData]);

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
  }, [filters.q, filters.department, filters.maxPrice, filters.inStockOnly, boot.status, fetchProducts]);

  const setFilters = useCallback((patch) => setFiltersState((prev) => ({ ...prev, ...patch })), []);
  const resetFilters = useCallback(() => setFiltersState((prev) => ({ ...DEFAULT_FILTERS, sort: prev.sort })), []);
  const hasActiveFilters = Boolean(filters.q || filters.department !== "ALL" || filters.maxPrice || filters.inStockOnly);
  const visibleProducts = useMemo(() => sortProducts(catalog.items, filters.sort), [catalog.items, filters.sort]);

  const setOverlay = useCallback((patch) => setUi((prev) => ({ ...prev, ...patch })), []);

  const setTheme = useCallback((next) => {
    setThemeState(next);
    applyTheme(next);
  }, []);

  const setFontScale = useCallback((next) => {
    setFontScaleState(next);
    applyFontScale(next);
  }, []);

  const toggleWishlist = useCallback(
    (productId) => {
      setWishlist((prev) => {
        const next = prev.includes(productId) ? prev.filter((id) => id !== productId) : [...prev, productId];
        writeJson(WISHLIST_STORAGE_KEY, next);
        return next;
      });
    },
    []
  );

  const switchActor = useCallback(
    async (token) => {
      const next = actors.find((a) => a.token === token);
      if (!next) return;
      api.setToken(next.token);
      actorRef.current = next;
      setActor(next);
      setSystem((prev) => ({ ...prev, sessionExpired: false }));
      try {
        window.localStorage.setItem(ACTOR_STORAGE_KEY, next.token);
      } catch {
        /* storage unavailable */
      }
      setCart(null);
      setOrders({ status: "idle", items: [], error: null });
      await loadAccountData();
      notify({ tone: "info", title: "Account switched", message: `You're now browsing as ${next.label}.` });
    },
    [actors, api, loadAccountData, notify]
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
        setProductDetail({ status: "ready", product, recommendations: Array.isArray(recommendations) ? recommendations : [], error: null });
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
      const updated = await api.addProductReview(productId, review);
      setProductDetail((prev) => ({ ...prev, product: updated }));
      fetchProducts(filtersRef.current, { silent: true });
      notify({ title: "Thanks for your review", message: "Your feedback helps other customers choose with confidence." });
      return updated;
    },
    [api, fetchProducts, notify]
  );

  const guardCustomer = useCallback(() => {
    if (actorRef.current?.role === "customer") return true;
    notify({
      tone: "info",
      title: "Customer account needed",
      message: "Team accounts can't shop. Switch to a customer account to place orders.",
    });
    return false;
  }, [notify]);

  const addToCart = useCallback(
    async ({ productId, size, quantity = 1, openCart = true, productName }) => {
      if (!guardCustomer()) return null;
      setBusyKey(`add:${productId}`);
      try {
        const next = await api.addToCart({ productId, size, quantity });
        setCart(next);
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
    [api, guardCustomer, notify]
  );

  const removeCartItem = useCallback(
    async (cartId) => {
      setBusyKey(`cart:${cartId}`);
      try {
        setCart(await api.removeCartItem(cartId));
      } catch (error) {
        notify({ tone: "error", title: "Couldn't update your bag", message: friendlyErrorMessage(error) });
      } finally {
        setBusyKey(null);
      }
    },
    [api, notify]
  );

  const changeCartQuantity = useCallback(
    async (item, nextQuantity) => {
      if (nextQuantity < 1) return removeCartItem(item.cart_id);
      const delta = nextQuantity - Number(item.quantity);
      if (delta === 0) return null;
      setBusyKey(`cart:${item.cart_id}`);
      try {
        if (delta > 0) {
          setCart(await api.addToCart({ productId: item.product_id, size: item.size, quantity: delta }));
        } else {
          await api.removeCartItem(item.cart_id);
          setCart(await api.addToCart({ productId: item.product_id, size: item.size, quantity: nextQuantity }));
        }
      } catch (error) {
        notify({ tone: "error", title: "Couldn't update quantity", message: friendlyErrorMessage(error) });
        await loadCart();
      } finally {
        setBusyKey(null);
      }
      return null;
    },
    [api, loadCart, notify, removeCartItem]
  );

  const validateCoupon = useCallback(
    async (code) => {
      const subtotal = Number(cart?.subtotal_mrp_inr || 0);
      return api.validateCoupon(code, subtotal);
    },
    [api, cart]
  );

  const checkoutKeyRef = useRef(null);

  const placeOrder = useCallback(
    async ({ addressId, paymentMethod, couponCode }) => {
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
      const order = settled.order || (await api.getOrder(hold.order_id));
      await Promise.all([loadCart(), loadOrders(), fetchProducts(filtersRef.current, { silent: true })]);
      return order;
    },
    [api, fetchProducts, loadCart, loadOrders]
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
          message: result.refund_id ? "Your full refund has been issued to your original payment method." : "Your reserved items have been released.",
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

  const assistant = useAssistant({ api, actor, onAfterAction: refreshAfterAssistant });

  const business = config.business || {};
  const freeShippingMin = Number(business.shipping?.free_shipping_threshold_inr ?? 2500);
  const cartItems = cart?.items || [];
  const cartCount = cartItems.reduce((sum, i) => sum + Number(i.quantity || 0), 0);

  // Compute rich cart totals
  const rawSubtotal = cartItems.reduce(
    (sum, i) => sum + Number(i.price || i.unit_price || i.mrp_inr || 0) * Number(i.quantity || 1),
    0
  );
  const cartSubtotal = Number(cart?.summary?.subtotal_mrp_inr ?? rawSubtotal);
  const cartDiscount = Number(cart?.summary?.discount_inr ?? 0);
  const cartGst5 = Number(cart?.summary?.gst_breakdown?.gst_5_inr ?? 0);
  const cartGst12 = Number(cart?.summary?.gst_breakdown?.gst_12_inr ?? 0);
  const cartShipping = Number(
    cart?.summary?.shipping_fee_inr ?? (cartCount > 0 ? (cartSubtotal >= freeShippingMin ? 0 : 250) : 0)
  );
  const cartGrandTotal = Number(
    cart?.summary?.grand_total_inr ?? Math.max(0, cartSubtotal - cartDiscount + cartGst5 + cartGst12 + cartShipping)
  );
  const cartTotals = {
    subtotal: cartSubtotal,
    discount: cartDiscount,
    gst5: cartGst5,
    gst12: cartGst12,
    shipping: cartShipping,
    grandTotal: cartGrandTotal,
  };

  // Dual-compatible catalog: supports both Array.isArray/iteration AND .items/.status/.error
  const catalogArray = [...visibleProducts];
  catalogArray.items = visibleProducts;
  catalogArray.status = catalog.status;
  catalogArray.error = catalog.error;

  // Dual-compatible cart
  const cartArray = [...cartItems];
  cartArray.items = cartItems;
  cartArray.summary = cart?.summary || {};
  cartArray.coupon = cart?.coupon || null;

  // Dual-compatible orders
  const ordersItems = orders.items || [];
  const ordersArray = [...ordersItems];
  ordersArray.items = ordersItems;
  ordersArray.status = orders.status;
  ordersArray.error = orders.error;

  const currentActor = actor || {
    token: "demo_CUS-001",
    role: "customer",
    label: "CUS-001 · Arjun (VIP_GOLD)",
    id: "CUS-001",
    customerId: "CUS-001",
  };

  const addCustomerAddress = async (addr) => {
    const custId = currentActor.id || currentActor.customerId || "CUS-001";
    const res = await api.addCustomerAddress(custId, addr);
    setAddresses((prev) => [...prev, res]);
    return res;
  };

  const addToBag = async (product, size, qty = 1) => {
    return addToCart(product, size, qty);
  };

  const removeFromBag = async (productId, size) => {
    return removeCartItem(productId, size);
  };

  const updateQuantity = async (productId, size, qty) => {
    return changeCartQuantity(productId, size, qty);
  };

  const clearBag = () => {
    setCart(null);
  };

  const applyCouponCode = async (code) => {
    try {
      await validateCoupon(code);
      return true;
    } catch {
      return false;
    }
  };

  const removeCoupon = () => {
    if (cart) setCart({ ...cart, coupon: null });
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
    actors,
    actorsList: actors,
    actor,
    currentActor,
    isCustomer,
    isStaff,
    switchActor,
    renewSession,
    categories,
    allProducts,
    catalog: catalogArray,
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
    clearBag,
    validateCoupon,
    appliedCoupon: cart?.coupon || null,
    applyCouponCode,
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
    classifyApiError,
  };

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore() {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore must be used inside <StoreProvider>");
  return ctx;
}
