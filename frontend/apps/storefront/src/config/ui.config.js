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
  chatMaxLength: 400,
  reviewMinLength: 10,
};

export const ASSISTANT = {
  name: "Atelier Stylist",
  tagline: "Ask about fabrics, sizes, orders or returns",
  inputPlaceholder: "Ask about a piece, your order or a return…",
  welcome:
    "Hello! I'm your Atelier Stylist. I can help you find the right piece, add it to your bag, place an order, or sort out a return.",
  statusBadges: {
    action_completed: { label: "Done", tone: "success" },
    pending_approval: { label: "Awaiting approval", tone: "warning" },
    escalated: { label: "Team notified", tone: "info" },
    clarify_missing_info: { label: "Need a detail", tone: "neutral" },
    blocked_unauthorized: { label: "Not allowed", tone: "warning" },
    blocked_prompt_injection: { label: "Blocked", tone: "warning" },
    error: { label: "Couldn't finish", tone: "error" },
  },
};
