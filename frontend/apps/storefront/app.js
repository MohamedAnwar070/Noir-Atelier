import { NoirApiClient } from "/packages/api/client.js";
import {
  DESIGN_TOKENS,
  applyFontScale,
  deriveGarmentStyleFromProduct,
  renderGarmentArtwork,
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
  validateReturnForm,
} from "/packages/utils/formatters.js";

const ACTORS = [
  { token: "demo_CUS-001", id: "CUS-001", role: "customer", label: "CUS-001 · Arjun (VIP_GOLD)" },
  { token: "demo_CUS-002", id: "CUS-002", role: "customer", label: "CUS-002 · Priya (STANDARD)" },
  { token: "admin_manager", id: "MGR-001", role: "manager", label: "MGR-001 · Store Manager" },
  { token: "admin_finance", id: "FIN-001", role: "finance_admin", label: "FIN-001 · Finance Admin" },
];

const state = {
  viewMode: "showcase",
  activeSurface: "storefront",
  rightPaneTab: "detail",
  fontScale: "default",
  activeUiPrinciple: "normal",
  actor: ACTORS[0],

  isOffline: typeof navigator !== "undefined" ? !navigator.onLine : false,
  slowLatencyMs: null,
  isLoading: true,
  apiError: null,
  permissionDeniedInfo: null,
  sessionExpired: false,
  toastSuccess: null,
  latestReturnEscalation: null,

  businessConfig: {},
  policies: [],
  categories: [],
  products: [],
  selectedProduct: null,
  selectedSize: null,
  recommendations: [],
  wishlistIds: new Set(),

  searchQuery: "",
  selectedDepartment: "ALL",
  maxPrice: "",

  cart: null,
  customerAddress: { street: "", pinCode: "", city: "", state: "" },
  checkoutForm: { street: "", pinCode: "", couponCode: "", paymentMethod: "upi" },
  checkoutValidationErrors: {},
  couponResult: null,

  orders: [],
  returnForm: { orderId: "", reasonNotes: "", tagIntact: true, qcPassed: true },
  returnValidationErrors: {},

  agentRegistry: [],
  agentMessages: [],
  agentPreferred: "",
  agentInput: "",
  agentBusy: false,

  adminDashboard: null,
  adminInventory: [],
  adminRefunds: [],
  adminAuditLog: [],
};

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
      state.permissionDeniedInfo = {
        actorId: `${state.actor.id} (${state.actor.role})`,
        endpoint: evt.endpoint,
        message: evt.data?.message || "Insufficient permissions.",
      };
      renderApp();
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

async function bootstrapData() {
  state.isLoading = true;
  state.apiError = null;
  renderApp();

  try {
    const [cfgPayload, categories, products, cart, orders, registry] = await Promise.all([
      api.getPoliciesAndConfig(),
      api.listCategories(),
      api.searchProducts({
        q: state.searchQuery,
        department: state.selectedDepartment,
        maxPrice: state.maxPrice || null,
      }),
      api.getCart().catch(() => null),
      api.listOrders().catch(() => []),
      api.getAgentsRegistry().catch(() => []),
    ]);

    state.businessConfig = cfgPayload.business_config || {};
    state.policies = cfgPayload.policies || [];
    state.categories = Array.isArray(categories) ? categories : [];
    state.products = Array.isArray(products) ? products : [];
    state.cart = cart;
    state.orders = Array.isArray(orders) ? orders : [];
    state.agentRegistry = Array.isArray(registry) ? registry : [];

    if (state.actor.role === "customer") {
      const addresses = await api.listCustomerAddresses(state.actor.id).catch(() => []);
      if (addresses.length > 0) {
        const primary = addresses.find((a) => a.is_primary) || addresses[0];
        state.customerAddress = {
          street: primary.street,
          pinCode: primary.pin_code,
          city: primary.city,
          state: primary.state,
        };
        if (!state.checkoutForm.street) state.checkoutForm.street = primary.street;
        if (!state.checkoutForm.pinCode) state.checkoutForm.pinCode = primary.pin_code;
      }
    }

    if (state.orders.length > 0 && !state.returnForm.orderId) {
      state.returnForm.orderId = state.orders[0].order_id;
    }

    if (state.products.length > 0) {
      const currentId = state.selectedProduct?.product_id;
      const matched = state.products.find((p) => p.product_id === currentId) || state.products[0];
      await selectProductFromDb(matched.product_id, matched);
    } else {
      state.selectedProduct = null;
    }

    state.isLoading = false;
    renderApp();
  } catch (err) {
    state.isLoading = false;
    state.apiError = err;
    renderApp();
  }
}

async function selectProductFromDb(productId, initialProduct = null) {
  try {
    const detail = initialProduct || (await api.getProductDetails(productId));
    state.selectedProduct = detail;
    const availSizes = detail.sizes_available || [];
    if (!state.selectedSize || !availSizes.includes(state.selectedSize)) {
      state.selectedSize = availSizes.includes("M") ? "M" : availSizes[0] || "M";
    }
    state.recommendations = await api.getRecommendations(productId).catch(() => []);
  } catch (err) {
    state.apiError = err;
  }
}

async function refreshProductsFromDb() {
  state.isLoading = true;
  state.apiError = null;
  renderApp();
  try {
    state.products = await api.searchProducts({
      q: state.searchQuery,
      department: state.selectedDepartment,
      maxPrice: state.maxPrice || null,
    });
    if (state.products.length > 0 && !state.selectedProduct) {
      await selectProductFromDb(state.products[0].product_id, state.products[0]);
    }
    state.isLoading = false;
    renderApp();
  } catch (err) {
    state.isLoading = false;
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
    const [dashboard, inventory, refunds, auditLog] = await Promise.all([
      api.getAdminDashboard(state.actor.token),
      api.listInventory(false, state.actor.token),
      api.listRefunds(state.actor.token),
      api.getAuditLog(20, state.actor.token),
    ]);
    state.adminDashboard = dashboard;
    state.adminInventory = inventory;
    state.adminRefunds = refunds;
    state.adminAuditLog = auditLog;
    state.isLoading = false;
    renderApp();
  } catch (err) {
    state.isLoading = false;
    if (err.status !== 403 && err.status !== 401) {
      state.apiError = err;
    }
    renderApp();
  }
}

function renderToolbar() {
  const storeName = state.businessConfig?.store?.name || "Noir Atelier";
  const fontOptions = DESIGN_TOKENS.fontScales
    .map(
      (f) => `<option value="${f.id}" ${state.fontScale === f.id ? "selected" : ""}>Font: ${f.label}</option>`
    )
    .join("");

  const actorOptions = ACTORS.map(
    (a) => `<option value="${a.token}" ${state.actor.token === a.token ? "selected" : ""}>Actor: ${a.label}</option>`
  ).join("");

  const statePills = UI_PRINCIPLE_STATES.map(
    (st) => `
      <button
        class="state-pill-btn ${state.activeUiPrinciple === st.id ? "active" : ""}"
        data-action="set-ui-principle"
        data-principle="${st.id}"
      >
        ${st.label}
      </button>
    `
  ).join("");

  return `
    <header class="design-toolbar">
      <div class="toolbar-row">
        <div class="toolbar-brand">
          <span class="toolbar-brand-title">${storeName}</span>
          <span style="font-size:11px;opacity:0.72;">DB-Driven AI-Native Commerce · Men · Women · Kids</span>
        </div>
        <div class="toolbar-controls">
          <button
            class="state-pill-btn ${state.activeSurface === "storefront" ? "active" : ""}"
            data-action="switch-surface"
            data-surface="storefront"
          >
            Storefront & 9-Agents
          </button>
          <button
            class="state-pill-btn ${state.activeSurface === "admin" ? "active" : ""}"
            data-action="switch-surface"
            data-surface="admin"
          >
            Admin Governance Portal
          </button>
          <button
            class="state-pill-btn ${state.viewMode === "showcase" ? "active" : ""}"
            data-action="toggle-view-mode"
          >
            ${state.viewMode === "showcase" ? "📱 Twin-Phone Reference View" : "🖥️ Full Responsive Desktop"}
          </button>
          <select class="toolbar-select" data-action="change-font-scale" aria-label="Font scale">
            ${fontOptions}
          </select>
          <select class="toolbar-select" data-action="change-actor" aria-label="Active database actor">
            ${actorOptions}
          </select>
        </div>
      </div>
      <div class="states-strip" role="navigation" aria-label="UI Design Principle States">
        ${statePills}
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
    banners.push(renderSlowNetworkBanner({ latencyMs: state.slowLatencyMs || 1680 }));
  }
  if (state.toastSuccess || state.activeUiPrinciple === "success") {
    const t = state.toastSuccess || {
      title: "Database Transaction Confirmed",
      message: "Order persisted in PostgreSQL/SQLite with HSN 61/62 GST invoice and audit_log trace.",
    };
    banners.push(renderSuccessBanner(t));
  }

  return banners.length ? `<div class="global-banners">${banners.join("")}</div>` : "";
}

function renderLeftStorefrontPhone() {
  const cartCount = (state.cart?.items || []).reduce((acc, i) => acc + Number(i.quantity || 0), 0);
  const deptPills = [
    { code: "ALL", label: "All" },
    ...state.categories.map((c) => ({
      code: c.department,
      label: c.department.charAt(0) + c.department.slice(1).toLowerCase(),
    })),
  ];

  let catalogBody = "";

  if (state.isLoading || state.activeUiPrinciple === "loading") {
    catalogBody = `<div style="padding:0 1.1rem 1.4rem;">${renderLoadingState({ count: 4 })}</div>`;
  } else if (state.sessionExpired || state.activeUiPrinciple === "session_expired") {
    catalogBody = `<div style="padding:0 1.1rem 1.4rem;">${renderSessionExpiredState()}</div>`;
  } else if (state.permissionDeniedInfo || state.activeUiPrinciple === "permission_denied") {
    const info = state.permissionDeniedInfo || {
      actorId: `${state.actor.id} (${state.actor.role})`,
      endpoint: "PUT /api/admin/config/policies",
    };
    catalogBody = `<div style="padding:0 1.1rem 1.4rem;">${renderPermissionDeniedState(info)}</div>`;
  } else if (state.apiError || state.activeUiPrinciple === "error") {
    const err = state.apiError || {
      code: "db_query_error",
      message: "Database query returned an unexpected status.",
      trace_id: "TRC-502910",
    };
    catalogBody = `<div style="padding:0 1.1rem 1.4rem;">${renderErrorState({
      code: err.code,
      message: err.message,
      traceId: err.trace_id,
    })}</div>`;
  } else if (state.activeUiPrinciple === "empty") {
    catalogBody = `<div style="padding:0 1.1rem 1.4rem;">${renderEmptyState({
      title: "Catalog Collection Empty",
      description: "No garments are active in this collection yet. Refresh from database to load Men, Women & Kids garments.",
      actionLabel: "Reload From Database",
      actionAttr: 'data-action="clear-filters"',
    })}</div>`;
  } else if (state.products.length === 0 || state.activeUiPrinciple === "no_results") {
    catalogBody = `<div style="padding:0 1.1rem 1.4rem;">${renderNoSearchResultState({
      query: state.searchQuery,
      department: state.selectedDepartment,
      maxPrice: state.maxPrice,
    })}</div>`;
  } else {
    const cardsHtml = state.products
      .map((p) => {
        const isSelected = state.selectedProduct?.product_id === p.product_id;
        const isLiked = state.wishlistIds.has(p.product_id);
        const visual = deriveGarmentStyleFromProduct(p);
        return `
          <article
            class="garment-card ${isSelected ? "selected" : ""}"
            data-action="select-product"
            data-product-id="${p.product_id}"
          >
            <div class="garment-thumb" style="background:${visual.cardBg};">
              <button
                class="wishlist-btn ${isLiked ? "liked" : ""}"
                data-action="toggle-wishlist"
                data-product-id="${p.product_id}"
                aria-label="Save ${p.name}"
              >
                ♥
              </button>
              ${renderGarmentArtwork(p, "card")}
            </div>
            <div class="garment-title">${p.name}</div>
            <div class="garment-price-row">
              <span>${formatInr(p.mrp_inr)}</span>
              <span style="font-size:10px;">${p.department} · ★ ${p.average_rating ?? "5.0"}</span>
            </div>
          </article>
        `;
      })
      .join("");

    catalogBody = `<div class="product-grid">${cardsHtml}</div>`;
  }

  return `
    <section class="phone-device" aria-label="Storefront Discovery">
      <div class="phone-statusbar" style="color:#ffffff;">
        <span>9:41</span>
        <div class="phone-notch"></div>
        <span>5G · 100%</span>
      </div>
      <div class="phone-scroll">
        <div class="hero-editorial">
          <div class="hero-top-actions">
            <button class="icon-circle" data-action="focus-search" title="Search Catalog">🔍</button>
            <button class="icon-circle" data-action="open-right-tab" data-tab="bag" title="Shopping Bag">
              🛍️
              ${cartCount > 0 ? '<span class="badge-dot"></span>' : ""}
            </button>
            <button class="icon-circle" data-action="open-right-tab" data-tab="orders" title="Orders & Returns">📦</button>
            <button class="icon-circle" data-action="open-right-tab" data-tab="concierge" title="9-Agent AI Concierge">✨</button>
          </div>
          <div class="hero-copy">
            <h1>The New Edit</h1>
            <p>Explore timeless tailored linen, mulberry silk dresses & superfine merino garments</p>
            <button class="btn-pill" data-action="clear-filters" style="padding:0.58rem 1.35rem;font-size:12px;">
              Explore
            </button>
          </div>
          <div class="hero-editorial-figure">
            ${state.selectedProduct ? renderGarmentArtwork(state.selectedProduct, "card") : ""}
          </div>
        </div>

        <div class="section-header">
          <h2>Trending Now</h2>
          <button class="section-link" data-action="clear-filters">View all (${state.products.length})</button>
        </div>

        <form class="search-inline-bar" data-form="catalog-search">
          <input
            id="catalog-search-input"
            class="field-input"
            type="search"
            placeholder="Search linen, silk, merino, PRD-001..."
            value="${state.searchQuery}"
            style="padding:0.45rem 0.75rem;font-size:12px;border-radius:999px;"
          />
          <input
            id="catalog-max-price"
            class="field-input"
            type="number"
            placeholder="Max ₹"
            value="${state.maxPrice}"
            style="width:92px;padding:0.45rem 0.65rem;font-size:12px;border-radius:999px;"
          />
          <button type="submit" class="chip-pill active">Filter</button>
        </form>

        <div class="pill-tabs" role="tablist">
          ${deptPills
            .map(
              (d) => `
              <button
                class="chip-pill ${state.selectedDepartment === d.code ? "active" : ""}"
                data-action="filter-department"
                data-department="${d.code}"
              >
                ${d.label}
              </button>
            `
            )
            .join("")}
        </div>

        ${catalogBody}
      </div>
    </section>
  `;
}

function renderRightDetailOrWorkspacePhone() {
  const navTabs = [
    { id: "detail", label: "Garment Sheet" },
    { id: "bag", label: `Bag (${(state.cart?.items || []).reduce((s, i) => s + i.quantity, 0)})` },
    { id: "orders", label: `Orders (${state.orders.length})` },
    { id: "concierge", label: "9-Agent AI" },
  ];

  const tabStrip = `
    <div style="display:flex;gap:0.35rem;padding:0.55rem 1rem;background:var(--bg-subtle);border-bottom:1px solid var(--border-subtle);overflow-x:auto;">
      ${navTabs
        .map(
          (t) => `
          <button
            class="chip-pill ${state.rightPaneTab === t.id ? "active" : ""}"
            data-action="open-right-tab"
            data-tab="${t.id}"
            style="padding:0.32rem 0.8rem;font-size:11px;"
          >
            ${t.label}
          </button>
        `
        )
        .join("")}
    </div>
  `;

  let paneContent = "";
  if (state.activeUiPrinciple === "pending_approval") {
    paneContent = `<div style="padding:1.25rem;">${renderPendingApprovalState(
      state.latestReturnEscalation || {}
    )}</div>`;
  } else if (state.rightPaneTab === "bag" || state.activeUiPrinciple === "form_validation") {
    paneContent = renderShoppingBagAndCheckoutTab();
  } else if (state.rightPaneTab === "orders") {
    paneContent = renderOrdersAndReturnsTab();
  } else if (state.rightPaneTab === "concierge") {
    paneContent = renderAgentConciergeTab();
  } else {
    paneContent = renderGarmentDetailSheet();
  }

  return `
    <section class="phone-device" aria-label="Garment Detail & Client Workspace">
      <div class="phone-statusbar" style="color:${state.rightPaneTab === "detail" ? "#ffffff" : "var(--text-primary)"};">
        <span>9:41</span>
        <div class="phone-notch"></div>
        <span>5G · 100%</span>
      </div>
      ${state.rightPaneTab !== "detail" ? tabStrip : ""}
      <div class="phone-scroll">
        ${paneContent}
      </div>
      ${state.rightPaneTab === "detail" ? tabStrip : ""}
    </section>
  `;
}

function renderGarmentDetailSheet() {
  const p = state.selectedProduct;
  if (!p) {
    return `<div style="padding:1.5rem;">${renderEmptyState({
      title: "Select a Garment",
      description: "Choose any garment from the database catalog to inspect its HSN tax slab, fabric care, and size availability.",
    })}</div>`;
  }

  const visual = deriveGarmentStyleFromProduct(p);
  const taxInfo = computeGstSlabFromConfig(p.mrp_inr, state.businessConfig?.tax || {});
  const sizeBreakdown = p.size_breakdown || {};
  const sizes = p.sizes_available || [];
  const isLiked = state.wishlistIds.has(p.product_id);

  return `
    <div class="detail-hero-canvas" style="background:${visual.gradient};">
      <div class="detail-top-bar">
        <button class="icon-circle" data-action="open-right-tab" data-tab="bag" title="View Bag">←</button>
        <div style="display:flex;gap:0.45rem;">
          <button class="icon-circle" data-action="ask-agent-about-product" data-product-id="${p.product_id}" title="Ask AI Stylist">✨</button>
          <button
            class="icon-circle"
            data-action="toggle-wishlist"
            data-product-id="${p.product_id}"
            title="Wishlist"
          >
            ${isLiked ? "❤️" : "🤍"}
          </button>
        </div>
      </div>
      <div style="margin:auto 0;padding-top:0.5rem;">
        ${renderGarmentArtwork(p, "hero")}
      </div>
    </div>

    <div class="detail-sheet">
      <div>
        <div class="detail-title-row">
          <h2>${p.name}</h2>
          <span class="rating-pill">★ ${p.average_rating ?? "5.0"}</span>
        </div>

        <p class="detail-desc">${p.description} ${p.fit_guide}</p>

        <div class="detail-meta-strip">
          <span class="meta-tag">${p.product_id}</span>
          <span class="meta-tag">${p.department}</span>
          <span class="meta-tag">HSN ${p.hsn_code} · ${taxInfo.label}</span>
          <span class="meta-tag">${p.stock} in stock</span>
          ${p.security_tag_required ? '<span class="meta-tag">Ribbon QC Protected</span>' : ""}
        </div>

        <div class="field-label">SIZE (LIVE DB STOCK)</div>
        <div class="size-row">
          ${sizes
            .map((sz) => {
              const qty = sizeBreakdown[sz] ?? p.stock;
              const active = state.selectedSize === sz;
              return `
                <button
                  class="size-pill ${active ? "active" : ""}"
                  data-action="select-size"
                  data-size="${sz}"
                  ${qty <= 0 ? "disabled" : ""}
                  title="${qty} units available"
                >
                  ${sz}
                </button>
              `;
            })
            .join("")}
        </div>

        <div style="font-size:11px;color:var(--text-secondary);margin-bottom:0.85rem;">
          <strong>Fabric & Care:</strong> ${p.fabric_and_care}
        </div>
      </div>

      <div class="detail-footer-cta">
        <div>
          <div class="price-block-label">PRICE (MRP INCL. GST)</div>
          <div class="price-block-value">${formatInr(p.mrp_inr)}</div>
        </div>
        <button
          class="btn-pill"
          style="flex:1;max-width:210px;"
          data-action="add-to-cart"
          data-product-id="${p.product_id}"
          ${p.stock <= 0 ? "disabled" : ""}
        >
          Add to Cart
        </button>
      </div>
    </div>
  `;
}

function renderShoppingBagAndCheckoutTab() {
  const items = state.cart?.items || [];
  const forceValidationDemo = state.activeUiPrinciple === "form_validation";
  const errors = forceValidationDemo
    ? validateCheckoutForm({ street: "abc", pinCode: "000", couponCode: "!" }).errors
    : state.checkoutValidationErrors;

  if (items.length === 0 && !forceValidationDemo) {
    return `<div style="padding:1.25rem;">${renderEmptyState({
      title: "Your Shopping Bag is Empty",
      description: "Add a tailored garment from the catalog to compute real-time HSN 61/62 GST slabs and free shipping eligibility.",
      actionLabel: "Browse Garments",
      actionAttr: 'data-action="open-right-tab" data-tab="detail"',
    })}</div>`;
  }

  return `
    <div style="padding:1.1rem;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem;">
        <h3 class="font-editorial" style="font-size:var(--text-xl);">Atelier Shopping Bag</h3>
        ${items.length > 0 ? '<button class="section-link" data-action="clear-cart">Clear Bag</button>' : ""}
      </div>

      <div style="display:flex;flex-direction:column;gap:0.55rem;margin-bottom:1rem;">
        ${items
          .map(
            (item) => `
            <div style="display:flex;justify-content:space-between;align-items:center;padding:0.65rem 0.8rem;background:var(--bg-surface);border-radius:14px;border:1px solid var(--border-subtle);">
              <div>
                <div style="font-size:12px;font-weight:600;">${item.product_name}</div>
                <div style="font-size:11px;color:var(--text-secondary);">
                  ${item.product_id} · Size ${item.size} · Qty ${item.quantity} · GST ${item.gst_rate_pct}%
                </div>
              </div>
              <div style="text-align:right;">
                <div style="font-size:12px;font-weight:600;">${formatInr(item.line_mrp_inr)}</div>
                <button class="section-link" style="font-size:10px;color:#b91c1c;" data-action="remove-cart-item" data-cart-id="${item.cart_id}">Remove</button>
              </div>
            </div>
          `
          )
          .join("")}
      </div>

      ${
        state.cart
          ? `
        <div style="background:var(--bg-surface);border-radius:16px;padding:0.85rem;border:1px solid var(--border-subtle);margin-bottom:1rem;font-size:12px;">
          <div style="display:flex;justify-content:space-between;margin-bottom:0.25rem;">
            <span style="color:var(--text-secondary);">Subtotal (MRP incl. GST)</span>
            <span>${formatInr(state.cart.subtotal_mrp_inr)}</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:0.25rem;">
            <span style="color:var(--text-secondary);">Taxable Value + CGST/SGST</span>
            <span>${formatInr(state.cart.taxable_value_inr)} + ${formatInr(state.cart.total_gst_inr)}</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:0.25rem;">
            <span style="color:var(--text-secondary);">Shipping (${state.cart.free_shipping_applied ? "Free >= ₹" + (state.businessConfig?.shipping?.free_shipping_threshold_inr ?? 1999) : "Standard"})</span>
            <span>${formatInr(state.cart.shipping_fee_inr)}</span>
          </div>
          ${
            state.couponResult?.valid
              ? `<div style="display:flex;justify-content:space-between;color:var(--state-success-text);font-weight:600;">
                  <span>Coupon (${state.couponResult.code})</span>
                  <span>-${formatInr(state.couponResult.discount_inr)}</span>
                </div>`
              : ""
          }
          <div style="display:flex;justify-content:space-between;font-weight:700;font-size:14px;padding-top:0.45rem;margin-top:0.45rem;border-top:1px solid var(--border-subtle);">
            <span>Grand Total</span>
            <span>${formatInr(state.couponResult?.valid ? state.couponResult.new_total_inr : state.cart.grand_total_inr)}</span>
          </div>
        </div>
      `
          : ""
      }

      <form data-form="checkout-form" style="display:flex;flex-direction:column;gap:0.65rem;">
        <div class="field-group">
          <label class="field-label" for="checkout-street">Delivery Street Address *</label>
          <input
            id="checkout-street"
            class="field-input ${errors.street ? "invalid" : ""}"
            type="text"
            value="${state.checkoutForm.street}"
            placeholder="14 Cathedral Road, Gopalapuram"
          />
          ${errors.street ? `<span class="field-error">${errors.street}</span>` : ""}
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;">
          <div class="field-group">
            <label class="field-label" for="checkout-pin">6-Digit PIN Code *</label>
            <input
              id="checkout-pin"
              class="field-input ${errors.pinCode ? "invalid" : ""}"
              type="text"
              maxlength="6"
              value="${state.checkoutForm.pinCode}"
              placeholder="600086"
            />
            ${errors.pinCode ? `<span class="field-error">${errors.pinCode}</span>` : ""}
          </div>

          <div class="field-group">
            <label class="field-label" for="checkout-coupon">Promo Code</label>
            <div style="display:flex;gap:0.35rem;">
              <input
                id="checkout-coupon"
                class="field-input ${errors.couponCode ? "invalid" : ""}"
                type="text"
                value="${state.checkoutForm.couponCode}"
                placeholder="ATELIER10"
              />
              <button type="button" class="chip-pill" data-action="apply-coupon">Apply</button>
            </div>
            ${errors.couponCode ? `<span class="field-error">${errors.couponCode}</span>` : ""}
          </div>
        </div>

        <button type="submit" class="btn-pill" style="width:100%;margin-top:0.3rem;">
          Complete Verified Order (UPI / Card)
        </button>
      </form>
    </div>
  `;
}

function renderOrdersAndReturnsTab() {
  const retErrors = state.returnValidationErrors;

  return `
    <div style="padding:1.1rem;display:flex;flex-direction:column;gap:1rem;">
      <div>
        <h3 class="font-editorial" style="font-size:var(--text-xl);margin-bottom:0.5rem;">Your Database Orders</h3>
        ${
          state.orders.length === 0
            ? renderEmptyState({
                title: "No Orders Yet",
                description: "Orders placed via Storefront or the Order Agent appear here with live status & GST invoices.",
                actionLabel: "Shop Collection",
                actionAttr: 'data-action="open-right-tab" data-tab="detail"',
              })
            : `<div style="display:flex;flex-direction:column;gap:0.55rem;">
                ${state.orders
                  .map(
                    (o) => `
                    <div style="background:var(--bg-surface);border-radius:14px;padding:0.75rem;border:1px solid var(--border-subtle);font-size:12px;">
                      <div style="display:flex;justify-content:space-between;font-weight:600;margin-bottom:0.25rem;">
                        <span>${o.order_id} · ${formatInr(o.grand_total_inr)}</span>
                        <span class="meta-tag">${o.status}</span>
                      </div>
                      <div style="font-size:11px;color:var(--text-secondary);margin-bottom:0.45rem;">
                        Invoice: ${o.invoice_id || "—"} · GST: ${formatInr(o.total_gst_inr)}
                      </div>
                      <div style="display:flex;gap:0.4rem;">
                        <button class="chip-pill" style="font-size:10px;padding:0.22rem 0.6rem;" data-action="prefill-return-order" data-order-id="${o.order_id}">
                          Initiate Return
                        </button>
                        ${
                          o.status === "confirmed" || o.status === "processing"
                            ? `<button class="chip-pill" style="font-size:10px;padding:0.22rem 0.6rem;color:#b91c1c;" data-action="cancel-order" data-order-id="${o.order_id}">
                                Cancel (Tier 0)
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

      ${state.latestReturnEscalation ? renderPendingApprovalState(state.latestReturnEscalation) : ""}

      <form data-form="return-form" style="background:var(--bg-surface);border-radius:18px;padding:0.95rem;border:1px solid var(--border-subtle);display:flex;flex-direction:column;gap:0.6rem;">
        <h4 class="font-editorial" style="font-size:var(--text-lg);">4-Tier Garment Return & QC</h4>
        <div class="field-group">
          <label class="field-label" for="return-order-id">Order ID *</label>
          <input
            id="return-order-id"
            class="field-input ${retErrors.orderId ? "invalid" : ""}"
            type="text"
            value="${state.returnForm.orderId}"
            placeholder="ORD-1001"
          />
          ${retErrors.orderId ? `<span class="field-error">${retErrors.orderId}</span>` : ""}
        </div>

        <div class="field-group">
          <label class="field-label" for="return-notes">Return Reason & Fit Notes *</label>
          <input
            id="return-notes"
            class="field-input ${retErrors.reasonNotes ? "invalid" : ""}"
            type="text"
            value="${state.returnForm.reasonNotes}"
            placeholder="Slightly tight across shoulders"
          />
          ${retErrors.reasonNotes ? `<span class="field-error">${retErrors.reasonNotes}</span>` : ""}
        </div>

        <label style="display:flex;align-items:center;gap:0.45rem;font-size:11px;cursor:pointer;">
          <input id="return-tag-intact" type="checkbox" ${state.returnForm.tagIntact ? "checked" : ""} />
          <span>Noir Atelier security ribbon & tags intact (POL-RET-01)</span>
        </label>
        ${retErrors.tagIntact ? `<span class="field-error">${retErrors.tagIntact}</span>` : ""}

        <button type="submit" class="btn-pill" style="width:100%;">Submit Return to /api/returns</button>
      </form>
    </div>
  `;
}

function renderAgentConciergeTab() {
  const agentOptions = [
    `<option value="">Auto-Route (Supervisor Intent Router)</option>`,
    ...state.agentRegistry.map(
      (a) =>
        `<option value="${a.agent_name}" ${state.agentPreferred === a.agent_name ? "selected" : ""}>${a.agent_name} (${a.service_account})</option>`
    ),
  ].join("");

  const quickPrompts = [
    "Show me Women's garments",
    "What are the return policy rules and GST slabs?",
    "Add PRD-001 size M to my shopping bag",
    "Show GMV and order analytics report",
  ];

  return `
    <div style="padding:1rem;display:flex;flex-direction:column;height:100%;justify-content:space-between;gap:0.75rem;">
      <div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
          <h3 class="font-editorial" style="font-size:var(--text-xl);">9-Agent AI Concierge</h3>
          <span class="meta-tag">HTTP /api/agents/chat</span>
        </div>

        <select id="agent-preferred-select" class="field-input" style="font-size:11px;padding:0.4rem 0.65rem;margin-bottom:0.55rem;">
          ${agentOptions}
        </select>

        <div style="display:flex;gap:0.35rem;flex-wrap:wrap;margin-bottom:0.65rem;">
          ${quickPrompts
            .map(
              (qp) => `
              <button class="chip-pill" style="font-size:10px;padding:0.25rem 0.6rem;" data-action="send-quick-prompt" data-prompt="${qp}">
                ${qp}
              </button>
            `
            )
            .join("")}
        </div>

        <div style="display:flex;flex-direction:column;gap:0.55rem;max-height:380px;overflow-y:auto;">
          ${
            state.agentMessages.length === 0
              ? `<div style="padding:0.85rem;background:var(--bg-surface);border-radius:14px;border:1px solid var(--border-subtle);font-size:12px;color:var(--text-secondary);">
                  Ask anything about Men, Women, or Kids garments, cart coupons, order status, 4-tier returns, warehouse stock, or store policies. Every tool call executes live against <code>/api/*</code>.
                </div>`
              : state.agentMessages
                  .map(
                    (m) => `
                    <div style="padding:0.7rem 0.85rem;border-radius:14px;font-size:12px;background:${
                      m.role === "user" ? "var(--accent-noir)" : "var(--bg-surface)"
                    };color:${m.role === "user" ? "#ffffff" : "var(--text-primary)"};border:1px solid var(--border-subtle);">
                      ${
                        m.role === "agent"
                          ? `<div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text-muted);margin-bottom:0.25rem;font-family:var(--font-mono);">
                              <span>${m.routed_agent} (${m.service_account})</span>
                              <span>${m.status} · ${m.trace_id}</span>
                            </div>`
                          : ""
                      }
                      <div style="white-space:pre-line;">${m.text}</div>
                      ${
                        m.tool_traces?.length
                          ? `<div style="margin-top:0.4rem;padding-top:0.35rem;border-top:1px dashed var(--border-subtle);font-family:var(--font-mono);font-size:10px;color:var(--text-secondary);">
                              ${m.tool_traces
                                .map((t) => `${t.http_method} ${t.endpoint} → ${t.status_code} (${t.latency_ms}ms)`)
                                .join(" · ")}
                            </div>`
                          : ""
                      }
                    </div>
                  `
                  )
                  .join("")
          }
          ${state.agentBusy ? `<div class="shimmer" style="height:38px;border-radius:12px;"></div>` : ""}
        </div>
      </div>

      <form data-form="agent-chat-form" style="display:flex;gap:0.45rem;">
        <input
          id="agent-chat-input"
          class="field-input"
          type="text"
          placeholder="Message the 9-agent orchestrator..."
          value="${state.agentInput}"
        />
        <button type="submit" class="btn-pill" style="padding:0.55rem 1rem;">Send</button>
      </form>
    </div>
  `;
}

function renderAdminGovernanceSurface() {
  if (state.permissionDeniedInfo || state.actor.role === "customer") {
    return renderPermissionDeniedState({
      actorId: `${state.actor.id} (${state.actor.role})`,
      requiredRole: "Store Manager (MGR-001) or Finance Admin (FIN-001)",
      endpoint: "GET /api/admin/dashboard",
    });
  }

  if (state.isLoading) {
    return renderLoadingState({ count: 4, label: "Loading Admin Governance & Audit Log from database..." });
  }

  const ordStats = state.adminDashboard?.orders || { total_orders: 0, total_revenue_inr: 0 };
  const cusStats = state.adminDashboard?.customers || { total_customers: 0, retention_rate_pct: 0 };

  return `
    <div>
      <div class="panel-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.85rem;flex-wrap:wrap;gap:0.5rem;">
          <div>
            <h2 class="font-editorial" style="font-size:var(--text-2xl);">Noir Atelier Governance & Admin Console</h2>
            <p style="font-size:var(--text-xs);color:var(--text-secondary);">
              Connected to shared PostgreSQL/SQLite tables (<code>orders</code>, <code>returns</code>, <code>refunds</code>, <code>inventory</code>, <code>business_config</code>, <code>audit_log</code>).
            </p>
          </div>
          <span class="chip-pill active">Active Admin: ${state.actor.label}</span>
        </div>

        <div class="kpi-grid">
          <div class="kpi-box">
            <div class="kpi-box-label">Total Orders</div>
            <div class="kpi-box-value">${ordStats.total_orders}</div>
          </div>
          <div class="kpi-box">
            <div class="kpi-box-label">Total Revenue (INR)</div>
            <div class="kpi-box-value">${formatInr(ordStats.total_revenue_inr)}</div>
          </div>
          <div class="kpi-box">
            <div class="kpi-box-label">Registered Clients</div>
            <div class="kpi-box-value">${cusStats.total_customers}</div>
          </div>
          <div class="kpi-box">
            <div class="kpi-box-label">Repeat Retention</div>
            <div class="kpi-box-value">${cusStats.retention_rate_pct}%</div>
          </div>
        </div>
      </div>

      <div class="admin-grid">
        <div class="panel-card">
          <h3 class="font-editorial" style="font-size:var(--text-xl);margin-bottom:0.65rem;">4-Tier Refund Approval Queue</h3>
          ${
            state.adminRefunds.length === 0
              ? `<p style="font-size:var(--text-xs);color:var(--text-secondary);">No refunds in queue.</p>`
              : `<div style="display:flex;flex-direction:column;gap:0.55rem;">
                  ${state.adminRefunds
                    .map(
                      (r) => `
                      <div style="padding:0.7rem;border-radius:12px;background:var(--bg-subtle);font-size:12px;">
                        <div style="display:flex;justify-content:space-between;font-weight:600;">
                          <span>${r.refund_id} · Order ${r.order_id} (${formatInr(r.amount_inr)})</span>
                          <span class="meta-tag">Tier ${r.approval_tier} · ${r.status}</span>
                        </div>
                        <div style="font-size:11px;color:var(--text-secondary);margin:0.25rem 0 0.45rem;">
                          Approved by: ${r.approved_by || "—"} ${r.secondary_approved_by ? "· Secondary: " + r.secondary_approved_by : ""}
                        </div>
                        <div style="display:flex;gap:0.4rem;">
                          ${
                            r.status === "pending_approval" || r.status === "awaiting_secondary_approval"
                              ? `<button class="btn-pill" style="padding:0.3rem 0.75rem;font-size:11px;" data-action="admin-approve-refund" data-refund-id="${r.refund_id}">
                                  Approve (${state.actor.role})
                                </button>`
                              : ""
                          }
                          ${
                            r.status === "approved"
                              ? `<button class="btn-pill btn-pill-outline" style="padding:0.3rem 0.75rem;font-size:11px;" data-action="admin-process-refund" data-refund-id="${r.refund_id}">
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

        <div class="panel-card">
          <h3 class="font-editorial" style="font-size:var(--text-xl);margin-bottom:0.65rem;">Warehouse Garment Inventory</h3>
          <div style="display:flex;flex-direction:column;gap:0.5rem;">
            ${state.adminInventory
              .map(
                (inv) => `
                <div style="display:flex;justify-content:space-between;align-items:center;padding:0.6rem 0.75rem;border-radius:12px;background:var(--bg-subtle);font-size:12px;">
                  <div>
                    <strong>${inv.product_id}</strong> · ${inv.name}
                    <div style="font-size:11px;color:var(--text-secondary);">Available: ${inv.quantity_available} · Reserved: ${inv.quantity_reserved}</div>
                  </div>
                  <button
                    class="chip-pill"
                    data-action="admin-restock-sku"
                    data-product-id="${inv.product_id}"
                    data-current-stock="${inv.quantity_available}"
                  >
                    +10 Stock
                  </button>
                </div>
              `
              )
              .join("")}
          </div>
        </div>
      </div>

      <div class="panel-card">
        <h3 class="font-editorial" style="font-size:var(--text-xl);margin-bottom:0.65rem;">Immutable Audit Log (/api/audit/log)</h3>
        <div style="overflow-x:auto;">
          <table style="width:100%;border-collapse:collapse;font-size:11px;">
            <thead>
              <tr style="text-align:left;border-bottom:1px solid var(--border-strong);color:var(--text-secondary);">
                <th style="padding:0.45rem;">Trace ID</th>
                <th style="padding:0.45rem;">Actor</th>
                <th style="padding:0.45rem;">Resource</th>
                <th style="padding:0.45rem;">Action</th>
                <th style="padding:0.45rem;">Reason</th>
              </tr>
            </thead>
            <tbody>
              ${state.adminAuditLog
                .map(
                  (log) => `
                  <tr style="border-bottom:1px solid var(--border-subtle);">
                    <td style="padding:0.45rem;font-family:var(--font-mono);">${log.trace_id}</td>
                    <td style="padding:0.45rem;">${log.actor_type}:${log.actor_id}</td>
                    <td style="padding:0.45rem;">${log.resource_type}/${log.resource_id}</td>
                    <td style="padding:0.45rem;font-weight:600;">${log.action}</td>
                    <td style="padding:0.45rem;color:var(--text-secondary);">${log.reason || "—"}</td>
                  </tr>
                `
                )
                .join("")}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

export function renderApp() {
  const root = document.getElementById("noir-app");
  if (!root) return;

  root.className = `platform-shell ${state.viewMode === "desktop" ? "desktop-mode" : ""}`;

  const mainStage =
    state.activeSurface === "admin"
      ? renderAdminGovernanceSurface()
      : `<div class="showcase-grid">
          ${renderLeftStorefrontPhone()}
          ${renderRightDetailOrWorkspacePhone()}
        </div>`;

  root.innerHTML = `
    ${renderToolbar()}
    <main class="workspace-stage">
      ${renderGlobalBanners()}
      ${mainStage}
    </main>
  `;
}

document.addEventListener("click", async (e) => {
  const target = e.target.closest("[data-action]");
  if (!target) return;
  const action = target.getAttribute("data-action");

  if (action === "set-ui-principle") {
    const p = target.getAttribute("data-principle");
    state.activeUiPrinciple = p;
    if (p === "form_validation") state.rightPaneTab = "bag";
    renderApp();
    return;
  }

  if (action === "switch-surface") {
    state.activeSurface = target.getAttribute("data-surface");
    state.activeUiPrinciple = "normal";
    if (state.activeSurface === "admin") {
      await loadAdminDataFromDb();
    } else {
      renderApp();
    }
    return;
  }

  if (action === "toggle-view-mode") {
    state.viewMode = state.viewMode === "showcase" ? "desktop" : "showcase";
    renderApp();
    return;
  }

  if (action === "select-product") {
    if (e.target.closest('[data-action="toggle-wishlist"]')) return;
    const pid = target.getAttribute("data-product-id");
    state.rightPaneTab = "detail";
    await selectProductFromDb(pid);
    renderApp();
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

  if (action === "select-size") {
    state.selectedSize = target.getAttribute("data-size");
    renderApp();
    return;
  }

  if (action === "filter-department") {
    state.selectedDepartment = target.getAttribute("data-department");
    state.activeUiPrinciple = "normal";
    await refreshProductsFromDb();
    return;
  }

  if (action === "clear-filters" || action === "reset-view" || action === "retry-load") {
    state.searchQuery = "";
    state.selectedDepartment = "ALL";
    state.maxPrice = "";
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
    state.actor = ACTORS[2];
    api.setToken(state.actor.token);
    state.permissionDeniedInfo = null;
    state.activeUiPrinciple = "normal";
    if (state.activeSurface === "admin") await loadAdminDataFromDb();
    else await bootstrapData();
    return;
  }

  if (action === "dismiss-toast") {
    state.toastSuccess = null;
    if (state.activeUiPrinciple === "success") state.activeUiPrinciple = "normal";
    renderApp();
    return;
  }

  if (action === "open-right-tab") {
    state.rightPaneTab = target.getAttribute("data-tab");
    state.activeUiPrinciple = "normal";
    renderApp();
    return;
  }

  if (action === "focus-search") {
    document.getElementById("catalog-search-input")?.focus();
    return;
  }

  if (action === "add-to-cart") {
    const pid = target.getAttribute("data-product-id");
    try {
      state.cart = await api.addToCart({
        productId: pid,
        size: state.selectedSize || "M",
        quantity: 1,
      });
      state.toastSuccess = {
        title: "Added to Atelier Bag",
        message: `${pid} (Size ${state.selectedSize || "M"}) saved to database cart.`,
      };
      state.rightPaneTab = "bag";
      renderApp();
    } catch (err) {
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

  if (action === "clear-cart") {
    state.cart = await api.clearCart();
    state.couponResult = null;
    renderApp();
    return;
  }

  if (action === "apply-coupon") {
    const codeInput = document.getElementById("checkout-coupon");
    const code = (codeInput?.value || "ATELIER10").trim().toUpperCase();
    state.checkoutForm.couponCode = code;
    const subtotal = Number(state.cart?.subtotal_mrp_inr || 0);
    if (subtotal <= 0) return;
    const res = await api.validateCoupon(code, subtotal);
    state.couponResult = res;
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
      message: `Status updated to '${cancelled.status}' in database under policy POL-CAN-01.`,
    };
    renderApp();
    return;
  }

  if (action === "ask-agent-about-product") {
    const pid = target.getAttribute("data-product-id");
    state.rightPaneTab = "concierge";
    await sendAgentChatMessage(`Tell me the fabric, fit guide, and price details for ${pid}`);
    return;
  }

  if (action === "send-quick-prompt") {
    const prompt = target.getAttribute("data-prompt");
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
  } else if (action === "change-actor") {
    const tok = e.target.value;
    const found = ACTORS.find((a) => a.token === tok) || ACTORS[0];
    state.actor = found;
    api.setToken(found.token);
    state.permissionDeniedInfo = null;
    if (state.activeSurface === "admin") {
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

  if (formType === "catalog-search") {
    state.searchQuery = document.getElementById("catalog-search-input")?.value || "";
    state.maxPrice = document.getElementById("catalog-max-price")?.value || "";
    state.activeUiPrinciple = "normal";
    await refreshProductsFromDb();
    return;
  }

  if (formType === "checkout-form") {
    state.checkoutForm.street = document.getElementById("checkout-street")?.value || "";
    state.checkoutForm.pinCode = document.getElementById("checkout-pin")?.value || "";
    state.checkoutForm.couponCode = document.getElementById("checkout-coupon")?.value || "";

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
        paymentMethod: "upi",
      });
      state.cart = await api.getCart();
      state.orders = await api.listOrders();
      state.returnForm.orderId = order.order_id;
      state.couponResult = null;
      state.activeUiPrinciple = "normal";
      state.toastSuccess = {
        title: `Order ${order.order_id} Confirmed!`,
        message: `Total ${formatInr(order.grand_total_inr)} (incl. GST ${formatInr(order.total_gst_inr)}) · Invoice ${order.invoice_id}`,
      };
      state.rightPaneTab = "orders";
      await refreshProductsFromDb();
    } catch (err) {
      state.apiError = err;
      renderApp();
    }
    return;
  }

  if (formType === "return-form") {
    state.returnForm.orderId = (document.getElementById("return-order-id")?.value || "").trim().toUpperCase();
    state.returnForm.reasonNotes = document.getElementById("return-notes")?.value || "";
    state.returnForm.tagIntact = Boolean(document.getElementById("return-tag-intact")?.checked);

    const check = validateReturnForm(state.returnForm);
    state.returnValidationErrors = check.errors;
    if (!check.valid) {
      renderApp();
      return;
    }

    try {
      const res = await api.initiateReturn({
        orderId: state.returnForm.orderId,
        reasonCategory: "size_mismatch",
        customerNotes: state.returnForm.reasonNotes,
        tagIntact: state.returnForm.tagIntact,
        qcPassed: true,
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

  if (formType === "agent-chat-form") {
    const input = document.getElementById("agent-chat-input");
    const msg = (input?.value || "").trim();
    if (!msg) return;
    state.agentInput = "";
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
      tool_traces: res.tool_traces || [],
    });
    state.cart = await api.getCart().catch(() => state.cart);
    state.orders = await api.listOrders().catch(() => state.orders);
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
