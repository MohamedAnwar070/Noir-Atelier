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
  validation_error: "Please review the details and try again.",
};

export function friendlyErrorMessage(err, fallback = "Something went wrong. Please try again.") {
  if (!err) return fallback;
  if (FRIENDLY_BY_CODE[err.code] && err.code !== "insufficient_stock") return FRIENDLY_BY_CODE[err.code];
  if (err.code === "insufficient_stock") {
    const shortages = err.details?.shortages;
    if (Array.isArray(shortages) && shortages.length) {
      return shortages
        .map((s) => `${s.name}: only ${s.available} left (you asked for ${s.requested})`)
        .join(" · ");
    }
    return FRIENDLY_BY_CODE.insufficient_stock;
  }
  if (err.status >= 500) return fallback;
  return err.message || fallback;
}
