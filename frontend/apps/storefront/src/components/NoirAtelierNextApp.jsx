"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { NoirApiClient } from "@noir/api/client.js";
import {
  DESIGN_TOKENS,
  applyFontScale,
  applyTheme,
  getContrastRatio,
  getInitialTheme,
  getProductEditorialVisual,
} from "@noir/ui/theme.js";
import { UI_PRINCIPLE_STATES } from "@noir/ui/states.js";
import {
  computeGstSlabFromConfig,
  formatInr,
  validateCheckoutForm,
  validatePolicyConfigForm,
  validateReturnForm,
} from "@noir/utils/formatters.js";

function SvgIcon({ name, size = 16 }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "1.85",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": "true",
  };
  switch (name) {
    case "search":
      return (
        <span className="ui-icon">
          <svg {...common}>
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
        </span>
      );
    case "bag":
      return (
        <span className="ui-icon">
          <svg {...common}>
            <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z" />
            <path d="M3 6h18" />
            <path d="M16 10a4 4 0 0 1-8 0" />
          </svg>
        </span>
      );
    case "sparkles":
      return (
        <span className="ui-icon">
          <svg {...common}>
            <path d="M12 3l1.9 5.3L19 10l-5.1 1.7L12 17l-1.9-5.3L5 10l5.1-1.7L12 3z" />
            <path d="M5 3v4" />
            <path d="M3 5h4" />
          </svg>
        </span>
      );
    case "heart":
      return (
        <span className="ui-icon">
          <svg {...common}>
            <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
          </svg>
        </span>
      );
    case "heart-filled":
      return (
        <span className="ui-icon">
          <svg {...common}>
            <path
              fill="currentColor"
              d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"
            />
          </svg>
        </span>
      );
    case "star":
      return (
        <span className="ui-icon">
          <svg {...common}>
            <polygon
              fill="currentColor"
              points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"
            />
          </svg>
        </span>
      );
    case "sliders":
      return (
        <span className="ui-icon">
          <svg {...common}>
            <line x1="4" x2="4" y1="21" y2="14" />
            <line x1="4" x2="4" y1="10" y2="3" />
            <line x1="12" x2="12" y1="21" y2="12" />
            <line x1="12" x2="12" y1="8" y2="3" />
            <line x1="20" x2="20" y1="21" y2="16" />
            <line x1="20" x2="20" y1="12" y2="3" />
          </svg>
        </span>
      );
    case "sun":
      return (
        <span className="ui-icon">
          <svg {...common}>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2" />
            <path d="M12 20v2" />
            <path d="M2 12h2" />
            <path d="M20 12h2" />
          </svg>
        </span>
      );
    case "moon":
      return (
        <span className="ui-icon">
          <svg {...common}>
            <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
          </svg>
        </span>
      );
    case "close":
      return (
        <span className="ui-icon">
          <svg {...common}>
            <path d="M18 6 6 18" />
            <path d="m6 6 12 12" />
          </svg>
        </span>
      );
    case "check":
      return (
        <span className="ui-icon">
          <svg {...common}>
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </span>
      );
    case "shield":
      return (
        <span className="ui-icon">
          <svg {...common}>
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            <path d="m9 12 2 2 4-4" />
          </svg>
        </span>
      );
    case "lock":
      return (
        <span className="ui-icon">
          <svg {...common}>
            <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        </span>
      );
    case "key":
      return (
        <span className="ui-icon">
          <svg {...common}>
            <circle cx="7.5" cy="15.5" r="5.5" />
            <path d="m21 2-9.6 9.6" />
          </svg>
        </span>
      );
    case "alert":
      return (
        <span className="ui-icon">
          <svg {...common}>
            <circle cx="12" cy="12" r="10" />
            <line x1="12" x2="12" y1="8" y2="12" />
            <line x1="12" x2="12.01" y1="16" y2="16" />
          </svg>
        </span>
      );
    case "arrow-right":
    default:
      return (
        <span className="ui-icon">
          <svg {...common}>
            <path d="M5 12h14" />
            <path d="m12 5 7 7-7 7" />
          </svg>
        </span>
      );
  }
}

export default function NoirAtelierNextApp({ initialPage = "shop" }) {
  const router = useRouter();
  const pathname = usePathname();

  const [activePage, setActivePage] = useState(initialPage);
  const [activeDrawer, setActiveDrawer] = useState(null);
  const [detailModalProduct, setDetailModalProduct] = useState(null);
  const [showDiagnosticsBar, setShowDiagnosticsBar] = useState(false);
  const [fontScale, setFontScale] = useState("default");
  const [theme, setTheme] = useState("light");
  const [activeUiPrinciple, setActiveUiPrinciple] = useState("normal");
  const [actors, setActors] = useState([]);
  const [actor, setActor] = useState({ token: "demo_CUS-001", id: "CUS-001", role: "customer", label: "CUS-001" });
  const [inFlightAction, setInFlightAction] = useState(null);
  const [liveAnnouncement, setLiveAnnouncement] = useState("");

  const [isOffline, setIsOffline] = useState(false);
  const [slowLatencyMs, setSlowLatencyMs] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [apiError, setApiError] = useState(null);
  const [permissionDeniedInfo, setPermissionDeniedInfo] = useState(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [toastSuccess, setToastSuccess] = useState(null);

  const [businessConfig, setBusinessConfig] = useState({});
  const [policies, setPolicies] = useState([]);
  const [paymentMethods, setPaymentMethods] = useState([]);
  const [availableCoupons, setAvailableCoupons] = useState([]);
  const [shippingZones, setShippingZones] = useState([]);
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [cardSizeSelection, setCardSizeSelection] = useState({});
  const [recommendations, setRecommendations] = useState([]);
  const [wishlistIds, setWishlistIds] = useState([]);
  const [reviewForm, setReviewForm] = useState({ rating: 5, fitFeedback: "true_to_size", comment: "" });

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedDepartment, setSelectedDepartment] = useState("ALL");
  const [maxPrice, setMaxPrice] = useState("");
  const [sortBy, setSortBy] = useState("featured");

  const [cart, setCart] = useState(null);
  const [checkoutForm, setCheckoutForm] = useState({
    street: "",
    pinCode: "",
    couponCode: "",
    paymentMethod: "upi",
  });
  const [checkoutValidationErrors, setCheckoutValidationErrors] = useState({});
  const [couponResult, setCouponResult] = useState(null);

  const [orders, setOrders] = useState([]);
  const [inspectedOrderMeta, setInspectedOrderMeta] = useState(null);
  const [returnForm, setReturnForm] = useState({
    orderId: "",
    reasonNotes: "",
    tagIntact: true,
    qcPassed: true,
  });
  const [returnValidationErrors, setReturnValidationErrors] = useState({});

  const [agentRegistry, setAgentRegistry] = useState([]);
  const [agentMessages, setAgentMessages] = useState([]);
  const [agentPreferred, setAgentPreferred] = useState("");
  const [agentChatInput, setAgentChatInput] = useState("");
  const [agentBusy, setAgentBusy] = useState(false);

  const [adminDashboard, setAdminDashboard] = useState(null);
  const [adminInventory, setAdminInventory] = useState([]);
  const [adminRefunds, setAdminRefunds] = useState([]);
  const [adminAuditLog, setAdminAuditLog] = useState([]);
  const [policyConfigForm, setPolicyConfigForm] = useState({
    freeShippingThresholdInr: 1999,
    standardShippingFeeInr: 149,
    reason: "Seasonal luxury shipping threshold review",
  });
  const [policyConfigErrors, setPolicyConfigErrors] = useState({});

  const apiRef = useRef(null);
  if (!apiRef.current) {
    apiRef.current = new NoirApiClient({
      onNetworkEvent: (evt) => {
        if (evt.type === "offline") setIsOffline(true);
        else if (evt.type === "slow_network") setSlowLatencyMs(evt.latencyMs);
        else if (evt.type === "session_expired") setSessionExpired(true);
        else if (evt.type === "permission_denied") {
          setPermissionDeniedInfo({
            actorId: `${actor.id} (${actor.role})`,
            endpoint: evt.endpoint,
            message: evt.data?.message || "Insufficient permissions.",
          });
        }
      },
    });
  }

  useEffect(() => {
    const initial = getInitialTheme();
    setTheme(initial);
    applyTheme(initial);
  }, []);

  useEffect(() => {
    if (pathname === "/orders") setActivePage("orders");
    else if (pathname === "/policies") setActivePage("policies");
    else if (pathname === "/admin") setActivePage("admin");
    else setActivePage("shop");
  }, [pathname]);

  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        setDetailModalProduct(null);
        setActiveDrawer(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  async function bootstrapData(currentActor = actor, q = searchQuery, dept = selectedDepartment, mp = maxPrice) {
    setIsLoading(true);
    setApiError(null);
    setPermissionDeniedInfo(null);
    const api = apiRef.current;

    try {
      const [cfgPayload, cats, prods, currentCart, currentOrders, registry] = await Promise.all([
        api.getPoliciesAndConfig(),
        api.listCategories(),
        api.searchProducts({ q, department: dept, maxPrice: mp || null }),
        api.getCart().catch(() => null),
        api.listOrders().catch(() => []),
        api.getAgentsRegistry().catch(() => []),
      ]);

      const bCfg = cfgPayload.business_config || {};
      setBusinessConfig(bCfg);
      setPolicies(cfgPayload.policies || []);
      setPaymentMethods(cfgPayload.payment_methods || []);
      setAvailableCoupons(cfgPayload.coupons || []);
      setShippingZones(cfgPayload.shipping_zones || []);

      const dbActors = cfgPayload.actors || [];
      if (dbActors.length > 0) {
        setActors(dbActors);
        const matchActor = dbActors.find((a) => a.token === currentActor.token) || dbActors[0];
        setActor(matchActor);
      }

      setCategories(Array.isArray(cats) ? cats : []);
      const safeProds = Array.isArray(prods) ? prods : [];
      setProducts(safeProds);
      setCart(currentCart);
      const safeOrders = Array.isArray(currentOrders) ? currentOrders : [];
      setOrders(safeOrders);
      setAgentRegistry(Array.isArray(registry) ? registry : []);

      if (bCfg.shipping) {
        setPolicyConfigForm((prev) => ({
          ...prev,
          freeShippingThresholdInr: bCfg.shipping.free_shipping_threshold_inr ?? 1999,
          standardShippingFeeInr: bCfg.shipping.default_shipping_fee_inr ?? 99,
        }));
      }

      setCardSizeSelection((prev) => {
        const next = { ...prev };
        safeProds.forEach((p) => {
          if (!next[p.product_id]) {
            const sizes = p.sizes_available || [];
            next[p.product_id] = sizes.includes("M") ? "M" : sizes[0] || "M";
          }
        });
        return next;
      });

      if (currentActor.role === "customer") {
        const addresses = await api.listCustomerAddresses(currentActor.id).catch(() => []);
        if (addresses.length > 0) {
          const primary = addresses.find((a) => a.is_primary) || addresses[0];
          setCheckoutForm((prev) => ({
            ...prev,
            street: prev.street || primary.street,
            pinCode: prev.pinCode || primary.pin_code,
          }));
        }
      }

      if (safeOrders.length > 0) {
        setReturnForm((prev) => ({
          ...prev,
          orderId: prev.orderId || safeOrders[0].order_id,
        }));
      }

      setIsLoading(false);
    } catch (err) {
      setIsLoading(false);
      setApiError(err);
    }
  }

  async function loadAdminData(currentActor = actor) {
    setIsLoading(true);
    setApiError(null);
    setPermissionDeniedInfo(null);
    const api = apiRef.current;

    try {
      const [dashboard, inventory, refunds, auditLog, cfgPayload] = await Promise.all([
        api.getAdminDashboard(currentActor.token),
        api.listInventory(false, currentActor.token),
        api.listRefunds(currentActor.token),
        api.getAuditLog(20, currentActor.token),
        api.getPoliciesAndConfig(),
      ]);
      setAdminDashboard(dashboard);
      setAdminInventory(inventory);
      setAdminRefunds(refunds);
      setAdminAuditLog(auditLog);
      if (cfgPayload?.business_config) setBusinessConfig(cfgPayload.business_config);
      if (cfgPayload?.actors) setActors(cfgPayload.actors);
      setIsLoading(false);
    } catch (err) {
      setIsLoading(false);
      if (err.status === 403) {
        setPermissionDeniedInfo({
          actorId: `${currentActor.id} (${currentActor.role})`,
          endpoint: "GET /api/admin/dashboard",
          message: err.message,
        });
      } else if (err.status !== 401) {
        setApiError(err);
      }
    }
  }

  useEffect(() => {
    bootstrapData();
    if (initialPage === "admin") {
      loadAdminData();
    }
  }, []);

  const sortedProducts = useMemo(() => {
    const list = [...products];
    if (sortBy === "price_asc") list.sort((a, b) => Number(a.mrp_inr) - Number(b.mrp_inr));
    else if (sortBy === "price_desc") list.sort((a, b) => Number(b.mrp_inr) - Number(a.mrp_inr));
    else if (sortBy === "rating") list.sort((a, b) => Number(b.average_rating || 5) - Number(a.average_rating || 5));
    return list;
  }, [products, sortBy]);

  function navigateToPage(page) {
    setActivePage(page);
    setActiveUiPrinciple("normal");
    setPermissionDeniedInfo(null);
    if (page === "shop") router.push("/");
    else router.push(`/${page}`);
    if (page === "admin") loadAdminData();
  }

  async function handleDepartmentSelect(dept) {
    setActivePage("shop");
    setSelectedDepartment(dept);
    setActiveUiPrinciple("normal");
    if (pathname !== "/") router.push("/");
    await bootstrapData(actor, searchQuery, dept, maxPrice);
  }

  async function handleOpenProductModal(productId) {
    try {
      const api = apiRef.current;
      const [detail, recs] = await Promise.all([
        api.getProductDetails(productId),
        api.getRecommendations(productId).catch(() => []),
      ]);
      setDetailModalProduct(detail);
      setRecommendations(recs);
    } catch (err) {
      setApiError(err);
    }
  }

  async function handleAddToCart(productId) {
    const chosenSize = cardSizeSelection[productId] || "M";
    setInFlightAction(`add:${productId}`);
    try {
      const updatedCart = await apiRef.current.addToCart({
        productId,
        size: chosenSize,
        quantity: 1,
      });
      setCart(updatedCart);
      setDetailModalProduct(null);
      setActiveDrawer("bag");
      setToastSuccess({
        title: "Added to Atelier Bag",
        message: `${productId} (Size ${chosenSize}) added to your shopping bag.`,
      });
      setLiveAnnouncement(`${productId} size ${chosenSize} added to bag.`);
    } catch (err) {
      setApiError(err);
    } finally {
      setInFlightAction(null);
    }
  }

  async function handleSendAgentPrompt(promptText) {
    const msg = (promptText || agentChatInput || "").trim();
    if (!msg) return;
    setAgentChatInput("");
    setDetailModalProduct(null);
    setActiveDrawer("ai");
    setAgentMessages((prev) => [...prev, { role: "user", text: msg }]);
    setAgentBusy(true);

    try {
      const api = apiRef.current;
      const res = await api.chatWithAgents({
        message: msg,
        customerId: actor.role === "customer" ? actor.id : "CUS-001",
        actorRole: actor.role,
        preferredAgent: agentPreferred || null,
      });
      setAgentMessages((prev) => [
        ...prev,
        {
          role: "agent",
          routed_agent: res.routed_agent,
          service_account: res.service_account,
          status: res.status,
          trace_id: res.trace_id,
          text: res.reply,
          tool_traces: res.tool_traces || [],
          react_steps: res.react_steps || [],
          active_patterns: res.active_patterns || [],
          memory: res.memory || null,
          steps_taken: res.steps_taken || 0,
          step_budget_max: res.step_budget_max || 10,
          reflection_verified: res.reflection_verified ?? true,
        },
      ]);
      const [updatedCart, updatedOrders] = await Promise.all([
        api.getCart().catch(() => cart),
        api.listOrders().catch(() => orders),
      ]);
      setCart(updatedCart);
      setOrders(updatedOrders);
    } catch (err) {
      setAgentMessages((prev) => [
        ...prev,
        {
          role: "agent",
          routed_agent: "gateway_error",
          service_account: "none",
          status: "error",
          trace_id: err.trace_id || "TRC-ERR",
          text: err.message || "Could not reach /api/agents/chat.",
        },
      ]);
    } finally {
      setAgentBusy(false);
    }
  }

  const cartCount = (cart?.items || []).reduce((acc, i) => acc + Number(i.quantity || 0), 0);
  const storeName = businessConfig?.store?.name || "Noir Atelier";
  const heroCfg = businessConfig?.storefront_ui || {};
  const freeShipMin = businessConfig?.shipping?.free_shipping_threshold_inr ?? 1999;
  const gstThreshold = businessConfig?.tax?.garment_slab_threshold_inr ?? 2500;
  const gstLowPct = Number(businessConfig?.tax?.rate_upto_threshold ?? 0.05) * 100;
  const spotlight = products[0];
  const contrastRatio =
    theme === "dark" ? getContrastRatio("#f5f3ef", "#131312") : getContrastRatio("#181817", "#f6f4ef");

  const forceValidationDemo = activeUiPrinciple === "form_validation";
  const activeCheckoutErrors = forceValidationDemo
    ? validateCheckoutForm({ street: "abc", pinCode: "000", couponCode: "!" }).errors
    : checkoutValidationErrors;

  return (
    <div className="web-app">
      <a href="#main-content" className="skip-link">
        Skip to main garment collection
      </a>
      <div id="a11y-live-announcer" className="sr-only" aria-live="polite" aria-atomic="true">
        {liveAnnouncement}
      </div>

      <header className="site-header">
        <div className="site-header-inner">
          <div className="brand-group">
            <button className="brand-logo" onClick={() => navigateToPage("shop")}>
              {storeName}
            </button>
            <nav className="primary-nav" aria-label="Main Navigation">
              <button
                className={`nav-link ${activePage === "shop" && selectedDepartment === "ALL" ? "active" : ""}`}
                onClick={() => handleDepartmentSelect("ALL")}
              >
                The Edit
              </button>
              {categories.map((cat) => (
                <button
                  key={cat.category_id}
                  className={`nav-link ${activePage === "shop" && selectedDepartment === cat.department ? "active" : ""}`}
                  onClick={() => handleDepartmentSelect(cat.department)}
                >
                  {cat.department.charAt(0) + cat.department.slice(1).toLowerCase()}
                </button>
              ))}
              <button
                className={`nav-link ${activePage === "orders" ? "active" : ""}`}
                onClick={() => navigateToPage("orders")}
              >
                Orders & Returns ({orders.length})
              </button>
              <button
                className={`nav-link ${activePage === "policies" ? "active" : ""}`}
                onClick={() => navigateToPage("policies")}
              >
                Atelier Policies
              </button>
              <button
                className={`nav-link ${activePage === "admin" ? "active" : ""}`}
                onClick={() => navigateToPage("admin")}
              >
                Admin Console
              </button>
            </nav>
          </div>

          <div className="header-actions">
            <form
              className="header-search"
              role="search"
              onSubmit={(e) => {
                e.preventDefault();
                bootstrapData(actor, searchQuery, selectedDepartment, maxPrice);
              }}
            >
              <span className="header-search-icon">
                <SvgIcon name="search" size={14} />
              </span>
              <input
                type="search"
                aria-label="Search garments"
                placeholder="Search linen, silk, merino..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </form>

            <select
              className="header-pill-select"
              aria-label="Account profile"
              value={actor.token}
              onChange={async (e) => {
                const found = actors.find((a) => a.token === e.target.value) || actor;
                setActor(found);
                apiRef.current.setToken(found.token);
                setPermissionDeniedInfo(null);
                if (activePage === "admin") await loadAdminData(found);
                else await bootstrapData(found);
              }}
            >
              {actors.map((a) => (
                <option key={a.token} value={a.token}>
                  {a.label}
                </option>
              ))}
            </select>

            <select
              className="header-pill-select"
              aria-label="Typography scale"
              value={fontScale}
              onChange={(e) => {
                setFontScale(e.target.value);
                applyFontScale(e.target.value);
              }}
            >
              {DESIGN_TOKENS.fontScales.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.label}
                </option>
              ))}
            </select>

            <button
              className="chip-pill"
              onClick={() => {
                const next = theme === "dark" ? "light" : "dark";
                setTheme(next);
                applyTheme(next);
              }}
              title="Switch Light / Noir Dark Theme"
            >
              <SvgIcon name={theme === "dark" ? "sun" : "moon"} size={14} />
              <span>{theme === "dark" ? "Light" : "Noir"}</span>
            </button>

            <button
              className={`chip-pill ${showDiagnosticsBar ? "active" : ""}`}
              onClick={() => setShowDiagnosticsBar(!showDiagnosticsBar)}
              aria-expanded={showDiagnosticsBar}
            >
              <SvgIcon name="sliders" size={14} />
              <span>UI States</span>
            </button>

            <button
              className="btn-pill btn-pill-outline"
              style={{ padding: "0.48rem 1rem", fontSize: "var(--text-xs)" }}
              onClick={() => setActiveDrawer("ai")}
            >
              <SvgIcon name="sparkles" size={14} />
              <span>AI Stylist</span>
            </button>

            <button
              className="btn-pill"
              style={{ padding: "0.48rem 1.05rem", fontSize: "var(--text-xs)" }}
              onClick={() => setActiveDrawer("bag")}
            >
              <SvgIcon name="bag" size={14} />
              <span>Bag ({cartCount})</span>
            </button>
          </div>
        </div>

        {showDiagnosticsBar && (
          <div className="diagnostics-bar" role="region" aria-label="UI Design Principles Inspector">
            <div className="diagnostics-bar-inner">
              <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)" }}>
                UI Design Principles Inspector (Click any state to preview):
              </span>
              <div className="diagnostics-pills">
                {UI_PRINCIPLE_STATES.map((st) => (
                  <button
                    key={st.id}
                    className={`chip-pill ${activeUiPrinciple === st.id ? "active" : ""}`}
                    style={{ padding: "0.25rem 0.7rem", fontSize: 11, minHeight: 28 }}
                    onClick={() => {
                      setActiveUiPrinciple(st.id);
                      if (st.id === "form_validation") setActiveDrawer("bag");
                    }}
                  >
                    {st.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </header>

      <main id="main-content" className="main-container" tabIndex={-1}>
        {(isOffline || activeUiPrinciple === "offline") && (
          <div className="state-banner error" role="alert">
            <div>
              <strong>No Internet Connection</strong>
              <div style={{ fontSize: 11 }}>
                You are currently offline. Browsing cached catalog; checkout & agent actions are queued safely.
              </div>
            </div>
            <button
              className="btn-pill btn-pill-outline"
              style={{ padding: "0.35rem 0.9rem", fontSize: 11, minHeight: 34 }}
              onClick={() => {
                setIsOffline(false);
                setActiveUiPrinciple("normal");
                bootstrapData();
              }}
            >
              Reconnect
            </button>
          </div>
        )}

        {(slowLatencyMs || activeUiPrinciple === "slow_network") && (
          <div className="state-banner warning" role="status">
            <div>
              <strong>Slow Network Detected ({slowLatencyMs || 1640}ms)</strong>
              <div style={{ fontSize: 11 }}>
                Switched to lightweight garment previews and idempotent request keys to prevent duplicate charges.
              </div>
            </div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>LITE MODE</span>
          </div>
        )}

        {(toastSuccess || activeUiPrinciple === "success") && (
          <div className="state-banner success" role="status">
            <div style={{ display: "flex", alignItems: "center", gap: "0.65rem" }}>
              <SvgIcon name="check" size={16} />
              <div>
                <strong>{toastSuccess?.title || "Confirmed in Database"}</strong>
                <div style={{ fontSize: 11 }}>
                  {toastSuccess?.message ||
                    "Transaction committed to PostgreSQL/SQLite with HSN 61/62 GST invoice and audit_log record."}
                </div>
              </div>
            </div>
            <button
              className="chip-pill"
              style={{ padding: "0.2rem 0.65rem", minHeight: 28 }}
              onClick={() => {
                setToastSuccess(null);
                if (activeUiPrinciple === "success") setActiveUiPrinciple("normal");
              }}
            >
              Dismiss
            </button>
          </div>
        )}

        {activePage === "shop" && (
          <>
            <section className="hero-banner" aria-label="Editorial Spotlight">
              <div className="hero-content">
                <div>
                  <div className="hero-eyebrow">
                    <SvgIcon name="sparkles" size={14} />
                    <span>{heroCfg.hero_eyebrow || `${storeName} · HSN 61 & 62 Luxury Garments`}</span>
                  </div>
                  <h1 className="hero-title">{heroCfg.hero_title || "The New Edit"}</h1>
                  <p className="hero-subtitle">
                    {heroCfg.hero_subtitle || ""}{" "}
                    Complimentary express delivery above {formatInr(freeShipMin)}.
                  </p>
                  <div className="hero-cta-row">
                    <button
                      className="btn-pill"
                      onClick={() =>
                        document.getElementById("catalog-grid-anchor")?.scrollIntoView({ behavior: "smooth" })
                      }
                    >
                      <span>Explore Collection</span>
                      <SvgIcon name="arrow-right" size={14} />
                    </button>
                    <button
                      className="btn-pill btn-pill-outline"
                      style={{ background: "rgba(255,255,255,0.92)", color: "#181817", borderColor: "transparent" }}
                      onClick={() => setActiveDrawer("ai")}
                    >
                      <SvgIcon name="sparkles" size={14} />
                      <span>Shop with AI Stylist</span>
                    </button>
                  </div>
                </div>

                <div className="hero-ai-prompts">
                  <span style={{ fontSize: 11, opacity: 0.88 }}>Try asking AI:</span>
                  {(heroCfg.ai_quick_prompts || []).map((qp, idx) => (
                    <button
                      key={idx}
                      className="hero-ai-chip"
                      onClick={() => handleSendAgentPrompt(qp.prompt)}
                    >
                      "{qp.label}"
                    </button>
                  ))}
                </div>
              </div>

              <div className="hero-visual">
                {heroCfg.hero_image_url && (
                  <img
                    src={heroCfg.hero_image_url}
                    alt={heroCfg.hero_image_alt || storeName}
                  />
                )}
                {spotlight && (
                  <div className="hero-floating-card">
                    <div>
                      <div
                        style={{
                          fontSize: 10,
                          textTransform: "uppercase",
                          letterSpacing: "0.08em",
                          color: "var(--text-muted)",
                          fontWeight: 600,
                        }}
                      >
                        Featured Atelier Piece · {spotlight.department}
                      </div>
                      <div className="font-editorial" style={{ fontSize: "var(--text-lg)", fontWeight: 600 }}>
                        {spotlight.name}
                      </div>
                      <div style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
                        {formatInr(spotlight.mrp_inr)} · ★ {spotlight.average_rating ?? "5.0"}
                      </div>
                    </div>
                    <button
                      className="btn-pill"
                      style={{ padding: "0.5rem 1.1rem", fontSize: "var(--text-xs)" }}
                      onClick={() => handleOpenProductModal(spotlight.product_id)}
                    >
                      View Piece
                    </button>
                  </div>
                )}
              </div>
            </section>

            <section className="catalog-section" aria-label="Garment Catalog">
              <div className="catalog-toolbar">
                <div className="catalog-heading-group">
                  <h2>Trending Now</h2>
                  <span style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
                    {products.length} tailored pieces available
                  </span>
                </div>
                {(searchQuery || selectedDepartment !== "ALL" || maxPrice) && (
                  <button
                    className="section-link"
                    onClick={() => {
                      setSearchQuery("");
                      setSelectedDepartment("ALL");
                      setMaxPrice("");
                      setActiveUiPrinciple("normal");
                      bootstrapData(actor, "", "ALL", "");
                    }}
                  >
                    <span>Reset all filters</span>
                    <SvgIcon name="close" size={14} />
                  </button>
                )}
              </div>

              <div className="catalog-filters-row">
                <div className="category-pills" role="tablist">
                  <button
                    className={`chip-pill ${selectedDepartment === "ALL" ? "active" : ""}`}
                    onClick={() => handleDepartmentSelect("ALL")}
                  >
                    All Garments
                  </button>
                  {categories.map((c) => (
                    <button
                      key={c.category_id}
                      className={`chip-pill ${selectedDepartment === c.department ? "active" : ""}`}
                      onClick={() => handleDepartmentSelect(c.department)}
                    >
                      {c.name} ({c.product_count})
                    </button>
                  ))}
                  <button
                    className={`chip-pill ${Number(maxPrice) === Number(gstThreshold) ? "active" : ""}`}
                    onClick={() => {
                      const nextMp = Number(maxPrice) === Number(gstThreshold) ? "" : String(gstThreshold);
                      setMaxPrice(nextMp);
                      bootstrapData(actor, searchQuery, selectedDepartment, nextMp);
                    }}
                  >
                    Under {formatInr(gstThreshold)} ({gstLowPct}% GST Slab)
                  </button>
                </div>

                <div className="filter-controls">
                  <select
                    className="header-pill-select"
                    aria-label="Sort garments"
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value)}
                  >
                    <option value="featured">Sort: Featured</option>
                    <option value="price_asc">Price: Low to High</option>
                    <option value="price_desc">Price: High to Low</option>
                    <option value="rating">Highest Rated</option>
                  </select>
                </div>
              </div>

              {isLoading || activeUiPrinciple === "loading" ? (
                <div className="catalog-grid">
                  {[1, 2, 3, 4].map((n) => (
                    <div
                      key={n}
                      style={{
                        background: "var(--bg-surface)",
                        borderRadius: "var(--card-radius)",
                        padding: "1rem",
                        border: "1px solid var(--border-subtle)",
                      }}
                    >
                      <div className="shimmer" style={{ height: 260, borderRadius: 18, marginBottom: "0.85rem" }} />
                      <div className="shimmer" style={{ height: 15, width: "78%", borderRadius: 6, marginBottom: 8 }} />
                      <div className="shimmer" style={{ height: 12, width: "48%", borderRadius: 6 }} />
                    </div>
                  ))}
                </div>
              ) : sessionExpired || activeUiPrinciple === "session_expired" ? (
                <div className="state-card">
                  <div className="state-icon-badge">
                    <SvgIcon name="key" size={22} />
                  </div>
                  <h3 className="font-editorial" style={{ fontSize: "var(--text-xl)", marginBottom: "0.35rem" }}>
                    Session Expired (HTTP 401)
                  </h3>
                  <p style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", marginBottom: "1rem" }}>
                    Your JWT access token has expired. Your bag and session state are preserved.
                  </p>
                  <button
                    className="btn-pill"
                    onClick={() => {
                      setSessionExpired(false);
                      setActiveUiPrinciple("normal");
                      bootstrapData();
                    }}
                  >
                    Re-Authenticate Session ({actor.id})
                  </button>
                </div>
              ) : activeUiPrinciple === "permission_denied" ? (
                <div className="state-card">
                  <div className="state-icon-badge">
                    <SvgIcon name="lock" size={22} />
                  </div>
                  <h3 className="font-editorial" style={{ fontSize: "var(--text-xl)", marginBottom: "0.35rem" }}>
                    Permission Denied (HTTP 403)
                  </h3>
                  <p style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", marginBottom: "1rem" }}>
                    Actor <strong>{actor.id}</strong> is not authorized to mutate store policies.
                  </p>
                  <button
                    className="btn-pill"
                    onClick={() => {
                      const mgr = actors.find((a) => a.role === "manager") || actor;
                      setActor(mgr);
                      apiRef.current.setToken(mgr.token);
                      setActiveUiPrinciple("normal");
                      bootstrapData(mgr);
                    }}
                  >
                    Switch to Store Manager Token
                  </button>
                </div>
              ) : apiError || activeUiPrinciple === "error" ? (
                <div className="state-card">
                  <div className="state-icon-badge">
                    <SvgIcon name="alert" size={22} />
                  </div>
                  <h3 className="font-editorial" style={{ fontSize: "var(--text-xl)", marginBottom: "0.35rem" }}>
                    Something Went Wrong
                  </h3>
                  <p style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", marginBottom: "1rem" }}>
                    {apiError?.message || "Could not fetch catalog from /api/products/search."}
                  </p>
                  <button className="btn-pill" onClick={() => bootstrapData()}>
                    Retry Request
                  </button>
                </div>
              ) : activeUiPrinciple === "empty" ? (
                <div className="state-card">
                  <div className="state-icon-badge">
                    <SvgIcon name="bag" size={22} />
                  </div>
                  <h3 className="font-editorial" style={{ fontSize: "var(--text-xl)", marginBottom: "0.35rem" }}>
                    Collection Currently Empty
                  </h3>
                  <p style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", marginBottom: "1rem" }}>
                    Click below to reload all Men, Women, and Kids garments from the database.
                  </p>
                  <button className="btn-pill" onClick={() => setActiveUiPrinciple("normal")}>
                    Reload Catalog
                  </button>
                </div>
              ) : sortedProducts.length === 0 || activeUiPrinciple === "no_results" ? (
                <div className="state-card">
                  <div className="state-icon-badge">
                    <SvgIcon name="search" size={22} />
                  </div>
                  <h3 className="font-editorial" style={{ fontSize: "var(--text-xl)", marginBottom: "0.35rem" }}>
                    No Matching Garments
                  </h3>
                  <p style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", marginBottom: "1rem" }}>
                    No garments matched your active filters. Try resetting filters to browse all collections.
                  </p>
                  <button
                    className="btn-pill"
                    onClick={() => {
                      setSearchQuery("");
                      setSelectedDepartment("ALL");
                      setMaxPrice("");
                      setActiveUiPrinciple("normal");
                      bootstrapData(actor, "", "ALL", "");
                    }}
                  >
                    Reset All Filters
                  </button>
                </div>
              ) : (
                <div className="catalog-grid" id="catalog-grid-anchor">
                  {sortedProducts.map((p) => {
                    const visual = getProductEditorialVisual(p);
                    const taxInfo = computeGstSlabFromConfig(p.mrp_inr, businessConfig?.tax || {});
                    const isLiked = wishlistIds.includes(p.product_id);
                    const activeSize = cardSizeSelection[p.product_id] || (p.sizes_available || [])[0] || "M";
                    const sizeBreakdown = p.size_breakdown || {};
                    const isAddingThis = inFlightAction === `add:${p.product_id}`;

                    return (
                      <article key={p.product_id} className="product-card">
                        <div
                          className="product-card-media"
                          style={{ background: visual.bgGradient }}
                          onClick={() => handleOpenProductModal(p.product_id)}
                        >
                          <div className="card-top-badges">
                            <span className="rating-badge">
                              <SvgIcon name="star" size={13} />
                              <span>{p.average_rating ?? "5.0"}</span>
                            </span>
                            <button
                              className={`heart-btn ${isLiked ? "liked" : ""}`}
                              aria-label={`Save ${p.name} to wishlist`}
                              onClick={(e) => {
                                e.stopPropagation();
                                setWishlistIds((prev) =>
                                  prev.includes(p.product_id)
                                    ? prev.filter((id) => id !== p.product_id)
                                    : [...prev, p.product_id]
                                );
                              }}
                            >
                              <SvgIcon name={isLiked ? "heart-filled" : "heart"} size={16} />
                            </button>
                          </div>
                          {visual.photoUrl && <img src={visual.photoUrl} alt={p.name} loading="lazy" />}
                        </div>

                        <div className="product-card-body">
                          <div>
                            <div
                              style={{
                                display: "flex",
                                justifyContent: "space-between",
                                alignItems: "center",
                                marginBottom: "0.25rem",
                              }}
                            >
                              <span className="product-card-dept">
                                {p.department} · {p.product_id}
                              </span>
                              <span className="meta-tag">{visual.accentTag}</span>
                            </div>
                            <h3 className="product-card-title" onClick={() => handleOpenProductModal(p.product_id)}>
                              {p.name}
                            </h3>
                            <p className="product-card-desc" style={{ marginTop: "0.35rem" }}>
                              {p.description}
                            </p>
                          </div>

                          <div>
                            <div
                              style={{
                                display: "flex",
                                justifyContent: "space-between",
                                alignItems: "center",
                                marginBottom: "0.35rem",
                              }}
                            >
                              <span className="field-label" style={{ fontSize: 10 }}>
                                Select Size
                              </span>
                              <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{p.stock} in stock</span>
                            </div>
                            <div className="product-card-sizes" style={{ marginBottom: "0.85rem" }}>
                              {(p.sizes_available || []).map((sz) => {
                                const qty = sizeBreakdown[sz] ?? p.stock;
                                return (
                                  <button
                                    key={sz}
                                    className={`size-pill ${activeSize === sz ? "active" : ""}`}
                                    style={{ minWidth: 38, height: 32, padding: "0 0.55rem", fontSize: 11 }}
                                    disabled={qty <= 0}
                                    onClick={() =>
                                      setCardSizeSelection((prev) => ({
                                        ...prev,
                                        [p.product_id]: sz,
                                      }))
                                    }
                                  >
                                    {sz}
                                  </button>
                                );
                              })}
                            </div>

                            <div className="product-card-footer">
                              <div>
                                <div className="product-price">{formatInr(p.mrp_inr)}</div>
                                <div className="product-gst-sub">
                                  HSN {p.hsn_code} · {taxInfo.label}
                                </div>
                              </div>
                              <button
                                className="btn-pill"
                                style={{ padding: "0.62rem 1.25rem", fontSize: "var(--text-xs)" }}
                                disabled={p.stock <= 0 || isAddingThis}
                                onClick={() => handleAddToCart(p.product_id)}
                              >
                                {isAddingThis ? "Adding..." : "Add to Cart"}
                              </button>
                            </div>
                          </div>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </section>
          </>
        )}

        {activePage === "orders" && (
          <div className="page-grid-2col">
            <div className="surface-card">
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "1.1rem",
                }}
              >
                <div>
                  <h2 className="font-editorial" style={{ fontSize: "var(--text-2xl)" }}>
                    Your Orders & Shipments
                  </h2>
                  <p style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
                    Showing live database orders for <strong>{actor.label}</strong>
                  </p>
                </div>
                <button className="chip-pill" onClick={() => navigateToPage("shop")}>
                  + New Order
                </button>
              </div>

              {inspectedOrderMeta && (
                <div
                  style={{
                    padding: "0.9rem",
                    borderRadius: 16,
                    background: "var(--state-info-bg)",
                    color: "var(--state-info-text)",
                    border: "1px solid var(--state-info-border)",
                    marginBottom: "1rem",
                    fontSize: 12,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <strong>{inspectedOrderMeta.title}</strong>
                    <button className="chip-pill" onClick={() => setInspectedOrderMeta(null)}>
                      Close
                    </button>
                  </div>
                  <pre style={{ marginTop: 6, fontFamily: "var(--font-mono)", fontSize: 11, whiteSpace: "pre-wrap" }}>
                    {JSON.stringify(inspectedOrderMeta.data, null, 2)}
                  </pre>
                </div>
              )}

              {orders.length === 0 ? (
                <div className="state-card">
                  <h3 className="font-editorial" style={{ fontSize: "var(--text-xl)", marginBottom: "0.4rem" }}>
                    No Orders Found
                  </h3>
                  <button className="btn-pill" onClick={() => navigateToPage("shop")}>
                    Explore Garments
                  </button>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
                  {orders.map((o) => (
                    <div
                      key={o.order_id}
                      style={{
                        padding: "1.1rem",
                        borderRadius: 18,
                        background: "var(--bg-page)",
                        border: "1px solid var(--border-subtle)",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          marginBottom: "0.45rem",
                          flexWrap: "wrap",
                          gap: "0.5rem",
                        }}
                      >
                        <div>
                          <strong>{o.order_id}</strong>
                          <span style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", marginLeft: 8 }}>
                            Invoice: {o.invoice_id || "—"}
                          </span>
                        </div>
                        <div style={{ display: "flex", gap: "0.4rem" }}>
                          <span className="meta-tag">Status: {o.status}</span>
                          <span className="meta-tag">Payment: {o.payment_status}</span>
                        </div>
                      </div>
                      <div style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", marginBottom: 10 }}>
                        {(o.items || [])
                          .map((i) => `${i.quantity}x ${i.product_name} (Size ${i.size}, GST ${i.gst_rate_pct}%)`)
                          .join(" · ")}
                      </div>
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          paddingTop: "0.65rem",
                          borderTop: "1px solid var(--border-subtle)",
                          flexWrap: "wrap",
                          gap: "0.5rem",
                        }}
                      >
                        <div style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>
                          Grand Total: {formatInr(o.grand_total_inr)}
                        </div>
                        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                          {o.invoice_id && (
                            <button
                              className="chip-pill"
                              onClick={async () => {
                                const inv = await apiRef.current.getInvoice(o.order_id);
                                setInspectedOrderMeta({ title: `GST Tax Invoice (${inv.invoice_id})`, data: inv });
                              }}
                            >
                              GST Invoice
                            </button>
                          )}
                          <button
                            className="chip-pill"
                            onClick={() => setReturnForm((prev) => ({ ...prev, orderId: o.order_id }))}
                          >
                            Initiate Return
                          </button>
                          {(o.status === "confirmed" || o.status === "processing") && (
                            <button
                              className="chip-pill"
                              style={{ color: "var(--state-error-text)", borderColor: "var(--state-error-border)" }}
                              onClick={async () => {
                                await apiRef.current.cancelOrder(o.order_id);
                                const nextOrders = await apiRef.current.listOrders();
                                setOrders(nextOrders);
                                setToastSuccess({
                                  title: `Order ${o.order_id} Cancelled (Tier 0)`,
                                  message: "Pre-shipment cancellation auto-refunded under POL-CAN-01.",
                                });
                              }}
                            >
                              Cancel Order (Tier 0)
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="surface-card">
              <h3 className="font-editorial" style={{ fontSize: "var(--text-2xl)", marginBottom: "0.35rem" }}>
                4-Tier Garment Return & Physical QC
              </h3>
              <p style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", marginBottom: "1.1rem" }}>
                Tier 1 (≤ {formatInr(businessConfig?.returns_and_refunds?.tiers?.tier_1_auto_refund_max_inr ?? 5000)})
                auto-refunds upon QC pass; Tier 2 routes to Store Manager; Tier 3 requires Manager + Finance dual
                approval.
              </p>

              <form
                style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}
                onSubmit={async (e) => {
                  e.preventDefault();
                  const check = validateReturnForm(returnForm);
                  setReturnValidationErrors(check.errors);
                  if (!check.valid) return;
                  try {
                    const res = await apiRef.current.initiateReturn({
                      orderId: returnForm.orderId.trim().toUpperCase(),
                      reasonCategory: "size_mismatch",
                      customerNotes: returnForm.reasonNotes,
                      tagIntact: returnForm.tagIntact,
                      qcPassed: true,
                    });
                    const nextOrders = await apiRef.current.listOrders();
                    setOrders(nextOrders);
                    setToastSuccess({
                      title: `Return ${res.return_id} Recorded (Tier ${res.approval_tier})`,
                      message: `Refund ${res.refund_id} status: ${res.refund_status}`,
                    });
                  } catch (err) {
                    setApiError(err);
                  }
                }}
              >
                <div className="field-group">
                  <label className="field-label" htmlFor="next-ret-ord">
                    Order ID *
                  </label>
                  <input
                    id="next-ret-ord"
                    className={`field-input ${returnValidationErrors.orderId ? "invalid" : ""}`}
                    value={returnForm.orderId}
                    onChange={(e) => setReturnForm({ ...returnForm, orderId: e.target.value })}
                    placeholder="ORD-1001"
                  />
                  {returnValidationErrors.orderId && (
                    <span className="field-error">{returnValidationErrors.orderId}</span>
                  )}
                </div>

                <div className="field-group">
                  <label className="field-label" htmlFor="next-ret-notes">
                    Reason & Fit Feedback *
                  </label>
                  <input
                    id="next-ret-notes"
                    className={`field-input ${returnValidationErrors.reasonNotes ? "invalid" : ""}`}
                    value={returnForm.reasonNotes}
                    onChange={(e) => setReturnForm({ ...returnForm, reasonNotes: e.target.value })}
                    placeholder="Slightly tight across shoulders"
                  />
                  {returnValidationErrors.reasonNotes && (
                    <span className="field-error">{returnValidationErrors.reasonNotes}</span>
                  )}
                </div>

                <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "var(--text-xs)" }}>
                  <input
                    type="checkbox"
                    checked={returnForm.tagIntact}
                    onChange={(e) => setReturnForm({ ...returnForm, tagIntact: e.target.checked })}
                  />
                  <span>Noir Atelier security ribbon & garment tags intact (POL-RET-01)</span>
                </label>
                {returnValidationErrors.tagIntact && (
                  <span className="field-error">{returnValidationErrors.tagIntact}</span>
                )}

                <button type="submit" className="btn-pill">
                  <SvgIcon name="shield" size={14} />
                  <span>Submit Return Request</span>
                </button>
              </form>
            </div>
          </div>
        )}

        {activePage === "policies" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div className="surface-card kpi-section">
              <h2 className="font-editorial" style={{ fontSize: "var(--text-3xl)", marginBottom: "0.4rem" }}>
                Noir Atelier Governance & Store Policies
              </h2>
              <p style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
                Loaded dynamically from PostgreSQL/SQLite <code>business_config</code>, <code>policies</code>,{" "}
                <code>shipping_zones</code>, and <code>payment_methods</code> tables.
              </p>
              <div className="kpi-row" style={{ marginTop: "1.25rem", marginBottom: 0 }}>
                <div className="kpi-tile">
                  <div className="kpi-tile-label">
                    HSN 61/62 Slab ≤ ₹{businessConfig?.tax?.garment_slab_threshold_inr ?? 2500}
                  </div>
                  <div className="kpi-tile-value">
                    {Number(businessConfig?.tax?.rate_upto_threshold ?? 0.05) * 100}% GST
                  </div>
                </div>
                <div className="kpi-tile">
                  <div className="kpi-tile-label">
                    HSN 61/62 Slab &gt; ₹{businessConfig?.tax?.garment_slab_threshold_inr ?? 2500}
                  </div>
                  <div className="kpi-tile-value">
                    {Number(businessConfig?.tax?.rate_above_threshold ?? 0.18) * 100}% GST
                  </div>
                </div>
                <div className="kpi-tile">
                  <div className="kpi-tile-label">Complimentary Shipping</div>
                  <div className="kpi-tile-value">≥ {formatInr(freeShipMin)}</div>
                </div>
                <div className="kpi-tile">
                  <div className="kpi-tile-label">Return Window</div>
                  <div className="kpi-tile-value">
                    {businessConfig?.returns_and_refunds?.return_window_days ?? 7} Days
                  </div>
                </div>
              </div>
            </div>

            <div className="catalog-grid">
              {policies.map((pol) => (
                <div key={pol.policy_id} className="surface-card">
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: "0.5rem",
                    }}
                  >
                    <span className="chip-pill active" style={{ fontSize: 10 }}>
                      {pol.policy_id}
                    </span>
                    <span className="meta-tag">
                      {pol.topic} · v{pol.version}
                    </span>
                  </div>
                  <h3 className="font-editorial" style={{ fontSize: "var(--text-xl)", marginBottom: "0.45rem" }}>
                    {pol.title}
                  </h3>
                  <p style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                    {pol.rule_text}
                  </p>
                </div>
              ))}
            </div>

            {shippingZones.length > 0 && (
              <div className="surface-card">
                <h3 className="font-editorial" style={{ fontSize: "var(--text-2xl)", marginBottom: "0.75rem" }}>
                  Active Courier Shipping Zones (Database <code>shipping_zones</code> Table)
                </h3>
                <div className="kpi-row" style={{ marginBottom: 0 }}>
                  {shippingZones.map((z) => (
                    <div key={z.zone_id} className="kpi-tile">
                      <div className="kpi-tile-label">
                        {z.zone_id} · {z.name}
                      </div>
                      <div style={{ fontWeight: 700, marginTop: 4 }}>
                        {formatInr(z.base_fee_inr)} · {z.estimated_days} Days ETA
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>
                        PIN Prefixes: {(z.pin_prefixes || []).join(", ")}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {activePage === "admin" && (
          <>
            {permissionDeniedInfo || actor.role === "customer" ? (
              <div className="state-card">
                <div className="state-icon-badge">
                  <SvgIcon name="lock" size={22} />
                </div>
                <h3 className="font-editorial" style={{ fontSize: "var(--text-xl)", marginBottom: "0.35rem" }}>
                  Permission Denied (HTTP 403)
                </h3>
                <p style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", marginBottom: "1rem" }}>
                  Actor <strong>{actor.label}</strong> is not authorized to access <code>GET /api/admin/dashboard</code>
                  .
                </p>
                <button
                  className="btn-pill"
                  onClick={() => {
                    const mgr = actors.find((a) => a.role === "manager") || actor;
                    setActor(mgr);
                    apiRef.current.setToken(mgr.token);
                    setPermissionDeniedInfo(null);
                    loadAdminData(mgr);
                  }}
                >
                  Switch to Store Manager Token
                </button>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
                <div className="surface-card kpi-section">
                  <h2 className="font-editorial" style={{ fontSize: "var(--text-3xl)", marginBottom: "0.5rem" }}>
                    Admin Governance Console
                  </h2>
                  <div className="kpi-row" style={{ marginBottom: 0 }}>
                    <div className="kpi-tile">
                      <div className="kpi-tile-label">Total Orders</div>
                      <div className="kpi-tile-value">{adminDashboard?.orders?.total_orders ?? 0}</div>
                    </div>
                    <div className="kpi-tile">
                      <div className="kpi-tile-label">Cumulative Revenue</div>
                      <div className="kpi-tile-value">
                        {formatInr(adminDashboard?.orders?.total_revenue_inr ?? 0)}
                      </div>
                    </div>
                    <div className="kpi-tile">
                      <div className="kpi-tile-label">Registered Customers</div>
                      <div className="kpi-tile-value">{adminDashboard?.customers?.total_customers ?? 0}</div>
                    </div>
                    <div className="kpi-tile">
                      <div className="kpi-tile-label">Repeat Buyer Retention</div>
                      <div className="kpi-tile-value">{adminDashboard?.customers?.retention_rate_pct ?? 0}%</div>
                    </div>
                  </div>
                </div>

                <div className="page-grid-2col">
                  <div className="surface-card">
                    <h3 className="font-editorial" style={{ fontSize: "var(--text-2xl)", marginBottom: "0.75rem" }}>
                      4-Tier Refund Approval Queue
                    </h3>
                    {adminRefunds.length === 0 ? (
                      <p style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
                        No refund requests in queue.
                      </p>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
                        {adminRefunds.map((r) => (
                          <div
                            key={r.refund_id}
                            style={{
                              padding: "0.9rem",
                              borderRadius: 16,
                              background: "var(--bg-page)",
                              border: "1px solid var(--border-subtle)",
                              fontSize: 12,
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 600 }}>
                              <span>
                                {r.refund_id} · Order {r.order_id} · {formatInr(r.amount_inr)}
                              </span>
                              <span className="meta-tag">
                                Tier {r.approval_tier} · {r.status}
                              </span>
                            </div>
                            <div style={{ display: "flex", gap: "0.45rem", marginTop: "0.5rem" }}>
                              {(r.status === "pending_approval" || r.status === "awaiting_secondary_approval") && (
                                <button
                                  className="btn-pill"
                                  style={{ padding: "0.35rem 0.85rem", fontSize: 11, minHeight: 32 }}
                                  onClick={async () => {
                                    await apiRef.current.approveRefund(
                                      r.refund_id,
                                      `Approved by ${actor.id}`,
                                      actor.token
                                    );
                                    await loadAdminData(actor);
                                  }}
                                >
                                  Approve as {actor.role}
                                </button>
                              )}
                              {r.status === "approved" && (
                                <button
                                  className="btn-pill btn-pill-outline"
                                  style={{ padding: "0.35rem 0.85rem", fontSize: 11, minHeight: 32 }}
                                  onClick={async () => {
                                    await apiRef.current.processRefund(r.refund_id, actor.token);
                                    await loadAdminData(actor);
                                  }}
                                >
                                  Disburse Payout & Restock
                                </button>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="surface-card">
                    <h3 className="font-editorial" style={{ fontSize: "var(--text-2xl)", marginBottom: "0.75rem" }}>
                      Warehouse Garment Inventory
                    </h3>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                      {adminInventory.map((inv) => (
                        <div
                          key={inv.product_id}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            padding: "0.75rem 0.9rem",
                            borderRadius: 14,
                            background: "var(--bg-page)",
                            border: "1px solid var(--border-subtle)",
                            fontSize: 12,
                          }}
                        >
                          <div>
                            <strong>{inv.product_id}</strong> · {inv.name}
                            <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                              Available: {inv.quantity_available} · Reserved: {inv.quantity_reserved}
                            </div>
                          </div>
                          <button
                            className="chip-pill"
                            onClick={async () => {
                              await apiRef.current.updateInventory(
                                inv.product_id,
                                Number(inv.quantity_available) + 10,
                                "admin_portal_restock",
                                actor.token
                              );
                              await loadAdminData(actor);
                            }}
                          >
                            +10 Units
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="surface-card">
                  <h3 className="font-editorial" style={{ fontSize: "var(--text-2xl)", marginBottom: "0.4rem" }}>
                    Live Business Config Policy Editor (<code>PUT /api/admin/config/policies</code>)
                  </h3>
                  <form
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                      gap: "0.85rem",
                      alignItems: "end",
                    }}
                    onSubmit={async (e) => {
                      e.preventDefault();
                      const check = validatePolicyConfigForm(policyConfigForm);
                      setPolicyConfigErrors(check.errors);
                      if (!check.valid) return;
                      await apiRef.current.updateBusinessConfig(
                        "shipping",
                        {
                          free_shipping_threshold_inr: Number(policyConfigForm.freeShippingThresholdInr),
                          default_shipping_fee_inr: Number(policyConfigForm.standardShippingFeeInr),
                          cod_allowed: false,
                        },
                        policyConfigForm.reason,
                        actor.token
                      );
                      setToastSuccess({
                        title: "Database Policy Config Updated",
                        message: `Complimentary shipping threshold updated to ₹${policyConfigForm.freeShippingThresholdInr}.`,
                      });
                      await loadAdminData(actor);
                    }}
                  >
                    <div className="field-group">
                      <label className="field-label" htmlFor="next-cfg-free">
                        Free Shipping Threshold (₹) *
                      </label>
                      <input
                        id="next-cfg-free"
                        className="field-input"
                        type="number"
                        value={policyConfigForm.freeShippingThresholdInr}
                        onChange={(e) =>
                          setPolicyConfigForm({ ...policyConfigForm, freeShippingThresholdInr: e.target.value })
                        }
                      />
                    </div>
                    <div className="field-group">
                      <label className="field-label" htmlFor="next-cfg-fee">
                        Standard Courier Fee (₹) *
                      </label>
                      <input
                        id="next-cfg-fee"
                        className="field-input"
                        type="number"
                        value={policyConfigForm.standardShippingFeeInr}
                        onChange={(e) =>
                          setPolicyConfigForm({ ...policyConfigForm, standardShippingFeeInr: e.target.value })
                        }
                      />
                    </div>
                    <div className="field-group">
                      <label className="field-label" htmlFor="next-cfg-reason">
                        Governance Audit Reason *
                      </label>
                      <input
                        id="next-cfg-reason"
                        className="field-input"
                        type="text"
                        value={policyConfigForm.reason}
                        onChange={(e) => setPolicyConfigForm({ ...policyConfigForm, reason: e.target.value })}
                      />
                    </div>
                    <button type="submit" className="btn-pill">
                      <SvgIcon name="check" size={14} />
                      <span>Save to Database</span>
                    </button>
                  </form>
                </div>
              </div>
            )}
          </>
        )}
      </main>

      <footer className="site-footer">
        <div className="site-footer-inner">
          <div>
            <strong>{storeName}</strong> · Next.js 14+ App Router & FastAPI Unified Commerce Platform
          </div>
          <div style={{ display: "flex", gap: "1.25rem", flexWrap: "wrap", fontFamily: "var(--font-mono)", fontSize: 11 }}>
            <span>WCAG 2.2 AAA Contrast: {contrastRatio}:1</span>
            <span>4-Layer ReAct Loop · 9 Agents</span>
            <span>3-Tier Design Tokens ({theme.toUpperCase()})</span>
          </div>
        </div>
      </footer>

      {detailModalProduct && (
        <div className="detail-modal-backdrop" onClick={() => setDetailModalProduct(null)}>
          <div
            className="detail-modal-sheet"
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="detail-modal-media">
              <div className="card-top-badges">
                <span className="rating-badge">
                  <SvgIcon name="star" size={13} />
                  <span>
                    {detailModalProduct.average_rating ?? "5.0"} ({detailModalProduct.review_count || 1} verified review)
                  </span>
                </span>
                <button className="heart-btn" onClick={() => setDetailModalProduct(null)}>
                  <SvgIcon name="close" size={16} />
                </button>
              </div>
              {getProductEditorialVisual(detailModalProduct).photoUrl && (
                <img
                  src={getProductEditorialVisual(detailModalProduct).photoUrl}
                  alt={detailModalProduct.name}
                />
              )}
            </div>

            <div className="detail-modal-content">
              <div>
                <span className="product-card-dept">
                  {detailModalProduct.department} COLLECTION · {detailModalProduct.sku}
                </span>
                <h2 className="font-editorial" style={{ fontSize: "var(--text-3xl)", margin: "0.4rem 0 0.6rem" }}>
                  {detailModalProduct.name}
                </h2>
                <p style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", marginBottom: "1.1rem" }}>
                  {detailModalProduct.description}
                </p>

                {recommendations.length > 0 && (
                  <div style={{ marginBottom: "1rem" }}>
                    <div className="field-label" style={{ marginBottom: "0.4rem" }}>
                      Complete the Look (Database <code>recommendations</code> Table)
                    </div>
                    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                      {recommendations.map((rec) => (
                        <button
                          key={rec.product_id}
                          className="chip-pill"
                          onClick={() => handleOpenProductModal(rec.product_id)}
                        >
                          <span>
                            {rec.name} · {formatInr(rec.mrp_inr)}
                          </span>
                          <SvgIcon name="arrow-right" size={12} />
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div style={{ marginBottom: "1rem" }}>
                  <div className="field-label" style={{ marginBottom: "0.4rem" }}>
                    Verified Customer Reviews (Database <code>product_reviews</code> Table)
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", marginBottom: "0.6rem" }}>
                    {(detailModalProduct.reviews || []).slice(0, 3).map((rev) => (
                      <div
                        key={rev.review_id}
                        style={{
                          padding: "0.55rem 0.75rem",
                          borderRadius: 12,
                          background: "var(--bg-subtle)",
                          fontSize: 11,
                        }}
                      >
                        <strong>★ {rev.rating}.0</strong> · {rev.customer_id} ({rev.fit_feedback}): "{rev.comment}"
                      </div>
                    ))}
                  </div>
                  <form
                    style={{ display: "flex", gap: "0.4rem" }}
                    onSubmit={async (e) => {
                      e.preventDefault();
                      if (!reviewForm.comment.trim()) return;
                      const updatedProd = await apiRef.current.addProductReview(detailModalProduct.product_id, {
                        rating: reviewForm.rating,
                        fitFeedback: reviewForm.fitFeedback,
                        comment: reviewForm.comment,
                      });
                      setDetailModalProduct(updatedProd);
                      setReviewForm({ rating: 5, fitFeedback: "true_to_size", comment: "" });
                      await bootstrapData();
                    }}
                  >
                    <select
                      className="header-pill-select"
                      value={reviewForm.rating}
                      onChange={(e) => setReviewForm({ ...reviewForm, rating: Number(e.target.value) })}
                    >
                      <option value={5}>★ 5</option>
                      <option value={4}>★ 4</option>
                      <option value={3}>★ 3</option>
                    </select>
                    <input
                      className="field-input"
                      style={{ minHeight: 34, padding: "0.35rem 0.7rem", fontSize: 12 }}
                      placeholder="Write a verified garment review..."
                      value={reviewForm.comment}
                      onChange={(e) => setReviewForm({ ...reviewForm, comment: e.target.value })}
                    />
                    <button type="submit" className="chip-pill active">
                      Post
                    </button>
                  </form>
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  paddingTop: "1rem",
                  borderTop: "1px solid var(--border-subtle)",
                }}
              >
                <div style={{ fontSize: "var(--text-2xl)", fontWeight: 700 }}>
                  {formatInr(detailModalProduct.mrp_inr)}
                </div>
                <button className="btn-pill" onClick={() => handleAddToCart(detailModalProduct.product_id)}>
                  <SvgIcon name="bag" size={14} />
                  <span>Add to Cart</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {(activeDrawer === "bag" || forceValidationDemo) && (
        <div className="drawer-backdrop" onClick={() => setActiveDrawer(null)}>
          <aside className="slide-drawer" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-header">
              <div>
                <h3 className="font-editorial" style={{ fontSize: "var(--text-2xl)" }}>
                  Atelier Shopping Bag
                </h3>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  {cartCount} piece(s) · GST & Free Shipping calculated live
                </span>
              </div>
              <button className="heart-btn" onClick={() => setActiveDrawer(null)}>
                <SvgIcon name="close" size={16} />
              </button>
            </div>

            <div className="drawer-body">
              {(cart?.items || []).length === 0 && !forceValidationDemo ? (
                <div className="state-card">
                  <h3 className="font-editorial" style={{ fontSize: "var(--text-xl)", marginBottom: "0.4rem" }}>
                    Your Atelier Bag is Empty
                  </h3>
                  <button className="btn-pill" onClick={() => setActiveDrawer(null)}>
                    Continue Shopping
                  </button>
                </div>
              ) : (
                <>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem", marginBottom: "1.1rem" }}>
                    {(cart?.items || []).map((item) => (
                      <div
                        key={item.cart_id}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          padding: "0.85rem",
                          background: "var(--bg-surface)",
                          borderRadius: 16,
                          border: "1px solid var(--border-subtle)",
                        }}
                      >
                        <div>
                          <div style={{ fontSize: 13, fontWeight: 600 }}>{item.product_name}</div>
                          <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                            {item.product_id} · Size {item.size} · Qty {item.quantity} · {item.gst_rate_pct}% GST
                          </div>
                        </div>
                        <div style={{ textAlign: "right" }}>
                          <div style={{ fontSize: 13, fontWeight: 700 }}>{formatInr(item.line_mrp_inr)}</div>
                          <button
                            className="section-link"
                            style={{ fontSize: 11, color: "var(--state-error-text)" }}
                            onClick={async () => {
                              const nextCart = await apiRef.current.removeCartItem(item.cart_id);
                              setCart(nextCart);
                            }}
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>

                  {availableCoupons.length > 0 && (
                    <div style={{ marginBottom: "1rem" }}>
                      <div className="field-label" style={{ marginBottom: 4 }}>
                        Available Database Coupons (<code>coupons</code> Table)
                      </div>
                      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                        {availableCoupons.map((c) => (
                          <button
                            key={c.code}
                            type="button"
                            className={`chip-pill ${checkoutForm.couponCode === c.code ? "active" : ""}`}
                            style={{ fontSize: 11 }}
                            onClick={async () => {
                              setCheckoutForm((prev) => ({ ...prev, couponCode: c.code }));
                              const res = await apiRef.current.validateCoupon(
                                c.code,
                                Number(cart?.subtotal_mrp_inr || 0)
                              );
                              setCouponResult(res);
                            }}
                          >
                            {c.code} ({c.discount_value}% off ≥ {formatInr(c.min_order_value_inr)})
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <form
                    style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}
                    onSubmit={async (e) => {
                      e.preventDefault();
                      const check = validateCheckoutForm(checkoutForm);
                      setCheckoutValidationErrors(check.errors);
                      if (!check.valid) return;
                      const order = await apiRef.current.createOrder({
                        customerId: actor.role === "customer" ? actor.id : "CUS-001",
                        couponCode: checkoutForm.couponCode || null,
                        paymentMethod: checkoutForm.paymentMethod || "upi",
                      });
                      const [nextCart, nextOrders] = await Promise.all([
                        apiRef.current.getCart(),
                        apiRef.current.listOrders(),
                      ]);
                      setCart(nextCart);
                      setOrders(nextOrders);
                      setActiveDrawer(null);
                      setToastSuccess({
                        title: `Order ${order.order_id} Confirmed!`,
                        message: `Total ${formatInr(order.grand_total_inr)} · Invoice ${order.invoice_id}`,
                      });
                      navigateToPage("orders");
                    }}
                  >
                    <div className="field-group">
                      <label className="field-label" htmlFor="next-chk-street">
                        Delivery Street Address *
                      </label>
                      <input
                        id="next-chk-street"
                        className={`field-input ${activeCheckoutErrors.street ? "invalid" : ""}`}
                        value={checkoutForm.street}
                        onChange={(e) => setCheckoutForm({ ...checkoutForm, street: e.target.value })}
                      />
                      {activeCheckoutErrors.street && (
                        <span className="field-error">{activeCheckoutErrors.street}</span>
                      )}
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem" }}>
                      <div className="field-group">
                        <label className="field-label" htmlFor="next-chk-pin">
                          6-Digit PIN Code *
                        </label>
                        <input
                          id="next-chk-pin"
                          className={`field-input ${activeCheckoutErrors.pinCode ? "invalid" : ""}`}
                          value={checkoutForm.pinCode}
                          onChange={(e) => setCheckoutForm({ ...checkoutForm, pinCode: e.target.value })}
                        />
                        {activeCheckoutErrors.pinCode && (
                          <span className="field-error">{activeCheckoutErrors.pinCode}</span>
                        )}
                      </div>

                      <div className="field-group">
                        <label className="field-label" htmlFor="next-chk-pay">
                          Payment Method (DB) *
                        </label>
                        <select
                          id="next-chk-pay"
                          className="field-input"
                          value={checkoutForm.paymentMethod}
                          onChange={(e) => setCheckoutForm({ ...checkoutForm, paymentMethod: e.target.value })}
                        >
                          {paymentMethods.map((pm) => (
                            <option key={pm.method_id} value={pm.method_id}>
                              {pm.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <button type="submit" className="btn-pill">
                      <SvgIcon name="check" size={14} />
                      <span>Place Verified Order</span>
                    </button>
                  </form>
                </>
              )}
            </div>
          </aside>
        </div>
      )}

      {activeDrawer === "ai" && (
        <div className="drawer-backdrop" onClick={() => setActiveDrawer(null)}>
          <aside className="slide-drawer" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-header">
              <div>
                <h3 className="font-editorial" style={{ fontSize: "var(--text-2xl)" }}>
                  <SvgIcon name="sparkles" size={16} /> <span>{storeName} AI Stylist</span>
                </h3>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  4-Layer ReAct Loop · 9 Agents · Step Budget (Max 10)
                </span>
              </div>
              <button className="heart-btn" onClick={() => setActiveDrawer(null)}>
                <SvgIcon name="close" size={16} />
              </button>
            </div>

            <div className="drawer-body" style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
              <select
                className="field-input"
                style={{ fontSize: 12 }}
                value={agentPreferred}
                onChange={(e) => setAgentPreferred(e.target.value)}
              >
                <option value="">Supervisor Auto-Router (All 9 Agents)</option>
                {agentRegistry.map((a) => (
                  <option key={a.agent_name} value={a.agent_name}>
                    {a.agent_name} ({a.service_account})
                  </option>
                ))}
              </select>

              <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                {(heroCfg.ai_quick_prompts || []).map((qp, idx) => (
                  <button
                    key={idx}
                    className="chip-pill"
                    style={{ fontSize: 11, padding: "0.3rem 0.7rem" }}
                    onClick={() => handleSendAgentPrompt(qp.prompt)}
                  >
                    {qp.label}
                  </button>
                ))}
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem", flex: 1 }}>
                {agentMessages.map((m, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: "0.85rem 1rem",
                      borderRadius: 16,
                      fontSize: 12,
                      background: m.role === "user" ? "var(--accent-noir)" : "var(--bg-surface)",
                      color: m.role === "user" ? "var(--text-on-dark)" : "var(--text-primary)",
                      border: "1px solid var(--border-subtle)",
                    }}
                  >
                    {m.role === "agent" && (
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          fontSize: 10,
                          color: "var(--text-muted)",
                          marginBottom: "0.3rem",
                          fontFamily: "var(--font-mono)",
                        }}
                      >
                        <span>
                          {m.routed_agent} · {m.service_account}
                        </span>
                        <span>
                          Steps: {m.steps_taken ?? 1}/{m.step_budget_max ?? 10}
                        </span>
                      </div>
                    )}
                    <div style={{ whiteSpace: "pre-line", lineHeight: 1.5 }}>{m.text}</div>

                    {m.react_steps?.length > 0 && (
                      <div
                        style={{
                          marginTop: "0.55rem",
                          paddingTop: "0.45rem",
                          borderTop: "1px dashed var(--border-subtle)",
                          fontSize: 10,
                          color: "var(--text-secondary)",
                        }}
                      >
                        <div style={{ fontWeight: 600, marginBottom: 4 }}>
                          4-Layer Agentic Loop (Perception → Reasoning → Action → Reflection):
                        </div>
                        {m.react_steps.map((s) => (
                          <div key={s.step_number} style={{ fontFamily: "var(--font-mono)", marginBottom: 2 }}>
                            [{s.layer.toUpperCase()}] {s.thought}
                          </div>
                        ))}
                      </div>
                    )}

                    {m.tool_traces?.length > 0 && (
                      <div
                        style={{
                          marginTop: "0.45rem",
                          paddingTop: "0.4rem",
                          borderTop: "1px dashed var(--border-subtle)",
                          fontFamily: "var(--font-mono)",
                          fontSize: 10,
                          color: "var(--text-secondary)",
                        }}
                      >
                        {m.tool_traces
                          .map(
                            (t) =>
                              `${t.http_method} ${t.endpoint} [${t.risk_level || "read_only"}] → ${t.status_code} (${t.latency_ms}ms)`
                          )
                          .join(" · ")}
                      </div>
                    )}
                  </div>
                ))}
                {agentBusy && <div className="shimmer" style={{ height: 44, borderRadius: 14 }} />}
              </div>
            </div>

            <div className="drawer-footer">
              <form
                style={{ display: "flex", gap: "0.5rem" }}
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSendAgentPrompt(agentChatInput);
                }}
              >
                <input
                  className="field-input"
                  type="text"
                  value={agentChatInput}
                  onChange={(e) => setAgentChatInput(e.target.value)}
                  placeholder="Ask AI Stylist to search, add to bag, or return..."
                />
                <button type="submit" className="btn-pill">
                  Send
                </button>
              </form>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
