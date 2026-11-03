export const UI_PRINCIPLE_STATES = [
  { id: "normal", number: 0, label: "Live Normal Mode" },
  { id: "empty", number: 1, label: "1. Empty State" },
  { id: "loading", number: 2, label: "2. Loading State" },
  { id: "error", number: 3, label: "3. Error State" },
  { id: "offline", number: 4, label: "4. No Internet" },
  { id: "slow_network", number: 5, label: "5. Slow Network" },
  { id: "no_results", number: 6, label: "6. No Search Result" },
  { id: "permission_denied", number: 7, label: "7. Permission Denied" },
  { id: "session_expired", number: 8, label: "8. Session Expired" },
  { id: "form_validation", number: 9, label: "9. Form Validation" },
  { id: "success", number: 10, label: "10. Success State" },
  { id: "pending_approval", number: 11, label: "11. Tier 2/3 Approval" },
];

export function renderEmptyState({
  title = "Your Atelier Bag is Empty",
  description = "Explore our tailored Men, Women, and Kids garments crafted in Belgian linen, mulberry silk, and superfine merino wool.",
  actionLabel = "Explore The New Edit",
  actionAttr = 'data-action="reset-view"',
} = {}) {
  return `
    <div class="state-card" data-ui-state="empty">
      <div style="width:48px;height:48px;border-radius:50%;background:var(--bg-subtle);display:inline-flex;align-items:center;justify-content:center;margin-bottom:0.75rem;font-size:1.25rem;">🛍️</div>
      <h3 class="font-editorial" style="font-size:var(--text-xl);margin-bottom:0.4rem;">${title}</h3>
      <p style="font-size:var(--text-xs);color:var(--text-secondary);max-width:280px;margin:0 auto 1.1rem;">${description}</p>
      <button class="btn-pill" ${actionAttr}>${actionLabel}</button>
    </div>
  `;
}

export function renderLoadingState({ count = 4, label = "Curating Noir Atelier garments..." } = {}) {
  const cards = Array.from({ length: count })
    .map(
      () => `
      <div style="background:var(--bg-surface);border-radius:20px;padding:0.65rem;border:1px solid var(--border-subtle);">
        <div class="shimmer" style="height:152px;border-radius:16px;margin-bottom:0.65rem;"></div>
        <div class="shimmer" style="height:13px;width:78%;border-radius:6px;margin-bottom:0.4rem;"></div>
        <div class="shimmer" style="height:11px;width:45%;border-radius:6px;"></div>
      </div>
    `
    )
    .join("");

  return `
    <div data-ui-state="loading">
      <div class="state-banner info">
        <span>⏳ ${label}</span>
        <span style="font-family:var(--font-mono);font-size:10px;">FETCHING /api/*</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:0.75rem;">
        ${cards}
      </div>
    </div>
  `;
}

export function renderErrorState({
  code = "api_request_failed",
  message = "We could not complete your request against the Noir Atelier API.",
  traceId = "TRC-409102",
  retryAttr = 'data-action="retry-load"',
} = {}) {
  return `
    <div class="state-card" data-ui-state="error" style="border-color:var(--state-error-border);background:#fffcfc;">
      <div style="width:44px;height:44px;border-radius:50%;background:var(--state-error-bg);color:var(--state-error-text);display:inline-flex;align-items:center;justify-content:center;margin-bottom:0.65rem;font-weight:700;">!</div>
      <h3 class="font-editorial" style="font-size:var(--text-xl);color:var(--state-error-text);margin-bottom:0.35rem;">Something Went Wrong</h3>
      <p style="font-size:var(--text-xs);color:var(--text-secondary);margin-bottom:0.65rem;">${message}</p>
      <div style="font-family:var(--font-mono);font-size:11px;color:var(--text-muted);margin-bottom:1rem;">
        Code: <strong>${code}</strong> · Trace: <strong>${traceId}</strong>
      </div>
      <button class="btn-pill" ${retryAttr}>Retry Request</button>
    </div>
  `;
}

export function renderNoInternetBanner({ retryAttr = 'data-action="reconnect-network"' } = {}) {
  return `
    <div class="state-banner error" data-ui-state="offline" role="alert">
      <div>
        <strong>📡 No Internet Connection</strong>
        <div style="font-size:11px;opacity:0.9;">You are currently offline. Browsing cached catalog; checkout & agent actions are queued safely.</div>
      </div>
      <button class="btn-pill btn-pill-outline" style="padding:0.35rem 0.85rem;font-size:11px;" ${retryAttr}>Reconnect</button>
    </div>
  `;
}

export function renderSlowNetworkBanner({ latencyMs = 1840 } = {}) {
  return `
    <div class="state-banner warning" data-ui-state="slow_network" role="status">
      <div>
        <strong>🐢 Slow Network Detected (${latencyMs}ms)</strong>
        <div style="font-size:11px;opacity:0.92;">Switched to lightweight garment previews and idempotent request keys to prevent duplicate charges.</div>
      </div>
      <span style="font-family:var(--font-mono);font-size:10px;">LITE MODE</span>
    </div>
  `;
}

export function renderNoSearchResultState({
  query = "",
  department = "ALL",
  maxPrice = null,
  resetAttr = 'data-action="clear-filters"',
} = {}) {
  const filterDesc = [
    query ? `"${query}"` : null,
    department && department !== "ALL" ? `Dept: ${department}` : null,
    maxPrice ? `Max: ₹${maxPrice}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return `
    <div class="state-card" data-ui-state="no_results">
      <div style="width:46px;height:46px;border-radius:50%;background:var(--bg-subtle);display:inline-flex;align-items:center;justify-content:center;margin-bottom:0.65rem;">🔍</div>
      <h3 class="font-editorial" style="font-size:var(--text-xl);margin-bottom:0.35rem;">No Matching Garments</h3>
      <p style="font-size:var(--text-xs);color:var(--text-secondary);margin-bottom:0.9rem;">
        No garments matched ${filterDesc || "your active filters"}. Try broadening your price ceiling or exploring Men, Women, or Kids collections.
      </p>
      <div style="display:flex;gap:0.5rem;justify-content:center;flex-wrap:wrap;">
        <button class="btn-pill" ${resetAttr}>Reset All Filters</button>
      </div>
    </div>
  `;
}

export function renderPermissionDeniedState({
  actorId = "CUS-001 (customer)",
  requiredRole = "Store Manager (role: manager) or Finance Admin (role: finance_admin)",
  endpoint = "POST /api/refunds/RFD-1002/approve",
  switchAttr = 'data-action="switch-to-manager"',
} = {}) {
  return `
    <div class="state-card" data-ui-state="permission_denied" style="border-color:var(--state-warning-border);">
      <div style="width:46px;height:46px;border-radius:50%;background:var(--state-warning-bg);color:var(--state-warning-text);display:inline-flex;align-items:center;justify-content:center;margin-bottom:0.65rem;font-size:1.1rem;">🔒</div>
      <h3 class="font-editorial" style="font-size:var(--text-xl);margin-bottom:0.35rem;">Permission Denied (HTTP 403)</h3>
      <p style="font-size:var(--text-xs);color:var(--text-secondary);margin-bottom:0.75rem;">
        Actor <strong>${actorId}</strong> is not authorized to execute <code style="font-family:var(--font-mono);">${endpoint}</code>.
      </p>
      <div style="background:var(--bg-subtle);border-radius:12px;padding:0.6rem;font-size:11px;color:var(--text-secondary);margin-bottom:1rem;">
        Required Privilege: <strong>${requiredRole}</strong>
      </div>
      <button class="btn-pill" ${switchAttr}>Switch to Store Manager Token</button>
    </div>
  `;
}

export function renderSessionExpiredState({
  renewAttr = 'data-action="renew-session"',
} = {}) {
  return `
    <div class="state-card" data-ui-state="session_expired" style="border-color:var(--state-info-border);">
      <div style="width:46px;height:46px;border-radius:50%;background:var(--state-info-bg);color:var(--state-info-text);display:inline-flex;align-items:center;justify-content:center;margin-bottom:0.65rem;font-size:1.1rem;">🔑</div>
      <h3 class="font-editorial" style="font-size:var(--text-xl);margin-bottom:0.35rem;">Session Expired (HTTP 401)</h3>
      <p style="font-size:var(--text-xs);color:var(--text-secondary);margin-bottom:1rem;">
        Your JWT access token has expired for security. Your shopping bag and session state are preserved—re-authenticate to continue.
      </p>
      <button class="btn-pill" ${renewAttr}>Re-Authenticate Session (CUS-001)</button>
    </div>
  `;
}

export function renderSuccessBanner({
  title = "Order Confirmed",
  message = "Order ORD-1001 confirmed with GST Tax Invoice INV-1001.",
  dismissAttr = 'data-action="dismiss-toast"',
} = {}) {
  return `
    <div class="state-banner success" data-ui-state="success" role="status">
      <div>
        <strong>✓ ${title}</strong>
        <div style="font-size:11px;">${message}</div>
      </div>
      <button class="chip-pill" style="padding:0.2rem 0.6rem;" ${dismissAttr}>Dismiss</button>
    </div>
  `;
}

export function renderPendingApprovalState({
  returnId = "RET-1002",
  refundId = "RFD-1002",
  orderId = "ORD-1002",
  amountInr = 7999,
  tier = 2,
  ticketId = "TKT-1001",
  status = "pending_approval",
} = {}) {
  const isTier3 = Number(tier) >= 3;
  return `
    <div class="state-card" data-ui-state="pending_approval" style="text-align:left;border-color:var(--state-warning-border);">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
        <span class="chip-pill active" style="font-size:10px;">TIER ${tier} REFUND GOVERNANCE</span>
        <span style="font-family:var(--font-mono);font-size:11px;color:var(--text-secondary);">${returnId} · ${refundId}</span>
      </div>
      <h3 class="font-editorial" style="font-size:var(--text-lg);margin-bottom:0.3rem;">
        ${isTier3 ? "Dual Manager + Finance Approval Required" : "Store Manager Approval Required"}
      </h3>
      <p style="font-size:var(--text-xs);color:var(--text-secondary);margin-bottom:0.75rem;">
        Order <strong>${orderId}</strong> (₹${Number(amountInr).toLocaleString("en-IN")}) passed physical security ribbon & warehouse QC check (POL-RET-01). Escalated via ticket <strong>${ticketId || "TKT-1001"}</strong>.
      </p>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:0.4rem;font-size:10px;text-align:center;">
        <div style="padding:0.45rem;border-radius:10px;background:var(--state-success-bg);color:var(--state-success-text);font-weight:600;">1. QC & Ribbon ✓</div>
        <div style="padding:0.45rem;border-radius:10px;background:${status === "approved" || status === "awaiting_secondary_approval" ? "var(--state-success-bg)" : "var(--state-warning-bg)"};color:${status === "approved" || status === "awaiting_secondary_approval" ? "var(--state-success-text)" : "var(--state-warning-text)"};font-weight:600;">2. Store Manager</div>
        <div style="padding:0.45rem;border-radius:10px;background:${status === "approved" ? "var(--state-success-bg)" : "var(--bg-subtle)"};color:${status === "approved" ? "var(--state-success-text)" : "var(--text-secondary)"};font-weight:600;">${isTier3 ? "3. Finance Dual" : "3. Auto Payout"}</div>
      </div>
    </div>
  `;
}
