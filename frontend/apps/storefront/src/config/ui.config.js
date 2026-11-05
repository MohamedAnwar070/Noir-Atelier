export const ROUTES = {
  shop: "/",
  orders: "/orders",
  policies: "/policies",
  admin: "/admin",
};

export const LIMITS = {
  searchDebounceMs: 350,
  toastDurationMs: 5500,
  maxLineQuantity: 10,
  lowStockThreshold: 5,
  chatMaxLength: 500,
  reviewMinLength: 10,
  catalogPageSize: 24,
};

export const ASSISTANT = {
  name: "Personal Fashion Consultant",
  tagline: "Private styling, natural fiber provenance, sizing & client care",
  inputPlaceholder: "Ask about fabrics, fit, styling advice, or specific garments…",
  welcome:
    "Welcome to Noir Atelier. As your Personal Fashion Consultant, I can guide you through our curated archive—advising on natural fiber provenance, silhouette and fit, styling pairings, or assisting with your bag, orders, and returns.",
  statusBadges: {
    action_completed: { label: "Completed", tone: "success" },
    pending_approval: { label: "Private review", tone: "warning" },
    escalated: { label: "Concierge notified", tone: "info" },
    clarify_missing_info: { label: "Detail needed", tone: "neutral" },
    blocked_unauthorized: { label: "Restricted", tone: "warning" },
    blocked_prompt_injection: { label: "Declined", tone: "warning" },
    error: { label: "Unable to complete", tone: "error" },
  },
};
