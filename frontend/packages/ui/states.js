import { renderIcon } from "./theme.js";

export const STATE_KINDS = [
  "empty",
  "loading",
  "error",
  "offline",
  "slow_network",
  "no_results",
  "permission_denied",
  "session_expired",
  "form_validation",
  "success",
  "pending_approval",
];

export const STATE_CATALOG = {
  empty: {
    icon: "bag",
    tone: "neutral",
    title: "Nothing here yet",
    description: "When there is something to show, it will appear here.",
    actionLabel: "Browse the collection",
  },
  loading: {
    icon: "refresh",
    tone: "neutral",
    title: "Loading",
    description: "Getting the latest from the atelier…",
  },
  error: {
    icon: "alert",
    tone: "error",
    title: "Something went wrong",
    description: "We couldn't complete that request. Please try again in a moment.",
    actionLabel: "Try again",
  },
  offline: {
    icon: "wifi-off",
    tone: "warning",
    title: "You're offline",
    description: "Check your internet connection. We'll reconnect automatically as soon as you're back online.",
    actionLabel: "Retry now",
  },
  slow_network: {
    icon: "clock",
    tone: "info",
    title: "Slow connection",
    description: "This is taking longer than usual. Hang tight — we're still loading.",
  },
  no_results: {
    icon: "search",
    tone: "neutral",
    title: "No matching pieces",
    description: "Try a different search, or clear your filters to see the full collection.",
    actionLabel: "Clear all filters",
  },
  permission_denied: {
    icon: "lock",
    tone: "warning",
    title: "You don't have access",
    description: "This area is available to authorised team members only.",
    actionLabel: "Back to shop",
  },
  session_expired: {
    icon: "key",
    tone: "warning",
    title: "Your session has expired",
    description: "For your security we signed you out. Sign in again to continue where you left off.",
    actionLabel: "Sign in again",
  },
  form_validation: {
    icon: "alert",
    tone: "error",
    title: "Please check the highlighted fields",
    description: "Some details need your attention before we can continue.",
  },
  success: {
    icon: "check",
    tone: "success",
    title: "All done",
    description: "Your request was completed successfully.",
  },
  pending_approval: {
    icon: "shield",
    tone: "info",
    title: "Waiting for approval",
    description: "A member of our team is reviewing this. We'll update you as soon as it's approved.",
  },
};

export const UI_PRINCIPLE_STATES = STATE_CATALOG;

export function getStateCopy(kind, overrides = {}) {
  return { ...(STATE_CATALOG[kind] || STATE_CATALOG.error), ...overrides };
}

export function classifyApiError(err) {
  const status = Number(err?.status ?? 0);
  const code = String(err?.code || "");
  if (code === "offline") return "offline";
  if (status === 0) return "error";
  if (status === 401) return "session_expired";
  if (status === 403) return "permission_denied";
  return "error";
}

const FRIENDLY_BY_CODE = {
  backend_unreachable: "We couldn't reach our servers. Please check your connection and try again.",
  insufficient_stock: "Some items are no longer available in the quantity you selected.",
  empty_cart: "Your bag is empty. Add a piece to continue.",
  order_not_found: "We couldn't find that order.",
  cancel_not_eligible: "This order has already been dispatched, so it can no longer be cancelled.",
  not_cancellable: "This order can no longer be cancelled.",
  forbidden_order_access: "You don't have access to this order.",
  invalid_return_reason: "Please select a valid return reason from the list.",
  validation_error: "Please review the details and try again.",
};

export function friendlyErrorMessage(err, fallback = "Something went wrong. Please try again.") {
  if (!err) return fallback;
  if (FRIENDLY_BY_CODE[err.code] && err.code !== "insufficient_stock") return FRIENDLY_BY_CODE[err.code];
  if (err.code === "insufficient_stock") {
    const shortages = err.details?.shortages;
    if (Array.isArray(shortages) && shortages.length) {
      return shortages
        .map((s) => `${s.name}${s.size ? ` (size ${s.size})` : ""}: only ${s.available} left (you asked for ${s.requested})`)
        .join(" · ");
    }
    return FRIENDLY_BY_CODE.insufficient_stock;
  }
  if (err.status >= 500) return fallback;
  return err.message || fallback;
}

/* -------------------------------------------------------------------------- */
/* HTML State Helpers (used by /storefront/app.js ES module shell)            */
/* -------------------------------------------------------------------------- */

function renderStateBox({ icon, title, description, actionLabel, actionAttr = "", meta = "" }) {
  return `
    <div class="surface-card" role="status" style="padding:2rem 1.5rem;text-align:center;">
      <div style="margin-bottom:0.65rem;">${renderIcon(icon || "sparkles", "lg")}</div>
      <h3 class="font-editorial" style="font-size:var(--text-xl);margin-bottom:0.35rem;">${title}</h3>
      <p style="font-size:var(--text-xs);color:var(--text-secondary);max-width:480px;margin:0 auto 1rem;">${description}</p>
      ${meta ? `<div style="font-family:var(--font-mono);font-size:11px;color:var(--text-muted);margin-bottom:0.85rem;">${meta}</div>` : ""}
      ${actionLabel ? `<button type="button" class="btn-pill" ${actionAttr}><span>${actionLabel}</span></button>` : ""}
    </div>
  `;
}

export function renderEmptyState({ title, description, actionLabel, actionAttr = 'data-action="clear-filters"' } = {}) {
  const copy = getStateCopy("empty", { title, description, actionLabel });
  return renderStateBox({ ...copy, actionAttr });
}

export function renderLoadingState({ count = 4, label = "Loading garments..." } = {}) {
  const cards = Array.from({ length: count })
    .map(() => `<div class="shimmer" style="height:280px;border-radius:18px;"></div>`)
    .join("");
  return `
    <div aria-busy="true" aria-live="polite">
      <p style="font-size:var(--text-xs);color:var(--text-secondary);margin-bottom:0.85rem;">${label}</p>
      <div class="catalog-grid">${cards}</div>
    </div>
  `;
}

export function renderErrorState({ code = "http_error", message, traceId = "" } = {}) {
  const copy = getStateCopy("error", { description: message || STATE_CATALOG.error.description });
  return renderStateBox({
    ...copy,
    meta: `${code}${traceId ? ` · ${traceId}` : ""}`,
    actionAttr: 'data-action="retry-load"',
  });
}

export function renderNoSearchResultState({ query = "", department = "ALL", maxPrice = "" } = {}) {
  const parts = [];
  if (query) parts.push(`"${query}"`);
  if (department && department !== "ALL") parts.push(department);
  if (maxPrice) parts.push(`≤ ₹${maxPrice}`);
  const summary = parts.length ? `No pieces matched ${parts.join(" · ")}. ` : "";
  return renderStateBox({
    ...getStateCopy("no_results", {
      description: `${summary}Try broadening your search or clearing active filters.`,
    }),
    actionAttr: 'data-action="clear-filters"',
  });
}

export function renderPermissionDeniedState({ actorId = "", requiredRole = "Manager or Finance Admin", endpoint = "" } = {}) {
  return renderStateBox({
    ...getStateCopy("permission_denied", {
      description: `Actor ${actorId} does not have permission${endpoint ? ` for ${endpoint}` : ""}. Required: ${requiredRole}.`,
      actionLabel: "Switch to Store Manager",
    }),
    actionAttr: 'data-action="switch-to-manager"',
  });
}

export function renderSessionExpiredState() {
  return renderStateBox({
    ...getStateCopy("session_expired"),
    actionAttr: 'data-action="renew-session"',
  });
}

export function renderPendingApprovalState({ returnId = "RET-PENDING", refundId = "RFD-PENDING", tier = 2, status = "pending_approval" } = {}) {
  return renderStateBox({
    ...getStateCopy("pending_approval", {
      title: `Tier ${tier} Refund Review (${status})`,
      description: `Return ${returnId} · Refund ${refundId} has been routed for administrative approval.`,
      actionLabel: "",
    }),
  });
}

export function renderNoInternetBanner() {
  return `
    <div class="surface-card" role="alert" style="display:flex;justify-content:space-between;align-items:center;gap:0.75rem;padding:0.75rem 1rem;">
      <div style="display:flex;align-items:center;gap:0.5rem;font-size:var(--text-xs);">
        ${renderIcon("wifi-off", "sm")}
        <span><strong>Offline:</strong> ${STATE_CATALOG.offline.description}</span>
      </div>
      <button type="button" class="chip-pill" data-action="reconnect-network">Retry</button>
    </div>
  `;
}

export function renderSlowNetworkBanner({ latencyMs = 1500 } = {}) {
  return `
    <div class="surface-card" role="status" style="display:flex;align-items:center;gap:0.5rem;padding:0.65rem 1rem;font-size:var(--text-xs);">
      ${renderIcon("clock", "sm")}
      <span>Slow connection (${latencyMs}ms) — syncing live catalogue data…</span>
    </div>
  `;
}

export function renderSuccessBanner({ title = "Confirmed", message = "" } = {}) {
  return `
    <div class="surface-card" role="status" style="display:flex;justify-content:space-between;align-items:center;gap:0.75rem;padding:0.75rem 1rem;">
      <div style="display:flex;align-items:center;gap:0.5rem;font-size:var(--text-xs);">
        ${renderIcon("check", "sm")}
        <span><strong>${title}:</strong> ${message}</span>
      </div>
      <button type="button" class="chip-pill" data-action="dismiss-toast">Dismiss</button>
    </div>
  `;
}
