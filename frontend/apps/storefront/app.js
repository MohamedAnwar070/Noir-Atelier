import { NoirApiClient } from "/packages/api/client.js";
import {
  DESIGN_TOKENS,
  applyFontScale,
  applyTheme,
  getContrastRatio,
  getInitialTheme,
  getProductEditorialVisual,
  renderIcon,
} from "/packages/ui/theme.js";
import {
  UI_PRINCIPLE_STATES,
  renderEmptyState,
  renderErrorState,
  renderLoadingState,
  renderNoInternetBanner,
  renderNoSearchResultState,
  renderPendingApprovalState,
  renderPermissionDeniedState,
  renderSessionExpiredState,
  renderSlowNetworkBanner,
  renderSuccessBanner,
} from "/packages/ui/states.js";
import {
  computeGstSlabFromConfig,
  formatInr,
  validateCheckoutForm,
  validatePolicyConfigForm,
  validateReturnForm,
} from "/packages/utils/formatters.js";

const state = {
  activePage: "shop",
  activeDrawer: null,
  mobileMenuOpen: false,
  detailModalProduct: null,
  showDiagnosticsBar: false,
  fontScale: "default",
  theme: getInitialTheme(),
  activeUiPrinciple: "normal",
  actors: [],
  actor: { token: "demo_CUS-001", id: "CUS-001", role: "customer", label: "Loading profile..." },
  inFlightAction: null,
  liveAnnouncement: "",

  isOffline: typeof navigator !== "undefined" ? !navigator.onLine : false,
  slowLatencyMs: null,
  isLoading: true,
  apiError: null,
  permissionDeniedInfo: null,
  sessionExpired: false,
  toastSuccess: null,
  latestReturnEscalation: null,

  businessConfig: {},
  staffRoles: [],
  catalogMeta: {
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
  },
  policies: [],
  paymentMethods: [],
  availableCoupons: [],
  shippingZones: [],
  categories: [],
  products: [],
  catalogTotal: 0,
  searchInterpretation: null,
  cardSizeSelection: {},
  recommendations: [],
  wishlistIds: new Set(),
  reviewForm: { rating: 5, fitFeedback: "true_to_size", comment: "" },

  searchQuery: "",
  selectedDepartment: "ALL",
  selectedCategory: "",
  selectedColor: "",
  selectedMaterial: "",
  minPrice: "",
  maxPrice: "",
  sortBy: "featured",

  cart: null,
  checkoutForm: { street: "", pinCode: "", couponCode: "", paymentMethod: "upi" },
  checkoutValidationErrors: {},
  couponResult: null,

  orders: [],
  returnForm: { orderId: "", reasonCategory: "", reasonNotes: "", tagIntact: true, qcPassed: true },
  returnValidationErrors: {},

  agentRegistry: [],
  agentMessages: [],
  agentPreferred: "",
  agentBusy: false,

  adminDashboard: null,
  adminInventory: [],
  adminRefunds: [],
  adminAuditLog: [],
  policyConfigForm: {
    freeShippingThresholdInr: 1999,
    standardShippingFeeInr: 149,
    reason: "Seasonal luxury shipping threshold review",
  },
  policyConfigErrors: {},
};

applyTheme(state.theme);

const api = new NoirApiClient({
  onNetworkEvent: (evt) => {
    if (evt.type === "offline") {
      state.isOffline = true;
      renderApp();
    } else if (evt.type === "slow_network") {
      state.slowLatencyMs = evt.latencyMs;
      renderApp();
    } else if (evt.type === "session_expired") {
      state.sessionExpired = true;
      renderApp();
    } else if (evt.type === "permission_denied") {
      if (state.activePage === "admin" || state.activeUiPrinciple === "permission_denied") {
        state.permissionDeniedInfo = {
          actorId: `${state.actor.id} (${state.actor.role})`,
          endpoint: evt.endpoint,
          message: evt.data?.message || "Insufficient permissions.",
        };
        renderApp();
      }
    }
  },
});

window.addEventListener("online", () => {
  state.isOffline = false;
  renderApp();
  bootstrapData();
});

window.addEventListener("offline", () => {
  state.isOffline = true;
  renderApp();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (state.detailModalProduct) {
      state.detailModalProduct = null;
      renderApp();
    } else if (state.activeDrawer) {
      state.activeDrawer = null;
      if (state.activeUiPrinciple === "form_validation") state.activeUiPrinciple = "normal";
      renderApp();
    }
  }
});

function isActorStaff(actor = state.actor) {
  return Boolean(
    actor?.is_staff ||
      actor?.actor_type === "admin" ||
      (state.staffRoles || []).includes(actor?.role)
  );
}

async function bootstrapData() {
  state.isLoading = true;
  state.apiError = null;
  state.permissionDeniedInfo = null;
  renderApp();

  try {
    const [cfgPayload, catalogMeta, searchRes, cart, orders, registry] = await Promise.all([
      api.getPoliciesAndConfig(),
      api.getCatalogMeta(),
      api.searchCatalog({
        q: state.searchQuery,
        department: state.selectedDepartment,
        category: state.selectedCategory,
        color: state.selectedColor,
        material: state.selectedMaterial,
        minPrice: state.minPrice || null,
        maxPrice: state.maxPrice || null,
        sort: state.sortBy,
      }),
      api.getCart().catch(() => null),
      api.listOrders().catch(() => []),
      api.getAgentsRegistry().catch(() => []),
    ]);

    state.businessConfig = cfgPayload.business_config || {};
    state.staffRoles = cfgPayload.staff_roles || [];
    state.policies = cfgPayload.policies || [];
    state.paymentMethods = cfgPayload.payment_methods || [];
    state.availableCoupons = cfgPayload.coupons || [];
    state.shippingZones = cfgPayload.shipping_zones || [];
    if (Array.isArray(cfgPayload.actors) && cfgPayload.actors.length > 0) {
      state.actors = cfgPayload.actors;
      const matched = cfgPayload.actors.find((a) => a.token === state.actor.token) || cfgPayload.actors[0];
      state.actor = matched;
    }
    state.catalogMeta = { ...state.catalogMeta, ...(catalogMeta || {}) };
    state.categories = Array.isArray(state.catalogMeta.categories) ? state.catalogMeta.categories : [];
    const items = Array.isArray(searchRes) ? searchRes : searchRes?.items || [];
    state.products = items;
    state.catalogTotal = typeof searchRes?.total === "number" ? searchRes.total : items.length;
    state.searchInterpretation = searchRes?.interpretation || null;
    state.cart = cart;
    state.orders = Array.isArray(orders) ? orders : [];
    state.agentRegistry = Array.isArray(registry) ? registry : [];

    if (!state.returnForm.reasonCategory && state.catalogMeta.return_reasons?.length > 0) {
      state.returnForm.reasonCategory = state.catalogMeta.return_reasons[0].code;
    }
    if (state.paymentMethods.length > 0 && !state.checkoutForm.paymentMethod) {
      state.checkoutForm.paymentMethod = state.paymentMethods[0].method_id || state.paymentMethods[0].method_code || "";
    }

    if (state.businessConfig?.shipping) {
      state.policyConfigForm.freeShippingThresholdInr =
        state.businessConfig.shipping.free_shipping_threshold_inr ?? 1999;
      state.policyConfigForm.standardShippingFeeInr =
        state.businessConfig.shipping.standard_shipping_fee_inr ?? 149;
    }

    state.products.forEach((p) => {
      if (!state.cardSizeSelection[p.product_id]) {
        const sizes = p.sizes_available || [];
        state.cardSizeSelection[p.product_id] = sizes[0] || "";
      }
    });

    if (state.actor.role === "customer") {
      const addresses = await api.listCustomerAddresses(state.actor.id).catch(() => []);
      if (addresses.length > 0) {
        const primary = addresses.find((a) => a.is_primary) || addresses[0];
        if (!state.checkoutForm.street) state.checkoutForm.street = primary.street;
        if (!state.checkoutForm.pinCode) state.checkoutForm.pinCode = primary.pin_code;
      }
    }

    if (state.orders.length > 0 && !state.returnForm.orderId) {
      state.returnForm.orderId = state.orders[0].order_id;
    }

    state.isLoading = false;
    renderApp();
  } catch (err) {
    state.isLoading = false;
    state.apiError = err;
    renderApp();
  }
}

async function refreshProductsFromDb() {
  state.isLoading = true;
  state.apiError = null;
  renderApp();
  try {
    const searchRes = await api.searchCatalog({
      q: state.searchQuery,
      department: state.selectedDepartment,
      category: state.selectedCategory,
      color: state.selectedColor,
      material: state.selectedMaterial,
      minPrice: state.minPrice || null,
      maxPrice: state.maxPrice || null,
      sort: state.sortBy,
    });
    const items = Array.isArray(searchRes) ? searchRes : searchRes?.items || [];
    state.products = items;
    state.catalogTotal = typeof searchRes?.total === "number" ? searchRes.total : items.length;
    state.searchInterpretation = searchRes?.interpretation || null;
    state.products.forEach((p) => {
      if (!state.cardSizeSelection[p.product_id]) {
        const sizes = p.sizes_available || [];
        state.cardSizeSelection[p.product_id] = sizes[0] || "";
      }
    });
    state.isLoading = false;
    state.liveAnnouncement = `${state.products.length} garments loaded from database.`;
    renderApp();
  } catch (err) {
    state.isLoading = false;
    state.apiError = err;
    renderApp();
  }
}

async function openProductDetailModal(productId) {
  try {
    const [detail, recs] = await Promise.all([
      api.getProductDetails(productId),
      api.getRecommendations(productId).catch(() => []),
    ]);
    state.detailModalProduct = detail;
    state.recommendations = recs;
    if (!state.cardSizeSelection[productId]) {
      const sizes = detail.sizes_available || [];
      state.cardSizeSelection[productId] = sizes.includes("M") ? "M" : sizes[0] || "M";
    }
    renderApp();
  } catch (err) {
    state.apiError = err;
    renderApp();
  }
}

async function loadAdminDataFromDb() {
  state.isLoading = true;
  state.apiError = null;
  state.permissionDeniedInfo = null;
  renderApp();

  try {
    const [dashboard, inventory, refunds, auditLog, cfgPayload] = await Promise.all([
      api.getAdminDashboard(state.actor.token),
      api.listInventory(false, state.actor.token),
      api.listRefunds(state.actor.token),
      api.getAuditLog(20, state.actor.token),
      api.getPoliciesAndConfig(),
    ]);
    state.adminDashboard = dashboard;
    state.adminInventory = inventory;
    state.adminRefunds = refunds;
    state.adminAuditLog = auditLog;
    state.businessConfig = cfgPayload.business_config || state.businessConfig;
    state.isLoading = false;
    renderApp();
  } catch (err) {
    state.isLoading = false;
    if (err.status === 403) {
      state.permissionDeniedInfo = {
        actorId: `${state.actor.id} (${state.actor.role})`,
        endpoint: "GET /api/admin/dashboard",
        message: err.message,
      };
    } else if (err.status !== 401) {
      state.apiError = err;
    }
    renderApp();
  }
}

function getSortedProducts() {
  return [...state.products];
}

function renderHeader() {
  const storeName = state.businessConfig?.store?.name || "Noir Atelier";
  const cartCount = (state.cart?.items || []).reduce((acc, i) => acc + Number(i.quantity || 0), 0);
  const departments = state.catalogMeta?.departments || [];

  return `
    <a href="#main-content" class="skip-link">Skip to main garment collection</a>
    <div id="a11y-live-announcer" class="sr-only" aria-live="polite" aria-atomic="true">${state.liveAnnouncement}</div>
    <header class="site-header">
      <div class="site-header-inner">
        <div class="brand-group">
          <button class="brand-logo" data-action="nav-page" data-page="shop">${storeName}</button>
          <nav class="primary-nav" aria-label="Main Navigation">
            <button
              class="nav-link ${state.activePage === "shop" && state.selectedDepartment === "ALL" ? "active" : ""}"
              data-action="nav-dept"
              data-department="ALL"
            >
              The Edit
            </button>
            ${departments
              .map(
                (dept) => `
                <button
                  class="nav-link ${state.activePage === "shop" && state.selectedDepartment === dept.code ? "active" : ""}"
                  data-action="nav-dept"
                  data-department="${dept.code}"
                >
                  ${dept.name}
                </button>
              `
              )
              .join("")}
            <button
              class="nav-link ${state.activePage === "orders" ? "active" : ""}"
              data-action="nav-page"
              data-page="orders"
            >
              Orders & Returns (${state.orders.length})
            </button>
            <button
              class="nav-link ${state.activePage === "policies" ? "active" : ""}"
              data-action="nav-page"
              data-page="policies"
            >
              Atelier Policies
            </button>
            <button
              class="nav-link ${state.activePage === "admin" ? "active" : ""}"
              data-action="nav-page"
              data-page="admin"
            >
              Admin Console
            </button>
          </nav>
        </div>

        <div class="header-actions">
          <form class="header-search" data-form="catalog-search" role="search">
            <span class="header-search-icon">${renderIcon("search", "xs")}</span>
            <input
              id="catalog-search-input"
              type="search"
              aria-label="Search garments"
              placeholder="Search linen, silk, merino..."
              value="${state.searchQuery}"
            />
          </form>

          <div class="header-desktop-controls">
            <select class="header-pill-select" data-action="change-actor" aria-label="Account profile">
              ${(state.actors.length > 0 ? state.actors : [state.actor]).map(
                (a) => `<option value="${a.token}" ${state.actor.token === a.token ? "selected" : ""}>${a.label}</option>`
              ).join("")}
            </select>

            <select class="header-pill-select" data-action="change-font-scale" aria-label="Typography scale">
              ${DESIGN_TOKENS.fontScales
                .map((f) => `<option value="${f.id}" ${state.fontScale === f.id ? "selected" : ""}>${f.label}</option>`)
                .join("")}
            </select>
          </div>

          <button
            class="chip-pill"
            data-action="toggle-theme"
            aria-label="Toggle color theme"
            title="Switch Light / Noir Dark Theme"
          >
            ${state.theme === "dark" ? renderIcon("sun", "xs") : renderIcon("moon", "xs")}
            <span>${state.theme === "dark" ? "Light" : "Noir"}</span>
          </button>

          <button
            class="btn-pill"
            style="padding:0.48rem 1.05rem;font-size:var(--text-xs);"
            data-action="open-drawer"
            data-drawer="bag"
          >
            ${renderIcon("bag", "xs")}
            <span>Bag (${cartCount})</span>
          </button>

          <button
            type="button"
            class="mobile-menu-btn"
            data-action="toggle-mobile-menu"
            aria-label="Toggle mobile navigation menu"
            aria-expanded="${state.mobileMenuOpen}"
            aria-controls="mobile-nav-panel"
          >
            ${renderIcon(state.mobileMenuOpen ? "close" : "menu", "sm")}
          </button>
        </div>
      </div>

      <div
        id="mobile-nav-panel"
        class="mobile-nav-drawer ${state.mobileMenuOpen ? "open" : ""}"
        aria-label="Mobile Navigation & Profile Settings"
      >
        <div class="mobile-nav-grid">
          <button
            class="chip-pill ${state.activePage === "shop" && state.selectedDepartment === "ALL" ? "active" : ""}"
            data-action="nav-dept"
            data-department="ALL"
          >
            The Edit (All)
          </button>
          ${departments
            .map(
              (dept) => `
              <button
                class="chip-pill ${state.activePage === "shop" && state.selectedDepartment === dept.code ? "active" : ""}"
                data-action="nav-dept"
                data-department="${dept.code}"
              >
                ${dept.name}
              </button>
            `
            )
            .join("")}
          <button
            class="chip-pill ${state.activePage === "policies" ? "active" : ""}"
            data-action="nav-page"
            data-page="policies"
          >
            Atelier Policies
          </button>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;">
          <select class="header-pill-select" data-action="change-actor" aria-label="Mobile account profile">
            ${(state.actors.length > 0 ? state.actors : [state.actor]).map(
              (a) => `<option value="${a.token}" ${state.actor.token === a.token ? "selected" : ""}>${a.label}</option>`
            ).join("")}
          </select>

          <select class="header-pill-select" data-action="change-font-scale" aria-label="Mobile typography scale">
            ${DESIGN_TOKENS.fontScales
              .map((f) => `<option value="${f.id}" ${state.fontScale === f.id ? "selected" : ""}>${f.label}</option>`)
              .join("")}
          </select>
        </div>
      </div>
    </header>
  `;
}

function renderGlobalBanners() {
  const banners = [];
  if (state.isOffline || state.activeUiPrinciple === "offline") {
    banners.push(renderNoInternetBanner());
  }
  if (state.slowLatencyMs || state.activeUiPrinciple === "slow_network") {
    banners.push(renderSlowNetworkBanner({ latencyMs: state.slowLatencyMs || 1640 }));
  }
  if (state.toastSuccess || state.activeUiPrinciple === "success") {
    const t = state.toastSuccess || {
      title: "Confirmed in Database",
      message: "Transaction committed to PostgreSQL/SQLite with HSN 61/62 GST invoice and audit_log record.",
    };
    banners.push(renderSuccessBanner(t));
  }
  return banners.length ? `<div style="margin-bottom:1.25rem;">${banners.join("")}</div>` : "";
}

function renderHeroSection() {
  const spotlight = state.products[0];
  const freeShipMin = state.businessConfig?.shipping?.free_shipping_threshold_inr ?? 1999;
  const uiCfg = state.businessConfig?.storefront_ui || {};
  const aiPrompts = uiCfg.ai_quick_prompts || [];

  return `
    <div class="hero-banner-wrap">
      <section class="hero-banner" aria-label="Editorial Spotlight">
      <div class="hero-content">
        <div>
          <div class="hero-eyebrow">
            ${renderIcon("sparkles", "xs")}
            <span>${uiCfg.hero_eyebrow || "Noir Atelier · HSN 61 & 62 Luxury Garments"}</span>
          </div>
          <h1 class="hero-title">${uiCfg.hero_title || "The New Edit"}</h1>
          <p class="hero-subtitle">
            ${uiCfg.hero_subtitle || ""} Complimentary express delivery above ${formatInr(freeShipMin)}.
          </p>
          <div class="hero-cta-row">
            <button class="btn-pill" data-action="scroll-to-catalog">
              <span>Explore Collection</span>
              ${renderIcon("arrow-right", "xs")}
            </button>
            <button
              class="btn-pill btn-pill-outline"
              style="background:rgba(255,255,255,0.92);color:#181817;border-color:transparent;"
              data-action="open-drawer"
              data-drawer="ai"
            >
              ${renderIcon("sparkles", "xs")}
              <span>Shop with AI Stylist</span>
            </button>
          </div>
        </div>

        <div class="hero-ai-prompts">
          <span style="font-size:11px;opacity:0.88;">Try asking AI:</span>
          ${aiPrompts
            .map(
              (qp) => `
              <button
                class="hero-ai-chip"
                data-action="trigger-ai-prompt"
                data-prompt="${qp.prompt}"
              >
                "${qp.label}"
              </button>
            `
            )
            .join("")}
        </div>
      </div>

      <div class="hero-visual">
        ${uiCfg.hero_image_url ? `<img src="${uiCfg.hero_image_url}" alt="Noir Atelier Editorial Collection" />` : ""}
        ${
          spotlight
            ? `
          <div class="hero-floating-card">
            <div>
              <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-muted);font-weight:600;">
                Featured Atelier Piece · ${spotlight.department}
              </div>
              <div class="font-editorial" style="font-size:var(--text-lg);font-weight:600;">
                ${spotlight.name}
              </div>
              <div style="font-size:var(--text-xs);color:var(--text-secondary);">
                ${formatInr(spotlight.mrp_inr)} · ★ ${spotlight.average_rating ?? "5.0"}
              </div>
            </div>
            <button
              class="btn-pill"
              style="padding:0.5rem 1.1rem;font-size:var(--text-xs);"
              data-action="open-product-modal"
              data-product-id="${spotlight.product_id}"
            >
              View Piece
            </button>
          </div>
        `
            : ""
        }
      </div>
      </section>
    </div>
  `;
}

function renderShopPage() {
  const departments = state.catalogMeta?.departments || [];
  const deptPills = [
    { code: "ALL", label: "All Garments" },
    ...departments.map((d) => ({
      code: d.code,
      label: d.name,
    })),
  ];
  const sortOptions = state.catalogMeta?.sort_options || [];
  const categories = (state.catalogMeta?.categories || []).filter((c) => (c.product_count ?? 0) > 0);
  const colorFamilies = state.catalogMeta?.color_families || [];
  const materialFamilies = state.catalogMeta?.material_families || [];
  const slabThreshold = state.businessConfig?.tax?.garment_slab_threshold_inr ?? 2500;
  const lowGstPct = Math.round(Number(state.businessConfig?.tax?.rate_upto_threshold ?? 0.05) * 100);

  let catalogBody = "";

  if (state.isLoading || state.activeUiPrinciple === "loading") {
    catalogBody = renderLoadingState({ count: 4, label: "Loading garments from PostgreSQL/SQLite catalog..." });
  } else if (state.sessionExpired || state.activeUiPrinciple === "session_expired") {
    catalogBody = renderSessionExpiredState();
  } else if (state.activeUiPrinciple === "permission_denied") {
    catalogBody = renderPermissionDeniedState({
      actorId: `${state.actor.id} (${state.actor.role})`,
      endpoint: "PUT /api/admin/config/policies",
    });
  } else if (state.apiError || state.activeUiPrinciple === "error") {
    const err = state.apiError || {
      code: "catalog_fetch_error",
      message: "Could not load catalog from /api/catalog/search.",
      trace_id: "TRC-502910",
    };
    catalogBody = renderErrorState({
      code: err.code,
      message: err.message,
      traceId: err.trace_id,
    });
  } else if (state.activeUiPrinciple === "empty") {
    catalogBody = renderEmptyState({
      title: "Collection Currently Empty",
      description: "No active garments in this view. Click below to reload all garments from the database.",
      actionLabel: "Reload Catalog",
      actionAttr: 'data-action="clear-filters"',
    });
  } else if (state.activeUiPrinciple === "pending_approval") {
    catalogBody = renderPendingApprovalState(state.latestReturnEscalation || {});
  } else {
    const sorted = getSortedProducts();
    if (sorted.length === 0 || state.activeUiPrinciple === "no_results") {
      catalogBody = renderNoSearchResultState({
        query: state.searchQuery,
        department: state.selectedDepartment,
        maxPrice: state.maxPrice,
      });
    } else {
      catalogBody = `
        <div class="catalog-grid" id="catalog-grid-anchor">
          ${sorted.map((p) => renderProductCard(p)).join("")}
        </div>
      `;
    }
  }

  return `
    ${renderHeroSection()}

    <section class="catalog-section" aria-label="Garment Catalog">
      <div class="catalog-toolbar">
        <div class="catalog-heading-group">
          <h2>Trending Now</h2>
          <span style="font-size:var(--text-xs);color:var(--text-secondary);">
            ${state.catalogTotal || state.products.length} tailored pieces available
          </span>
        </div>
        ${
          state.searchQuery ||
          state.selectedDepartment !== "ALL" ||
          state.selectedCategory ||
          state.selectedColor ||
          state.selectedMaterial ||
          state.maxPrice
            ? `<button class="section-link" data-action="clear-filters">
                <span>Reset all filters</span>
                ${renderIcon("close", "xs")}
              </button>`
            : ""
        }
      </div>

      <div class="catalog-filters-row">
        <div class="category-pills" role="tablist" aria-label="Department Filter">
          ${deptPills
            .map(
              (d) => `
              <button
                class="chip-pill ${state.selectedDepartment === d.code ? "active" : ""}"
                role="tab"
                aria-selected="${state.selectedDepartment === d.code}"
                data-action="filter-department"
                data-department="${d.code}"
              >
                ${d.label}
              </button>
            `
            )
            .join("")}
          <button
            class="chip-pill ${Number(state.maxPrice) === Number(slabThreshold) ? "active" : ""}"
            data-action="quick-price-slab"
            data-max-price="${slabThreshold}"
          >
            Up to ${formatInr(slabThreshold)} (${lowGstPct}% GST Slab)
          </button>
        </div>

        <div class="filter-controls" style="display:flex;gap:0.5rem;flex-wrap:wrap;">
          ${
            categories.length > 0
              ? `<select class="header-pill-select" data-action="change-category" aria-label="Filter garment type">
                  <option value="">All Types</option>
                  ${categories
                    .map(
                      (c) =>
                        `<option value="${c.slug}" ${state.selectedCategory === c.slug ? "selected" : ""}>${c.name}</option>`
                    )
                    .join("")}
                </select>`
              : ""
          }
          ${
            colorFamilies.length > 0
              ? `<select class="header-pill-select" data-action="change-color" aria-label="Filter colour family">
                  <option value="">All Colours</option>
                  ${colorFamilies
                    .map(
                      (cf) =>
                        `<option value="${cf.family}" ${state.selectedColor === cf.family ? "selected" : ""}>${cf.label}</option>`
                    )
                    .join("")}
                </select>`
              : ""
          }
          ${
            materialFamilies.length > 0
              ? `<select class="header-pill-select" data-action="change-material" aria-label="Filter fiber">
                  <option value="">All Fibers</option>
                  ${materialFamilies
                    .map(
                      (mf) =>
                        `<option value="${mf.family}" ${state.selectedMaterial === mf.family ? "selected" : ""}>${mf.label}</option>`
                    )
                    .join("")}
                </select>`
              : ""
          }
          <select class="header-pill-select" data-action="change-sort" aria-label="Sort garments">
            ${sortOptions
              .map(
                (opt) =>
                  `<option value="${opt.id}" ${state.sortBy === opt.id ? "selected" : ""}>${opt.label}</option>`
              )
              .join("")}
          </select>
        </div>
      </div>

      ${catalogBody}
    </section>
  `;
}

function renderProductCard(p) {
  const visual = getProductEditorialVisual(p);
  const taxInfo = computeGstSlabFromConfig(p.mrp_inr, state.businessConfig?.tax || {});
  const isLiked = state.wishlistIds.has(p.product_id);
  const activeSize = state.cardSizeSelection[p.product_id] || (p.sizes_available || [])[0] || "M";
  const sizeBreakdown = p.size_breakdown || {};
  const isAddingThis = state.inFlightAction === `add:${p.product_id}`;

  return `
    <article class="product-card">
      <div
        class="product-card-media"
        style="background:${visual.bgGradient};"
        data-action="open-product-modal"
        data-product-id="${p.product_id}"
      >
        <div class="card-top-badges">
          <span class="rating-badge">
            ${renderIcon("star", "xs")}
            <span>${p.average_rating ?? "5.0"}</span>
          </span>
          <button
            class="heart-btn ${isLiked ? "liked" : ""}"
            data-action="toggle-wishlist"
            data-product-id="${p.product_id}"
            aria-label="Save ${p.name} to wishlist"
            aria-pressed="${isLiked}"
          >
            ${renderIcon(isLiked ? "heart-filled" : "heart", "sm")}
          </button>
        </div>
        <img src="${visual.photoUrl}" alt="${p.name}" loading="lazy" />
      </div>

      <div class="product-card-body">
        <div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem;">
            <span class="product-card-dept">${p.department} · ${p.product_id}</span>
            <span class="meta-tag">${visual.accentTag}</span>
          </div>
          <h3
            class="product-card-title"
            data-action="open-product-modal"
            data-product-id="${p.product_id}"
          >
            ${p.name}
          </h3>
          <p class="product-card-desc" style="margin-top:0.35rem;">${p.description}</p>
        </div>

        <div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.35rem;">
            <span class="field-label" style="font-size:10px;">Select Size</span>
            <span style="font-size:10px;color:var(--text-muted);">${p.stock} in stock</span>
          </div>
          <div class="product-card-sizes" style="margin-bottom:0.85rem;">
            ${(p.sizes_available || [])
              .map((sz) => {
                const qty = sizeBreakdown[sz] ?? p.stock;
                return `
                  <button
                    class="size-pill ${activeSize === sz ? "active" : ""}"
                    style="min-width:38px;height:32px;padding:0 0.55rem;font-size:11px;"
                    data-action="select-card-size"
                    data-product-id="${p.product_id}"
                    data-size="${sz}"
                    aria-pressed="${activeSize === sz}"
                    ${qty <= 0 ? "disabled" : ""}
                  >
                    ${sz}
                  </button>
                `;
              })
              .join("")}
          </div>

          <div class="product-card-footer">
            <div>
              <div class="product-price">${formatInr(p.mrp_inr)}</div>
              <div class="product-gst-sub">HSN ${p.hsn_code} · ${taxInfo.label}</div>
            </div>
            <button
              class="btn-pill"
              style="padding:0.62rem 1.25rem;font-size:var(--text-xs);"
              data-action="add-to-cart"
              data-product-id="${p.product_id}"
              ${p.stock <= 0 || isAddingThis ? "disabled" : ""}
            >
              ${isAddingThis ? `<span class="btn-spinner"></span><span>Adding...</span>` : `<span>Add to Cart</span>`}
            </button>
          </div>
        </div>
      </div>
    </article>
  `;
}

function renderProductDetailModal() {
  const p = state.detailModalProduct;
  if (!p) return "";

  const visual = getProductEditorialVisual(p);
  const taxInfo = computeGstSlabFromConfig(p.mrp_inr, state.businessConfig?.tax || {});
  const activeSize = state.cardSizeSelection[p.product_id] || (p.sizes_available || [])[0] || "M";
  const sizeBreakdown = p.size_breakdown || {};

  return `
    <div class="detail-modal-backdrop" data-action="close-modal-backdrop">
      <div class="detail-modal-sheet" role="dialog" aria-modal="true" aria-label="${p.name}">
        <div class="detail-modal-media">
          <div class="card-top-badges">
            <span class="rating-badge">
              ${renderIcon("star", "xs")}
              <span>${p.average_rating ?? "5.0"} (${p.review_count || 1} verified review)</span>
            </span>
            <button class="heart-btn" data-action="close-product-modal" aria-label="Close product modal" title="Close (Esc)">
              ${renderIcon("close", "sm")}
            </button>
          </div>
          <img src="${visual.photoUrl}" alt="${p.name}" />
        </div>

        <div class="detail-modal-content">
          <div>
            <div class="sheet-grabber" aria-hidden="true"></div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">
              <span class="product-card-dept">${p.department} COLLECTION · ${p.sku}</span>
              <span class="meta-tag">HSN ${p.hsn_code} · ${taxInfo.label}</span>
            </div>

            <h2 class="font-editorial" style="font-size:var(--text-3xl);margin-bottom:0.6rem;">${p.name}</h2>
            <p style="font-size:var(--text-sm);color:var(--text-secondary);line-height:1.6;margin-bottom:1.1rem;">
              ${p.description}
            </p>

            <div class="detail-specs-grid">
              <div>
                <div class="field-label" style="margin-bottom:0.2rem;">Fit & Silhouette</div>
                <div style="color:var(--text-secondary);">${p.fit_guide}</div>
              </div>
              <div>
                <div class="field-label" style="margin-bottom:0.2rem;">Fabric & Atelier Care</div>
                <div style="color:var(--text-secondary);">${p.fabric_and_care}</div>
              </div>
            </div>

            <div style="margin-bottom:1.25rem;">
              <div style="display:flex;justify-content:space-between;margin-bottom:0.45rem;">
                <span class="field-label">SIZE</span>
                <span style="font-size:11px;color:var(--text-secondary);">
                  Size ${activeSize}: ${sizeBreakdown[activeSize] ?? p.stock} units available in warehouse
                </span>
              </div>
              <div style="display:flex;gap:0.5rem;flex-wrap:wrap;">
                ${(p.sizes_available || [])
                  .map((sz) => {
                    const qty = sizeBreakdown[sz] ?? p.stock;
                    return `
                      <button
                        class="size-pill ${activeSize === sz ? "active" : ""}"
                        data-action="select-card-size"
                        data-product-id="${p.product_id}"
                        data-size="${sz}"
                        ${qty <= 0 ? "disabled" : ""}
                      >
                        ${sz}
                      </button>
                    `;
                  })
                  .join("")}
              </div>
            </div>

            ${
              state.recommendations.length > 0
                ? `
              <div style="margin-bottom:1rem;">
                <div class="field-label" style="margin-bottom:0.45rem;">Complete the Look (Database Recommendations)</div>
                <div style="display:flex;gap:0.6rem;flex-wrap:wrap;">
                  ${state.recommendations
                    .map(
                      (rec) => `
                      <button
                        class="chip-pill"
                        data-action="open-product-modal"
                        data-product-id="${rec.product_id}"
                      >
                        <span>${rec.name} · ${formatInr(rec.mrp_inr)}</span>
                        ${renderIcon("arrow-right", "xs")}
                      </button>
                    `
                    )
                    .join("")}
                </div>
              </div>
            `
                : ""
            }

            <div style="margin-bottom:1rem;padding:0.9rem;border-radius:16px;background:var(--bg-subtle);">
              <div class="field-label" style="margin-bottom:0.45rem;">
                Verified Customer Reviews (${(p.reviews || []).length})
              </div>
              <div style="display:flex;flex-direction:column;gap:0.45rem;margin-bottom:0.75rem;">
                ${(p.reviews || [])
                  .map(
                    (rv) => `
                    <div style="font-size:11px;padding:0.55rem 0.7rem;border-radius:10px;background:var(--bg-surface);border:1px solid var(--border-subtle);">
                      <div style="display:flex;justify-content:space-between;font-weight:600;margin-bottom:2px;">
                        <span>★ ${rv.rating}/5 · ${rv.customer_id}</span>
                        <span class="meta-tag">${rv.fit_feedback}</span>
                      </div>
                      <div style="color:var(--text-secondary);">${rv.comment}</div>
                    </div>
                  `
                  )
                  .join("")}
              </div>
              <form data-form="review-form" data-product-id="${p.product_id}" style="display:flex;gap:0.45rem;flex-wrap:wrap;">
                <select id="review-rating-input" class="field-input" style="width:92px;padding:0.35rem 0.5rem;font-size:11px;">
                  <option value="5">★ 5/5</option>
                  <option value="4">★ 4/5</option>
                  <option value="3">★ 3/5</option>
                </select>
                <select id="review-fit-input" class="field-input" style="width:130px;padding:0.35rem 0.5rem;font-size:11px;">
                  ${(state.catalogMeta?.fit_feedback_options || [])
                    .map((opt) => `<option value="${opt.code}">${opt.label}</option>`)
                    .join("")}
                </select>
                <input
                  id="review-comment-input"
                  class="field-input"
                  style="flex:1;padding:0.35rem 0.65rem;font-size:11px;"
                  placeholder="Write a verified garment review..."
                />
                <button type="submit" class="chip-pill active" style="font-size:11px;">Post Review</button>
              </form>
            </div>
          </div>

          <div style="display:flex;align-items:center;justify-content:space-between;gap:1rem;padding-top:1rem;border-top:1px solid var(--border-subtle);flex-wrap:wrap;">
            <div>
              <div class="field-label">PRICE (MRP INCLUSIVE OF ALL TAXES)</div>
              <div style="font-size:var(--text-2xl);font-weight:700;">${formatInr(p.mrp_inr)}</div>
            </div>
            <div style="display:flex;gap:0.6rem;flex-wrap:wrap;">
              <button
                class="btn-pill btn-pill-outline"
                data-action="trigger-ai-prompt"
                data-prompt="Tell me how to style ${p.product_id} (${p.name}) and its care instructions"
              >
                ${renderIcon("sparkles", "xs")}
                <span>Ask AI Stylist</span>
              </button>
              <button
                class="btn-pill"
                style="min-width:170px;"
                data-action="add-to-cart"
                data-product-id="${p.product_id}"
              >
                ${renderIcon("bag", "xs")}
                <span>Add to Cart</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderOrdersAndReturnsPage() {
  const retErrors = state.returnValidationErrors;

  return `
    <div class="page-grid-2col">
      <div class="surface-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.1rem;">
          <div>
            <h2 class="font-editorial" style="font-size:var(--text-2xl);">Your Orders & Shipments</h2>
            <p style="font-size:var(--text-xs);color:var(--text-secondary);">
              Showing live database orders for <strong>${state.actor.label}</strong>
            </p>
          </div>
          <button class="chip-pill" data-action="nav-page" data-page="shop">+ New Order</button>
        </div>

        ${
          state.orders.length === 0
            ? renderEmptyState({
                title: "No Orders Found",
                description: "Place an order from the Storefront or via the Order Agent to view GST invoices, shipment tracking, and return options.",
                actionLabel: "Explore Garments",
                actionAttr: 'data-action="nav-page" data-page="shop"',
              })
            : `<div style="display:flex;flex-direction:column;gap:0.85rem;">
                ${state.orders
                  .map(
                    (o) => `
                    <div style="padding:1.1rem;border-radius:18px;background:var(--bg-page);border:1px solid var(--border-subtle);">
                      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.45rem;flex-wrap:wrap;gap:0.5rem;">
                        <div>
                          <strong style="font-size:var(--text-base);">${o.order_id}</strong>
                          <span style="font-size:var(--text-xs);color:var(--text-secondary);margin-left:0.5rem;">
                            Invoice: ${o.invoice_id || "—"}
                          </span>
                        </div>
                        <div style="display:flex;gap:0.4rem;align-items:center;">
                          <span class="meta-tag">Status: ${o.status_label || o.status}</span>
                          <span class="meta-tag">Payment: ${o.payment_status}</span>
                        </div>
                      </div>

                      <div style="font-size:var(--text-xs);color:var(--text-secondary);margin-bottom:0.75rem;">
                        ${(o.items || [])
                          .map((i) => `${i.quantity}x ${i.product_name} (Size ${i.size}, GST ${i.gst_rate_pct}%)`)
                          .join(" · ")}
                      </div>

                      <div style="display:flex;justify-content:space-between;align-items:center;padding-top:0.65rem;border-top:1px solid var(--border-subtle);flex-wrap:wrap;gap:0.5rem;">
                        <div style="font-size:var(--text-sm);font-weight:600;">
                          Grand Total: ${formatInr(o.grand_total_inr)}
                          <span style="font-size:11px;font-weight:400;color:var(--text-secondary);">
                            (Taxable ${formatInr(o.taxable_value_inr)} + GST ${formatInr(o.total_gst_inr)})
                          </span>
                        </div>
                        <div style="display:flex;gap:0.45rem;">
                          <button
                            class="chip-pill"
                            data-action="prefill-return-order"
                            data-order-id="${o.order_id}"
                          >
                            Initiate Return
                          </button>
                          ${
                            o.can_cancel
                              ? `<button
                                  class="chip-pill"
                                  style="color:var(--state-error-text);border-color:var(--state-error-border);"
                                  data-action="cancel-order"
                                  data-order-id="${o.order_id}"
                                >
                                  Cancel Order (Tier 0 Auto-Refund)
                                </button>`
                              : ""
                          }
                        </div>
                      </div>
                    </div>
                  `
                  )
                  .join("")}
              </div>`
        }
      </div>

      <div style="display:flex;flex-direction:column;gap:1.25rem;">
        ${state.latestReturnEscalation ? renderPendingApprovalState(state.latestReturnEscalation) : ""}

        <div class="surface-card">
          <h3 class="font-editorial" style="font-size:var(--text-2xl);margin-bottom:0.35rem;">
            4-Tier Garment Return & Physical QC
          </h3>
          <p style="font-size:var(--text-xs);color:var(--text-secondary);margin-bottom:1.1rem;">
            Tier 1 (≤ ₹5,000) auto-refunds upon QC pass; Tier 2 (₹5,001–₹25,000) routes to Store Manager; Tier 3 (> ₹25,000) requires Manager + Finance dual approval.
          </p>

          <form data-form="return-form" style="display:flex;flex-direction:column;gap:0.85rem;" novalidate>
            <div class="field-group">
              <label class="field-label" for="return-order-id">Order ID *</label>
              <input
                id="return-order-id"
                class="field-input ${retErrors.orderId ? "invalid" : ""}"
                type="text"
                aria-invalid="${Boolean(retErrors.orderId)}"
                aria-describedby="${retErrors.orderId ? "err-return-order-id" : ""}"
                value="${state.returnForm.orderId}"
                placeholder="ORD-1001"
              />
              ${retErrors.orderId ? `<span id="err-return-order-id" class="field-error">${retErrors.orderId}</span>` : ""}
            </div>

            <div class="field-group">
              <label class="field-label" for="return-reason-category">Return Reason *</label>
              <select id="return-reason-category" class="field-input" style="font-size:12px;">
                ${(state.catalogMeta?.return_reasons || [])
                  .map(
                    (rr) =>
                      `<option value="${rr.code}" ${state.returnForm.reasonCategory === rr.code ? "selected" : ""}>${rr.label}</option>`
                  )
                  .join("")}
              </select>
            </div>

            <div class="field-group">
              <label class="field-label" for="return-notes">Reason & Fit Feedback *</label>
              <input
                id="return-notes"
                class="field-input ${retErrors.reasonNotes ? "invalid" : ""}"
                type="text"
                aria-invalid="${Boolean(retErrors.reasonNotes)}"
                aria-describedby="${retErrors.reasonNotes ? "err-return-notes" : ""}"
                value="${state.returnForm.reasonNotes}"
                placeholder="Slightly tight across shoulders"
              />
              ${retErrors.reasonNotes ? `<span id="err-return-notes" class="field-error">${retErrors.reasonNotes}</span>` : ""}
            </div>

            <label style="display:flex;align-items:center;gap:0.5rem;font-size:var(--text-xs);cursor:pointer;">
              <input id="return-tag-intact" type="checkbox" ${state.returnForm.tagIntact ? "checked" : ""} />
              <span>Noir Atelier security ribbon & garment tags intact (POL-RET-01)</span>
            </label>
            ${retErrors.tagIntact ? `<span class="field-error">${retErrors.tagIntact}</span>` : ""}

            <button type="submit" class="btn-pill" style="width:100%;">
              ${renderIcon("shield", "xs")}
              <span>Submit Return Request</span>
            </button>
          </form>
        </div>
      </div>
    </div>
  `;
}

function renderPoliciesPage() {
  const taxCfg = state.businessConfig?.tax || {};
  const shipCfg = state.businessConfig?.shipping || {};
  const retCfg = state.businessConfig?.returns_and_refunds || {};
  const tiers = retCfg.tiers || {};

  return `
    <div style="display:flex;flex-direction:column;gap:1.5rem;">
      <div class="surface-card kpi-section">
        <h2 class="font-editorial" style="font-size:var(--text-3xl);margin-bottom:0.4rem;">
          Noir Atelier Governance & Store Policies
        </h2>
        <p style="font-size:var(--text-sm);color:var(--text-secondary);">
          Loaded dynamically from PostgreSQL/SQLite <code>business_config</code> and <code>policies</code> tables via <code>GET /api/config/policies</code>.
        </p>

        <div class="kpi-row" style="margin-top:1.25rem;margin-bottom:0;">
          <div class="kpi-tile">
            <div class="kpi-tile-label">HSN 61/62 Slab ≤ ₹${taxCfg.garment_slab_threshold_inr ?? 2500}</div>
            <div class="kpi-tile-value">${Number(taxCfg.rate_upto_threshold ?? 0.05) * 100}% GST</div>
          </div>
          <div class="kpi-tile">
            <div class="kpi-tile-label">HSN 61/62 Slab > ₹${taxCfg.garment_slab_threshold_inr ?? 2500}</div>
            <div class="kpi-tile-value">${Number(taxCfg.rate_above_threshold ?? 0.18) * 100}% GST</div>
          </div>
          <div class="kpi-tile">
            <div class="kpi-tile-label">Complimentary Shipping</div>
            <div class="kpi-tile-value">≥ ${formatInr(shipCfg.free_shipping_threshold_inr ?? 1999)}</div>
          </div>
          <div class="kpi-tile">
            <div class="kpi-tile-label">Return Window</div>
            <div class="kpi-tile-value">${retCfg.return_window_days ?? 7} Days</div>
          </div>
        </div>
      </div>

      <div class="catalog-grid">
        ${state.policies
          .map(
            (pol) => `
            <div class="surface-card">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                <span class="chip-pill active" style="font-size:10px;">${pol.policy_id}</span>
                <span class="meta-tag">${pol.topic} · v${pol.version}</span>
              </div>
              <h3 class="font-editorial" style="font-size:var(--text-xl);margin-bottom:0.45rem;">${pol.title}</h3>
              <p style="font-size:var(--text-xs);color:var(--text-secondary);line-height:1.6;">${pol.rule_text}</p>
            </div>
          `
          )
          .join("")}
      </div>

      <div class="surface-card kpi-section">
        <h3 class="font-editorial" style="font-size:var(--text-2xl);margin-bottom:0.75rem;">
          4-Tier Premium Garment Refund Approval Matrix
        </h3>
        <div class="kpi-row" style="margin-bottom:0;">
          <div class="kpi-tile">
            <div class="kpi-tile-label">Tier 0 · Pre-Shipment Cancel</div>
            <div style="font-weight:700;margin-top:0.35rem;">Up to ${formatInr(tiers.tier_0_pre_ship_cancel_max_inr ?? 50000)}</div>
            <div style="font-size:11px;color:var(--text-secondary);margin-top:0.2rem;">Auto-approved by svc-order</div>
          </div>
          <div class="kpi-tile">
            <div class="kpi-tile-label">Tier 1 · Standard Garment</div>
            <div style="font-weight:700;margin-top:0.35rem;">Up to ${formatInr(tiers.tier_1_auto_refund_max_inr ?? 5000)}</div>
            <div style="font-size:11px;color:var(--text-secondary);margin-top:0.2rem;">Auto-approved by svc-returns (QC + Ribbon intact)</div>
          </div>
          <div class="kpi-tile">
            <div class="kpi-tile-label">Tier 2 · Luxury / Archive</div>
            <div style="font-weight:700;margin-top:0.35rem;">Up to ${formatInr(tiers.tier_2_manager_approval_max_inr ?? 25000)}</div>
            <div style="font-size:11px;color:var(--text-secondary);margin-top:0.2rem;">Requires Store Manager (MGR-001)</div>
          </div>
          <div class="kpi-tile">
            <div class="kpi-tile-label">Tier 3 · Couture / Multi-Item</div>
            <div style="font-weight:700;margin-top:0.35rem;">Up to ${formatInr(tiers.tier_3_dual_approval_max_inr ?? 50000)}</div>
            <div style="font-size:11px;color:var(--text-secondary);margin-top:0.2rem;">Dual Manager + Finance Admin sign-off</div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderAdminConsolePage() {
  if (state.permissionDeniedInfo || !isActorStaff()) {
    return renderPermissionDeniedState({
      actorId: `${state.actor.id} (${state.actor.role})`,
      requiredRole: "Store Manager (MGR-001) or Finance Admin (FIN-001)",
      endpoint: "GET /api/admin/dashboard",
    });
  }

  if (state.isLoading) {
    return renderLoadingState({ count: 4, label: "Loading Admin Governance & Audit Log..." });
  }

  const ordStats = state.adminDashboard?.orders || { total_orders: 0, total_revenue_inr: 0 };
  const cusStats = state.adminDashboard?.customers || { total_customers: 0, retention_rate_pct: 0 };
  const pErr = state.policyConfigErrors;

  return `
    <div style="display:flex;flex-direction:column;gap:1.5rem;">
      <div class="surface-card kpi-section">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.75rem;margin-bottom:1.25rem;">
          <div>
            <h2 class="font-editorial" style="font-size:var(--text-3xl);">Admin Governance Console</h2>
            <p style="font-size:var(--text-xs);color:var(--text-secondary);">
              Real-time operations across shared database tables (<code>orders</code>, <code>refunds</code>, <code>inventory</code>, <code>business_config</code>, <code>audit_log</code>).
            </p>
          </div>
          <span class="chip-pill active">
            ${renderIcon("shield", "xs")}
            <span>Authenticated as: ${state.actor.label}</span>
          </span>
        </div>

        <div class="kpi-row" style="margin-bottom:0;">
          <div class="kpi-tile">
            <div class="kpi-tile-label">Total Orders</div>
            <div class="kpi-tile-value">${ordStats.total_orders}</div>
          </div>
          <div class="kpi-tile">
            <div class="kpi-tile-label">Cumulative Revenue</div>
            <div class="kpi-tile-value">${formatInr(ordStats.total_revenue_inr)}</div>
          </div>
          <div class="kpi-tile">
            <div class="kpi-tile-label">Registered Customers</div>
            <div class="kpi-tile-value">${cusStats.total_customers}</div>
          </div>
          <div class="kpi-tile">
            <div class="kpi-tile-label">Repeat Buyer Retention</div>
            <div class="kpi-tile-value">${cusStats.retention_rate_pct}%</div>
          </div>
        </div>
      </div>

      <div class="page-grid-2col">
        <div class="surface-card">
          <h3 class="font-editorial" style="font-size:var(--text-2xl);margin-bottom:0.75rem;">
            4-Tier Refund Approval Queue
          </h3>
          ${
            state.adminRefunds.length === 0
              ? `<p style="font-size:var(--text-xs);color:var(--text-secondary);">No refund requests in queue.</p>`
              : `<div style="display:flex;flex-direction:column;gap:0.65rem;">
                  ${state.adminRefunds
                    .map(
                      (r) => `
                      <div style="padding:0.9rem;border-radius:16px;background:var(--bg-page);border:1px solid var(--border-subtle);font-size:12px;">
                        <div style="display:flex;justify-content:space-between;font-weight:600;margin-bottom:0.25rem;">
                          <span>${r.refund_id} · Order ${r.order_id} · ${formatInr(r.amount_inr)}</span>
                          <span class="meta-tag">Tier ${r.approval_tier} · ${r.status_label || r.status}</span>
                        </div>
                        <div style="font-size:11px;color:var(--text-secondary);margin-bottom:0.55rem;">
                          Primary Approver: ${r.approved_by || "Pending"} ${
                            r.secondary_approved_by ? "· Secondary Approver: " + r.secondary_approved_by : ""
                          }
                        </div>
                        <div style="display:flex;gap:0.45rem;">
                          ${
                            r.awaiting_approval
                              ? `<button
                                  class="btn-pill"
                                  style="padding:0.38rem 0.9rem;font-size:11px;min-height:34px;"
                                  data-action="admin-approve-refund"
                                  data-refund-id="${r.refund_id}"
                                >
                                  Approve as ${state.actor.role}
                                </button>`
                              : ""
                          }
                          ${
                            r.status === "approved"
                              ? `<button
                                  class="btn-pill btn-pill-outline"
                                  style="padding:0.38rem 0.9rem;font-size:11px;min-height:34px;"
                                  data-action="admin-process-refund"
                                  data-refund-id="${r.refund_id}"
                                >
                                  Disburse Payout & Restock
                                </button>`
                              : ""
                          }
                        </div>
                      </div>
                    `
                    )
                    .join("")}
                </div>`
          }
        </div>

        <div class="surface-card">
          <h3 class="font-editorial" style="font-size:var(--text-2xl);margin-bottom:0.75rem;">
            Warehouse Garment Inventory
          </h3>
          <div style="display:flex;flex-direction:column;gap:0.6rem;">
            ${state.adminInventory
              .map(
                (inv) => `
                <div style="display:flex;justify-content:space-between;align-items:center;padding:0.75rem 0.9rem;border-radius:14px;background:var(--bg-page);border:1px solid var(--border-subtle);font-size:12px;">
                  <div>
                    <strong>${inv.product_id}</strong> · ${inv.name}
                    <div style="font-size:11px;color:var(--text-secondary);">
                      Available: ${inv.quantity_available} · Reserved: ${inv.quantity_reserved}
                    </div>
                  </div>
                  <button
                    class="chip-pill"
                    data-action="admin-restock-sku"
                    data-product-id="${inv.product_id}"
                    data-current-stock="${inv.quantity_available}"
                  >
                    +10 Units
                  </button>
                </div>
              `
              )
              .join("")}
          </div>
        </div>
      </div>

      <div class="surface-card">
        <h3 class="font-editorial" style="font-size:var(--text-2xl);margin-bottom:0.35rem;">
          Live Business Config Policy Editor (<code>PUT /api/admin/config/policies</code>)
        </h3>
        <p style="font-size:var(--text-xs);color:var(--text-secondary);margin-bottom:1rem;">
          Updates the database <code>business_config</code> shipping rules in real time and appends a signed record to <code>audit_log</code>.
        </p>
        <form data-form="admin-policy-form" class="admin-policy-grid" novalidate>
          <div class="field-group">
            <label class="field-label" for="cfg-free-ship">Free Shipping Threshold (₹) *</label>
            <input
              id="cfg-free-ship"
              class="field-input ${pErr.freeShippingThresholdInr ? "invalid" : ""}"
              type="number"
              aria-invalid="${Boolean(pErr.freeShippingThresholdInr)}"
              value="${state.policyConfigForm.freeShippingThresholdInr}"
            />
            ${pErr.freeShippingThresholdInr ? `<span class="field-error">${pErr.freeShippingThresholdInr}</span>` : ""}
          </div>
          <div class="field-group">
            <label class="field-label" for="cfg-ship-fee">Standard Courier Fee (₹) *</label>
            <input
              id="cfg-ship-fee"
              class="field-input ${pErr.standardShippingFeeInr ? "invalid" : ""}"
              type="number"
              aria-invalid="${Boolean(pErr.standardShippingFeeInr)}"
              value="${state.policyConfigForm.standardShippingFeeInr}"
            />
            ${pErr.standardShippingFeeInr ? `<span class="field-error">${pErr.standardShippingFeeInr}</span>` : ""}
          </div>
          <div class="field-group">
            <label class="field-label" for="cfg-reason">Governance Audit Reason *</label>
            <input
              id="cfg-reason"
              class="field-input ${pErr.reason ? "invalid" : ""}"
              type="text"
              aria-invalid="${Boolean(pErr.reason)}"
              value="${state.policyConfigForm.reason}"
            />
            ${pErr.reason ? `<span class="field-error">${pErr.reason}</span>` : ""}
          </div>
          <button type="submit" class="btn-pill">
            ${renderIcon("check", "xs")}
            <span>Save to Database</span>
          </button>
        </form>
      </div>

      <div class="surface-card">
        <h3 class="font-editorial" style="font-size:var(--text-2xl);margin-bottom:0.75rem;">
          Immutable Audit Log (<code>GET /api/audit/log</code>)
        </h3>
        <div class="responsive-table-desktop">
          <table style="width:100%;border-collapse:collapse;font-size:12px;">
            <thead>
              <tr style="text-align:left;border-bottom:1px solid var(--border-strong);color:var(--text-secondary);">
                <th style="padding:0.55rem;">Trace ID</th>
                <th style="padding:0.55rem;">Actor</th>
                <th style="padding:0.55rem;">Resource</th>
                <th style="padding:0.55rem;">Action</th>
                <th style="padding:0.55rem;">Reason</th>
              </tr>
            </thead>
            <tbody>
              ${state.adminAuditLog
                .map(
                  (log) => `
                  <tr style="border-bottom:1px solid var(--border-subtle);">
                    <td style="padding:0.55rem;font-family:var(--font-mono);">${log.trace_id}</td>
                    <td style="padding:0.55rem;">${log.actor_type}:${log.actor_id}</td>
                    <td style="padding:0.55rem;">${log.resource_type}/${log.resource_id}</td>
                    <td style="padding:0.55rem;font-weight:600;">${log.action}</td>
                    <td style="padding:0.55rem;color:var(--text-secondary);">${log.reason || "—"}</td>
                  </tr>
                `
                )
                .join("")}
            </tbody>
          </table>
        </div>
        <div class="responsive-cards-mobile">
          ${state.adminAuditLog
            .map(
              (log) => `
              <div class="audit-mobile-card">
                <div style="display:flex;justify-content:space-between;font-weight:600;">
                  <span style="font-family:var(--font-mono);">${log.trace_id}</span>
                  <span class="meta-tag">${log.action}</span>
                </div>
                <div style="display:flex;justify-content:space-between;font-size:11px;">
                  <span style="color:var(--text-secondary);">Actor:</span>
                  <span>${log.actor_type}:${log.actor_id}</span>
                </div>
                <div style="display:flex;justify-content:space-between;font-size:11px;">
                  <span style="color:var(--text-secondary);">Resource:</span>
                  <span>${log.resource_type}/${log.resource_id}</span>
                </div>
                ${log.reason ? `<div style="font-size:11px;color:var(--text-secondary);">${log.reason}</div>` : ""}
              </div>
            `
            )
            .join("")}
        </div>
      </div>
    </div>
  `;
}

function renderShoppingBagDrawer() {
  if (state.activeDrawer !== "bag" && state.activeUiPrinciple !== "form_validation") return "";

  const items = state.cart?.items || [];
  const forceValidationDemo = state.activeUiPrinciple === "form_validation";
  const errors = forceValidationDemo
    ? validateCheckoutForm({ street: "abc", pinCode: "000", couponCode: "!" }).errors
    : state.checkoutValidationErrors;

  return `
    <div class="drawer-backdrop" data-action="close-drawer-backdrop">
      <aside class="slide-drawer" role="dialog" aria-modal="true" aria-label="Shopping Bag & Checkout">
        <div class="drawer-header">
          <div>
            <h3 class="font-editorial" style="font-size:var(--text-2xl);">Atelier Shopping Bag</h3>
            <span style="font-size:11px;color:var(--text-secondary);">
              ${items.reduce((s, i) => s + i.quantity, 0)} piece(s) · GST & Free Shipping calculated live
            </span>
          </div>
          <button class="heart-btn" data-action="close-drawer" aria-label="Close bag drawer" title="Close (Esc)">
            ${renderIcon("close", "sm")}
          </button>
        </div>

        <div class="drawer-body">
          ${
            items.length === 0 && !forceValidationDemo
              ? renderEmptyState({
                  title: "Your Atelier Bag is Empty",
                  description: "Select a tailored garment from the collection to add it to your bag.",
                  actionLabel: "Continue Shopping",
                  actionAttr: 'data-action="close-drawer"',
                })
              : `
                <div style="display:flex;flex-direction:column;gap:0.65rem;margin-bottom:1.25rem;">
                  ${items
                    .map(
                      (item) => `
                      <div style="display:flex;justify-content:space-between;align-items:center;padding:0.85rem;background:var(--bg-surface);border-radius:16px;border:1px solid var(--border-subtle);">
                        <div>
                          <div style="font-size:13px;font-weight:600;">${item.product_name}</div>
                          <div style="font-size:11px;color:var(--text-secondary);">
                            ${item.product_id} · Size ${item.size} · Qty ${item.quantity} · ${item.gst_rate_pct}% GST
                          </div>
                        </div>
                        <div style="text-align:right;">
                          <div style="font-size:13px;font-weight:700;">${formatInr(item.line_mrp_inr)}</div>
                          <button
                            class="section-link"
                            style="font-size:11px;color:var(--state-error-text);"
                            data-action="remove-cart-item"
                            data-cart-id="${item.cart_id}"
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    `
                    )
                    .join("")}
                </div>

                ${
                  state.cart
                    ? `
                  <div style="background:var(--bg-surface);border-radius:18px;padding:1rem;border:1px solid var(--border-subtle);margin-bottom:1.25rem;font-size:12px;">
                    <div style="display:flex;justify-content:space-between;margin-bottom:0.35rem;">
                      <span style="color:var(--text-secondary);">Subtotal (MRP incl. GST)</span>
                      <span>${formatInr(state.cart.subtotal_mrp_inr)}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;margin-bottom:0.35rem;">
                      <span style="color:var(--text-secondary);">Net Taxable + CGST/SGST</span>
                      <span>${formatInr(state.cart.taxable_value_inr)} + ${formatInr(state.cart.total_gst_inr)}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;margin-bottom:0.35rem;">
                      <span style="color:var(--text-secondary);">Express Courier</span>
                      <span>${state.cart.free_shipping_applied ? "Complimentary (₹0)" : formatInr(state.cart.shipping_fee_inr)}</span>
                    </div>
                    ${
                      state.couponResult?.valid
                        ? `<div style="display:flex;justify-content:space-between;color:var(--state-success-text);font-weight:600;">
                            <span>Promo (${state.couponResult.code})</span>
                            <span>-${formatInr(state.couponResult.discount_inr)}</span>
                          </div>`
                        : ""
                    }
                    <div style="display:flex;justify-content:space-between;font-weight:700;font-size:15px;padding-top:0.55rem;margin-top:0.55rem;border-top:1px solid var(--border-subtle);">
                      <span>Total Payable</span>
                      <span>${formatInr(
                        state.couponResult?.valid ? state.couponResult.new_total_inr : state.cart.grand_total_inr
                      )}</span>
                    </div>
                  </div>
                `
                    : ""
                }

                <form id="bag-checkout-form" data-form="checkout-form" style="display:flex;flex-direction:column;gap:0.75rem;" novalidate>
                  <div class="field-group">
                    <label class="field-label" for="checkout-street">Delivery Street Address *</label>
                    <input
                      id="checkout-street"
                      class="field-input ${errors.street ? "invalid" : ""}"
                      type="text"
                      aria-invalid="${Boolean(errors.street)}"
                      aria-describedby="${errors.street ? "err-checkout-street" : ""}"
                      value="${state.checkoutForm.street}"
                      placeholder="14 Cathedral Road, Gopalapuram"
                    />
                    ${errors.street ? `<span id="err-checkout-street" class="field-error">${errors.street}</span>` : ""}
                  </div>

                  <div class="checkout-2col-grid">
                    <div class="field-group">
                      <label class="field-label" for="checkout-pin">6-Digit PIN Code *</label>
                      <input
                        id="checkout-pin"
                        class="field-input ${errors.pinCode ? "invalid" : ""}"
                        type="text"
                        maxlength="6"
                        aria-invalid="${Boolean(errors.pinCode)}"
                        aria-describedby="${errors.pinCode ? "err-checkout-pin" : ""}"
                        value="${state.checkoutForm.pinCode}"
                        placeholder="600086"
                      />
                      ${errors.pinCode ? `<span id="err-checkout-pin" class="field-error">${errors.pinCode}</span>` : ""}
                    </div>

                    <div class="field-group">
                      <label class="field-label" for="checkout-coupon">Promo Code</label>
                      <div style="display:flex;gap:0.35rem;">
                        <input
                          id="checkout-coupon"
                          class="field-input ${errors.couponCode ? "invalid" : ""}"
                          type="text"
                          aria-invalid="${Boolean(errors.couponCode)}"
                          value="${state.checkoutForm.couponCode}"
                          placeholder="ATELIER10"
                        />
                        <button type="button" class="chip-pill" data-action="apply-coupon">Apply</button>
                      </div>
                      ${errors.couponCode ? `<span class="field-error">${errors.couponCode}</span>` : ""}
                      ${
                        state.availableCoupons.length > 0
                          ? `<div style="display:flex;gap:0.3rem;flex-wrap:wrap;margin-top:0.2rem;">
                              ${state.availableCoupons
                                .map(
                                  (c) => `
                                  <button type="button" class="meta-tag" style="cursor:pointer;border:none;" data-action="select-coupon-chip" data-code="${c.code}">
                                    ${c.code} (${c.discount_pct}% off)
                                  </button>
                                `
                                )
                                .join("")}
                            </div>`
                          : ""
                      }
                    </div>
                  </div>

                  <div class="field-group">
                    <label class="field-label" for="checkout-payment-method">Payment Method (Database Enabled)</label>
                    <select id="checkout-payment-method" class="field-input" style="font-size:12px;">
                      ${state.paymentMethods
                        .map((pm) => {
                          const code = pm.method_id || pm.method_code;
                          const label = pm.name || pm.display_name || code;
                          return `<option value="${code}" ${state.checkoutForm.paymentMethod === code ? "selected" : ""}>${label}</option>`;
                        })
                        .join("")}
                    </select>
                  </div>

                  <button type="submit" class="btn-pill" style="width:100%;margin-top:0.4rem;">
                    ${renderIcon("check", "xs")}
                    <span>Place Verified Order</span>
                  </button>
                </form>
              `
          }
        </div>
      </aside>
    </div>
  `;
}

function renderAiConciergeDrawer() {
  if (state.activeDrawer !== "ai") return "";

  const agentOptions = [
    `<option value="">Supervisor Auto-Router (All 9 Agents)</option>`,
    ...state.agentRegistry.map(
      (a) =>
        `<option value="${a.agent_name}" ${state.agentPreferred === a.agent_name ? "selected" : ""}>${a.agent_name} (${a.service_account})</option>`
    ),
  ].join("");

  const quickPrompts = (state.businessConfig?.storefront_ui?.ai_quick_prompts || []).map((p) => p.prompt);

  return `
    <div class="drawer-backdrop" data-action="close-drawer-backdrop">
      <aside class="slide-drawer" role="dialog" aria-modal="true" aria-label="AI Stylist & 9-Agent Copilot">
        <div class="drawer-header">
          <div>
            <h3 class="font-editorial" style="font-size:var(--text-2xl);">
              ${renderIcon("sparkles", "sm")}
              <span>Noir Atelier AI Stylist</span>
            </h3>
            <span style="font-size:11px;color:var(--text-secondary);">
              Powered by 9 specialized agents calling shared <code>/api/*</code> endpoints
            </span>
          </div>
          <button class="heart-btn" data-action="close-drawer" aria-label="Close AI Stylist drawer" title="Close (Esc)">
            ${renderIcon("close", "sm")}
          </button>
        </div>

        <div class="drawer-body" style="display:flex;flex-direction:column;gap:0.85rem;">
          <label class="sr-only" for="agent-preferred-select">Select Agent</label>
          <select id="agent-preferred-select" class="field-input" style="font-size:12px;">
            ${agentOptions}
          </select>

          <div style="display:flex;gap:0.4rem;flex-wrap:wrap;">
            ${quickPrompts
              .map(
                (qp) => `
                <button
                  class="chip-pill"
                  style="font-size:11px;padding:0.3rem 0.7rem;"
                  data-action="send-quick-prompt"
                  data-prompt="${qp}"
                >
                  ${qp}
                </button>
              `
              )
              .join("")}
          </div>

          <div style="display:flex;flex-direction:column;gap:0.75rem;flex:1;">
            ${
              state.agentMessages.length === 0
                ? `<div style="padding:1rem;background:var(--bg-surface);border-radius:16px;border:1px solid var(--border-subtle);font-size:12px;color:var(--text-secondary);line-height:1.55;">
                    Welcome to <strong>Noir Atelier Personal Stylist & Concierge</strong>. Ask me to find garments by fabric or budget, add pieces to your bag, place an order (e.g. <em>"Buy 2 Minimalist Pima Cotton Tee"</em>), cancel an order, or start a return.
                  </div>`
                : state.agentMessages
                    .map((m) => {
                      const friendlyAgentTitle =
                        state.agentRegistry.find((a) => a.agent_name === m.routed_agent)?.persona ||
                        m.routed_agent ||
                        "Atelier Assistant";

                      const statusBadgeLabel =
                        {
                          action_completed: "Action Completed",
                          pending_approval: "Sent for Approval",
                          escalated: "Concierge Assigned",
                          clarify_missing_info: "Needs Details",
                          blocked_unauthorized: "Access Restricted",
                          blocked_prompt_injection: "Security Guardrail",
                          error: "Action Failed",
                          answer: "Verified Answer",
                        }[m.status] || "Verified";

                      const fb = m.data?.action_feedback;
                      const chatProducts = Array.isArray(m.data?.products) ? m.data.products.slice(0, 4) : [];

                      return `
                      <div style="padding:0.9rem 1.05rem;border-radius:16px;font-size:12.5px;background:${
                        m.role === "user" ? "var(--accent-noir)" : "var(--bg-surface)"
                      };color:${m.role === "user" ? "var(--text-on-dark)" : "var(--text-primary)"};border:${
                        m.status === "action_completed" ? "1.5px solid var(--state-success-border)" : "1px solid var(--border-subtle)"
                      };">
                        ${
                          m.role === "agent"
                            ? `<div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;margin-bottom:0.45rem;">
                                <span style="font-weight:700;color:var(--text-primary);">${friendlyAgentTitle}</span>
                                <span class="meta-tag">${statusBadgeLabel}</span>
                              </div>`
                            : ""
                        }
                        <div style="white-space:pre-line;line-height:1.55;">${m.text}</div>
                        ${
                          fb
                            ? `<div style="margin-top:0.65rem;padding:0.75rem 0.9rem;border-radius:14px;background:${
                                m.status === "action_completed" ? "var(--state-success-bg)" : "var(--bg-page)"
                              };border:${
                                m.status === "action_completed" ? "1px solid var(--state-success-border)" : "1px solid var(--border-subtle)"
                              };">
                                <div style="display:flex;justify-content:space-between;align-items:center;gap:0.5rem;margin-bottom:0.25rem;">
                                  <strong style="font-size:12.5px;">${fb.title}</strong>
                                  ${fb.badge ? `<span class="meta-tag" style="font-size:10px;">${fb.badge}</span>` : ""}
                                </div>
                                ${fb.summary ? `<div style="font-size:11.5px;color:var(--text-secondary);">${fb.summary}</div>` : ""}
                                ${
                                  Array.isArray(fb.details) && fb.details.length
                                    ? `<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.35rem 0.75rem;padding-top:0.45rem;margin-top:0.45rem;border-top:1px solid var(--border-subtle);font-size:11px;">
                                        ${fb.details
                                          .map((d) => `<div><span style="color:var(--text-secondary);">${d.label}: </span><strong>${d.value}</strong></div>`)
                                          .join("")}
                                      </div>`
                                    : ""
                                }
                                ${
                                  fb.cta_drawer
                                    ? `<div style="margin-top:0.6rem;">
                                        <button type="button" class="btn-pill" style="padding:0.35rem 0.85rem;font-size:11px;min-height:32px;" data-action="open-drawer" data-drawer="${fb.cta_drawer}">
                                          <span>${fb.cta_label || "Open"}</span>
                                        </button>
                                      </div>`
                                    : fb.cta_page
                                    ? `<div style="margin-top:0.6rem;">
                                        <button type="button" class="btn-pill" style="padding:0.35rem 0.85rem;font-size:11px;min-height:32px;" data-action="nav-page" data-page="${fb.cta_page}">
                                          <span>${fb.cta_label || "View Details"}</span>
                                        </button>
                                      </div>`
                                    : ""
                                }
                              </div>`
                            : ""
                        }
                        ${
                          chatProducts.length
                            ? `<div style="display:flex;flex-direction:column;gap:0.45rem;margin-top:0.65rem;">
                                ${chatProducts
                                  .map(
                                    (cp) => `
                                    <div style="display:flex;justify-content:space-between;align-items:center;gap:0.6rem;padding:0.55rem 0.75rem;border-radius:12px;background:var(--bg-page);border:1px solid var(--border-subtle);">
                                      <div>
                                        <div style="font-weight:600;font-size:12px;">${cp.name}</div>
                                        <div style="font-size:11px;color:var(--text-secondary);">${formatInr(cp.mrp_inr)} · ${cp.department} · Sizes: ${(cp.sizes_available || []).join(", ")}</div>
                                      </div>
                                      <div style="display:flex;gap:0.35rem;flex-shrink:0;">
                                        <button type="button" class="chip-pill" style="padding:0.28rem 0.65rem;font-size:11px;min-height:28px;" data-action="add-to-cart" data-product-id="${cp.product_id}">+ Bag</button>
                                        <button type="button" class="btn-pill" style="padding:0.28rem 0.7rem;font-size:11px;min-height:28px;" data-action="send-quick-prompt" data-prompt="Buy 1 ${cp.name} in size ${(cp.sizes_available || ["M"])[0]}">Buy Now</button>
                                      </div>
                                    </div>
                                  `
                                  )
                                  .join("")}
                              </div>`
                            : ""
                        }
                        ${
                          m.role === "agent" && (m.react_steps?.length || m.tool_traces?.length)
                            ? `<details style="margin-top:0.55rem;padding-top:0.4rem;border-top:1px dashed var(--border-subtle);font-size:10px;color:var(--text-secondary);">
                                <summary style="cursor:pointer;user-select:none;font-family:var(--font-mono);">
                                  Technical Trace (${m.routed_agent} · Steps ${m.steps_taken ?? 1}/${m.step_budget_max ?? 10})
                                </summary>
                                <div style="margin-top:6px;font-family:var(--font-mono);">
                                  ${(m.react_steps || []).map((s) => `<div>[${s.layer.toUpperCase()}] ${s.thought}</div>`).join("")}
                                  ${
                                    m.tool_traces?.length
                                      ? `<div style="margin-top:4px;">${m.tool_traces
                                          .map((t) => `${t.http_method} ${t.endpoint} [${t.risk_level || "read_only"}] → ${t.status_code} (${t.latency_ms}ms)`)
                                          .join(" · ")}</div>`
                                      : ""
                                  }
                                </div>
                              </details>`
                            : ""
                        }
                      </div>
                    `;
                    })
                    .join("")
            }
            ${state.agentBusy ? `<div class="shimmer" style="height:44px;border-radius:14px;"></div>` : ""}
          </div>
        </div>

        <div class="drawer-footer">
          <form data-form="agent-chat-form" style="display:flex;gap:0.5rem;">
            <label class="sr-only" for="agent-chat-input">Message AI Stylist</label>
            <input
              id="agent-chat-input"
              class="field-input"
              type="text"
              placeholder="Ask AI Stylist to search, add to bag, or return..."
            />
            <button type="submit" class="btn-pill">Send</button>
          </form>
        </div>
      </aside>
    </div>
  `;
}

function renderFooter() {
  const contrastRatio =
    state.theme === "dark"
      ? getContrastRatio("#f5f3ef", "#131312")
      : getContrastRatio("#181817", "#f6f4ef");

  return `
    <footer class="site-footer">
      <div class="site-footer-inner">
        <div>
          <strong>Noir Atelier</strong> · AI-Native Luxury Garment Commerce (HSN 61 & 62)
        </div>
        <div style="display:flex;gap:1.25rem;flex-wrap:wrap;font-family:var(--font-mono);font-size:11px;">
          <span>WCAG 2.2 AAA Contrast: ${contrastRatio}:1</span>
          <span>9 Specialized Agents · Shared /api/*</span>
          <span>3-Tier Design Tokens (${state.theme.toUpperCase()})</span>
        </div>
      </div>
    </footer>
  `;
}

function renderMobileBottomNav() {
  const cartCount = (state.cart?.items || []).reduce((acc, i) => acc + Number(i.quantity || 0), 0);
  return `
    <nav class="mobile-bottom-nav" aria-label="Mobile Bottom Navigation">
      <button
        type="button"
        class="mobile-tab-btn ${state.activePage === "shop" && !state.activeDrawer ? "active" : ""}"
        data-action="nav-page"
        data-page="shop"
      >
        ${renderIcon("home", "sm")}
        <span>The Edit</span>
      </button>
      <button
        type="button"
        class="mobile-tab-btn ${state.activePage === "orders" && !state.activeDrawer ? "active" : ""}"
        data-action="nav-page"
        data-page="orders"
      >
        ${renderIcon("package", "sm")}
        <span>Orders (${state.orders.length})</span>
      </button>
      <button
        type="button"
        class="mobile-tab-btn ${state.activeDrawer === "ai" ? "active" : ""}"
        data-action="open-drawer"
        data-drawer="ai"
      >
        ${renderIcon("sparkles", "sm")}
        <span>AI Stylist</span>
      </button>
      <button
        type="button"
        class="mobile-tab-btn ${state.activeDrawer === "bag" ? "active" : ""}"
        data-action="open-drawer"
        data-drawer="bag"
      >
        ${renderIcon("bag", "sm")}
        <span>Bag (${cartCount})</span>
      </button>
      <button
        type="button"
        class="mobile-tab-btn ${state.activePage === "admin" && !state.activeDrawer ? "active" : ""}"
        data-action="nav-page"
        data-page="admin"
      >
        ${renderIcon("shield", "sm")}
        <span>Admin</span>
      </button>
    </nav>
  `;
}

export function renderApp() {
  const root = document.getElementById("noir-app");
  if (!root) return;

  let pageHtml = "";
  if (state.activePage === "orders") {
    pageHtml = renderOrdersAndReturnsPage();
  } else if (state.activePage === "policies") {
    pageHtml = renderPoliciesPage();
  } else if (state.activePage === "admin") {
    pageHtml = renderAdminConsolePage();
  } else {
    pageHtml = renderShopPage();
  }

  root.className = "web-app";
  root.innerHTML = `
    ${renderHeader()}
    <main id="main-content" class="main-container" tabindex="-1">
      ${renderGlobalBanners()}
      ${pageHtml}
    </main>
    ${renderFooter()}
    ${renderProductDetailModal()}
    ${renderShoppingBagDrawer()}
    ${renderAiConciergeDrawer()}
    <div class="ai-widget-container" aria-live="polite">
      ${
        state.activeDrawer !== "ai"
          ? `
        <button
          type="button"
          class="ai-floating-trigger"
          data-action="open-drawer"
          data-drawer="ai"
          aria-label="Open Noir Atelier AI Stylist Concierge"
        >
          <span class="ai-trigger-sparkle">${renderIcon("sparkles", "sm")}</span>
          <span class="ai-trigger-label">AI Stylist</span>
          <span class="ai-trigger-ping" aria-hidden="true"></span>
        </button>
      `
          : ""
      }
    </div>
    ${renderMobileBottomNav()}
  `;
}

document.addEventListener("click", async (e) => {
  const target = e.target.closest("[data-action]");
  if (!target) return;
  const action = target.getAttribute("data-action");

  if (action === "toggle-theme") {
    state.theme = state.theme === "dark" ? "light" : "dark";
    applyTheme(state.theme);
    state.liveAnnouncement = `Switched to ${state.theme} theme.`;
    renderApp();
    return;
  }

  if (action === "toggle-diagnostics") {
    state.showDiagnosticsBar = !state.showDiagnosticsBar;
    renderApp();
    return;
  }

  if (action === "toggle-mobile-menu") {
    state.mobileMenuOpen = !state.mobileMenuOpen;
    renderApp();
    return;
  }

  if (action === "set-ui-principle") {
    const p = target.getAttribute("data-principle");
    state.activeUiPrinciple = p;
    if (p === "form_validation") state.activeDrawer = "bag";
    renderApp();
    return;
  }

  if (action === "nav-page") {
    state.activePage = target.getAttribute("data-page");
    state.activeUiPrinciple = "normal";
    state.permissionDeniedInfo = null;
    if (state.activePage === "admin") {
      await loadAdminDataFromDb();
    } else {
      renderApp();
    }
    return;
  }

  if (action === "nav-dept" || action === "filter-department") {
    state.activePage = "shop";
    state.selectedDepartment = target.getAttribute("data-department");
    state.activeUiPrinciple = "normal";
    await refreshProductsFromDb();
    return;
  }

  if (action === "quick-price-slab") {
    const mp = target.getAttribute("data-max-price");
    state.maxPrice = Number(state.maxPrice) === Number(mp) ? "" : mp;
    await refreshProductsFromDb();
    return;
  }

  if (action === "scroll-to-catalog") {
    document.getElementById("catalog-grid-anchor")?.scrollIntoView({ behavior: "smooth" });
    return;
  }

  if (action === "open-product-modal") {
    if (e.target.closest('[data-action="toggle-wishlist"]')) return;
    const pid = target.getAttribute("data-product-id");
    await openProductDetailModal(pid);
    return;
  }

  if (action === "close-product-modal") {
    state.detailModalProduct = null;
    renderApp();
    return;
  }

  if (action === "close-modal-backdrop") {
    if (e.target.classList.contains("detail-modal-backdrop")) {
      state.detailModalProduct = null;
      renderApp();
    }
    return;
  }

  if (action === "open-drawer") {
    state.activeDrawer = target.getAttribute("data-drawer");
    renderApp();
    return;
  }

  if (action === "close-drawer") {
    state.activeDrawer = null;
    if (state.activeUiPrinciple === "form_validation") state.activeUiPrinciple = "normal";
    renderApp();
    return;
  }

  if (action === "close-drawer-backdrop") {
    if (e.target.classList.contains("drawer-backdrop")) {
      state.activeDrawer = null;
      if (state.activeUiPrinciple === "form_validation") state.activeUiPrinciple = "normal";
      renderApp();
    }
    return;
  }

  if (action === "toggle-wishlist") {
    e.stopPropagation();
    const pid = target.getAttribute("data-product-id");
    if (state.wishlistIds.has(pid)) state.wishlistIds.delete(pid);
    else state.wishlistIds.add(pid);
    renderApp();
    return;
  }

  if (action === "select-card-size") {
    const pid = target.getAttribute("data-product-id");
    const sz = target.getAttribute("data-size");
    state.cardSizeSelection[pid] = sz;
    renderApp();
    return;
  }

  if (action === "clear-filters" || action === "reset-view" || action === "retry-load") {
    state.searchQuery = "";
    state.selectedDepartment = "ALL";
    state.selectedCategory = "";
    state.selectedColor = "";
    state.selectedMaterial = "";
    state.minPrice = "";
    state.maxPrice = "";
    state.sortBy = "featured";
    state.activeUiPrinciple = "normal";
    state.apiError = null;
    state.permissionDeniedInfo = null;
    state.sessionExpired = false;
    await bootstrapData();
    return;
  }

  if (action === "reconnect-network") {
    state.isOffline = false;
    state.activeUiPrinciple = "normal";
    await bootstrapData();
    return;
  }

  if (action === "renew-session") {
    state.sessionExpired = false;
    state.activeUiPrinciple = "normal";
    api.setToken(state.actor.token);
    await bootstrapData();
    return;
  }

  if (action === "switch-to-manager") {
    const mgr = state.actors.find((a) => a.role === "manager") || {
      token: "admin_manager",
      id: "MGR-001",
      role: "manager",
      label: "Store Manager (MGR-001)",
    };
    state.actor = mgr;
    api.setToken(state.actor.token);
    state.permissionDeniedInfo = null;
    state.activeUiPrinciple = "normal";
    if (state.activePage === "admin") await loadAdminDataFromDb();
    else await bootstrapData();
    return;
  }

  if (action === "select-coupon-chip") {
    const code = target.getAttribute("data-code");
    state.checkoutForm.couponCode = code;
    renderApp();
    return;
  }

  if (action === "dismiss-toast") {
    state.toastSuccess = null;
    if (state.activeUiPrinciple === "success") state.activeUiPrinciple = "normal";
    renderApp();
    return;
  }

  if (action === "add-to-cart") {
    const pid = target.getAttribute("data-product-id");
    const chosenSize = state.cardSizeSelection[pid] || "M";
    state.inFlightAction = `add:${pid}`;
    renderApp();
    try {
      state.cart = await api.addToCart({
        productId: pid,
        size: chosenSize,
        quantity: 1,
      });
      state.inFlightAction = null;
      state.detailModalProduct = null;
      state.activeDrawer = "bag";
      state.toastSuccess = {
        title: "Added to Atelier Bag",
        message: `${pid} (Size ${chosenSize}) added to your shopping bag.`,
      };
      state.liveAnnouncement = `${pid} size ${chosenSize} added to bag.`;
      renderApp();
    } catch (err) {
      state.inFlightAction = null;
      state.apiError = err;
      renderApp();
    }
    return;
  }

  if (action === "remove-cart-item") {
    const cartId = target.getAttribute("data-cart-id");
    state.cart = await api.removeCartItem(cartId);
    renderApp();
    return;
  }

  if (action === "apply-coupon") {
    const codeInput = document.getElementById("checkout-coupon");
    const code = (codeInput?.value || "ATELIER10").trim().toUpperCase();
    state.checkoutForm.couponCode = code;
    const subtotal = Number(state.cart?.subtotal_mrp_inr || 0);
    if (subtotal <= 0) return;
    state.couponResult = await api.validateCoupon(code, subtotal);
    renderApp();
    return;
  }

  if (action === "prefill-return-order") {
    state.returnForm.orderId = target.getAttribute("data-order-id");
    renderApp();
    return;
  }

  if (action === "cancel-order") {
    const oid = target.getAttribute("data-order-id");
    const cancelled = await api.cancelOrder(oid);
    state.orders = await api.listOrders();
    state.toastSuccess = {
      title: `Order ${oid} Cancelled (Tier 0)`,
      message: `Status updated to '${cancelled.status}' with full refund under policy POL-CAN-01.`,
    };
    renderApp();
    return;
  }

  if (action === "trigger-ai-prompt" || action === "send-quick-prompt") {
    const prompt = target.getAttribute("data-prompt");
    state.detailModalProduct = null;
    state.activeDrawer = "ai";
    await sendAgentChatMessage(prompt);
    return;
  }

  if (action === "admin-approve-refund") {
    const rfdId = target.getAttribute("data-refund-id");
    try {
      const updated = await api.approveRefund(rfdId, `Approved by ${state.actor.id}`, state.actor.token);
      state.toastSuccess = {
        title: `Refund ${rfdId} Updated`,
        message: `New status: ${updated.status}`,
      };
      await loadAdminDataFromDb();
    } catch (err) {
      state.apiError = err;
      renderApp();
    }
    return;
  }

  if (action === "admin-process-refund") {
    const rfdId = target.getAttribute("data-refund-id");
    const processed = await api.processRefund(rfdId, state.actor.token);
    state.toastSuccess = {
      title: `Refund ${rfdId} Disbursed`,
      message: `Payment Ref: ${processed.payment_refund_id} · Inventory restocked.`,
    };
    await loadAdminDataFromDb();
    return;
  }

  if (action === "admin-restock-sku") {
    const pid = target.getAttribute("data-product-id");
    const cur = Number(target.getAttribute("data-current-stock") || 0);
    await api.updateInventory(pid, cur + 10, "admin_portal_restock", state.actor.token);
    await loadAdminDataFromDb();
  }
});

document.addEventListener("change", async (e) => {
  const action = e.target.getAttribute("data-action");
  if (action === "change-font-scale") {
    state.fontScale = e.target.value;
    applyFontScale(state.fontScale);
    renderApp();
  } else if (action === "change-sort") {
    state.sortBy = e.target.value;
    await refreshProductsFromDb();
  } else if (action === "change-category") {
    state.selectedCategory = e.target.value;
    await refreshProductsFromDb();
  } else if (action === "change-color") {
    state.selectedColor = e.target.value;
    await refreshProductsFromDb();
  } else if (action === "change-material") {
    state.selectedMaterial = e.target.value;
    await refreshProductsFromDb();
  } else if (action === "change-actor") {
    const tok = e.target.value;
    const found = state.actors.find((a) => a.token === tok) || state.actors[0] || state.actor;
    state.actor = found;
    api.setToken(found.token);
    state.permissionDeniedInfo = null;
    if (state.activePage === "admin") {
      await loadAdminDataFromDb();
    } else {
      await bootstrapData();
    }
  } else if (e.target.id === "agent-preferred-select") {
    state.agentPreferred = e.target.value;
  }
});

document.addEventListener("submit", async (e) => {
  const formType = e.target.getAttribute("data-form");
  if (!formType) return;
  e.preventDefault();

  if (formType === "review-form") {
    const pid = e.target.getAttribute("data-product-id");
    const rating = Number(document.getElementById("review-rating-input")?.value || 5);
    const fitFeedback =
      document.getElementById("review-fit-input")?.value ||
      state.catalogMeta?.fit_feedback_options?.[0]?.code ||
      "true_to_size";
    const comment = (document.getElementById("review-comment-input")?.value || "").trim();
    if (!comment || !pid) return;
    await api.addProductReview(pid, { rating, fitFeedback, comment });
    state.detailModalProduct = await api.getProductDetails(pid);
    await refreshProductsFromDb();
    state.toastSuccess = {
      title: "Verified Review Saved to Database",
      message: `Your review for ${pid} was recorded in product_reviews.`,
    };
    renderApp();
    return;
  }

  if (formType === "catalog-search") {
    state.activePage = "shop";
    state.searchQuery = document.getElementById("catalog-search-input")?.value || "";
    state.activeUiPrinciple = "normal";
    await refreshProductsFromDb();
    return;
  }

  if (formType === "checkout-form") {
    state.checkoutForm.street = document.getElementById("checkout-street")?.value || "";
    state.checkoutForm.pinCode = document.getElementById("checkout-pin")?.value || "";
    state.checkoutForm.couponCode = document.getElementById("checkout-coupon")?.value || "";
    state.checkoutForm.paymentMethod = document.getElementById("checkout-payment-method")?.value || "upi";

    const check = validateCheckoutForm(state.checkoutForm);
    state.checkoutValidationErrors = check.errors;
    if (!check.valid) {
      renderApp();
      return;
    }

    try {
      const order = await api.createOrder({
        customerId: state.actor.role === "customer" ? state.actor.id : "CUS-001",
        couponCode: state.checkoutForm.couponCode || null,
        paymentMethod: state.checkoutForm.paymentMethod,
      });
      state.cart = await api.getCart();
      state.orders = await api.listOrders();
      state.returnForm.orderId = order.order_id;
      state.couponResult = null;
      state.activeDrawer = null;
      state.activeUiPrinciple = "normal";
      state.toastSuccess = {
        title: `Order ${order.order_id} Confirmed!`,
        message: `Total ${formatInr(order.grand_total_inr)} (incl. GST ${formatInr(order.total_gst_inr)}) · Invoice ${order.invoice_id}`,
      };
      state.activePage = "orders";
      await refreshProductsFromDb();
    } catch (err) {
      state.apiError = err;
      renderApp();
    }
    return;
  }

  if (formType === "return-form") {
    state.returnForm.orderId = (document.getElementById("return-order-id")?.value || "").trim().toUpperCase();
    state.returnForm.reasonCategory =
      document.getElementById("return-reason-category")?.value ||
      state.catalogMeta?.return_reasons?.[0]?.code ||
      "";
    state.returnForm.reasonNotes = document.getElementById("return-notes")?.value || "";
    state.returnForm.tagIntact = Boolean(document.getElementById("return-tag-intact")?.checked);

    const check = validateReturnForm(state.returnForm);
    state.returnValidationErrors = check.errors;
    if (!check.valid) {
      renderApp();
      return;
    }

    const reasonRow = (state.catalogMeta?.return_reasons || []).find(
      (r) => r.code === state.returnForm.reasonCategory
    );

    try {
      const res = await api.initiateReturn({
        orderId: state.returnForm.orderId,
        reasonCategory: state.returnForm.reasonCategory,
        customerNotes: state.returnForm.reasonNotes,
        tagIntact: state.returnForm.tagIntact,
        qcPassed: true,
        isDefectiveClaim: Boolean(reasonRow?.is_defect_claim),
      });
      state.orders = await api.listOrders();
      if (Number(res.approval_tier) >= 2) {
        const matchOrder = state.orders.find((o) => o.order_id === res.order_id);
        state.latestReturnEscalation = {
          returnId: res.return_id,
          refundId: res.refund_id,
          orderId: res.order_id,
          amountInr: matchOrder?.grand_total_inr || 7999,
          tier: res.approval_tier,
          ticketId: res.escalation_ticket_id,
          status: res.refund_status,
        };
      } else {
        state.toastSuccess = {
          title: `Return ${res.return_id} Auto-Approved (Tier 1)`,
          message: `Refund ${res.refund_id} processed and inventory restocked in database.`,
        };
      }
      renderApp();
    } catch (err) {
      state.apiError = err;
      renderApp();
    }
    return;
  }

  if (formType === "admin-policy-form") {
    state.policyConfigForm.freeShippingThresholdInr = Number(document.getElementById("cfg-free-ship")?.value ?? 1999);
    state.policyConfigForm.standardShippingFeeInr = Number(document.getElementById("cfg-ship-fee")?.value ?? 149);
    state.policyConfigForm.reason = document.getElementById("cfg-reason")?.value || "";

    const check = validatePolicyConfigForm(state.policyConfigForm);
    state.policyConfigErrors = check.errors;
    if (!check.valid) {
      renderApp();
      return;
    }

    try {
      await api.updateBusinessConfig(
        "shipping",
        {
          free_shipping_threshold_inr: state.policyConfigForm.freeShippingThresholdInr,
          standard_shipping_fee_inr: state.policyConfigForm.standardShippingFeeInr,
          express_shipping_fee_inr: 299,
        },
        state.policyConfigForm.reason,
        state.actor.token
      );
      state.toastSuccess = {
        title: "Database Policy Config Updated",
        message: `Complimentary shipping threshold updated to ₹${state.policyConfigForm.freeShippingThresholdInr} and recorded in audit_log.`,
      };
      await loadAdminDataFromDb();
    } catch (err) {
      state.apiError = err;
      renderApp();
    }
    return;
  }

  if (formType === "agent-chat-form") {
    const input = document.getElementById("agent-chat-input");
    const msg = (input?.value || "").trim();
    if (!msg) return;
    input.value = "";
    await sendAgentChatMessage(msg);
  }
});

async function sendAgentChatMessage(message) {
  state.agentMessages.push({ role: "user", text: message });
  state.agentBusy = true;
  renderApp();

  try {
    const res = await api.chatWithAgents({
      message,
      customerId: state.actor.role === "customer" ? state.actor.id : "CUS-001",
      actorRole: state.actor.role,
      preferredAgent: state.agentPreferred || null,
    });
    state.agentMessages.push({
      role: "agent",
      routed_agent: res.routed_agent,
      service_account: res.service_account,
      status: res.status,
      trace_id: res.trace_id,
      text: res.reply,
      data: res.data || {},
      tool_traces: res.tool_traces || [],
      react_steps: res.react_steps || [],
      steps_taken: res.steps_taken ?? 1,
      step_budget_max: res.step_budget_max ?? 10,
    });
    const [searchRes, updatedCart, updatedOrders] = await Promise.all([
      api
        .searchCatalog({
          q: state.searchQuery,
          department: state.selectedDepartment === "ALL" ? "" : state.selectedDepartment,
          category: state.selectedCategory,
          color: state.selectedColor,
          material: state.selectedMaterial,
          minPrice: state.minPrice || null,
          maxPrice: state.maxPrice || null,
          sort: state.sortBy,
        })
        .catch(() => ({ items: state.products, total: state.catalogTotal, interpretation: state.searchInterpretation })),
      api.getCart().catch(() => state.cart),
      api.listOrders().catch(() => state.orders),
    ]);
    state.products = Array.isArray(searchRes) ? searchRes : searchRes?.items || state.products;
    state.catalogTotal = typeof searchRes?.total === "number" ? searchRes.total : state.products.length;
    state.searchInterpretation = searchRes?.interpretation || state.searchInterpretation;
    state.cart = updatedCart;
    state.orders = updatedOrders;
    const fb = res.data?.action_feedback;
    if (fb && (res.status === "action_completed" || res.status === "pending_approval" || res.status === "escalated")) {
      state.toastSuccess = {
        title: fb.title || "Action Completed",
        message: fb.summary || res.reply,
      };
      state.liveAnnouncement = `${fb.title}. ${fb.summary || ""}`;
    }
  } catch (err) {
    state.agentMessages.push({
      role: "agent",
      routed_agent: "gateway_error",
      service_account: "none",
      status: "error",
      trace_id: err.trace_id || "TRC-ERR",
      text: err.message || "Could not reach /api/agents/chat.",
    });
  } finally {
    state.agentBusy = false;
    renderApp();
  }
}

bootstrapData();
