export const ROUTES = {
  shop: "/",
  orders: "/orders",
  policies: "/policies",
  admin: "/admin",
};

export const STAFF_ROLES = ["manager", "finance_admin", "super_admin"];

export const LIMITS = {
  searchDebounceMs: 350,
  toastDurationMs: 5500,
  maxLineQuantity: 10,
  lowStockThreshold: 5,
  chatMaxLength: 400,
  reviewMinLength: 10,
};

export const ORDER_STATUS = {
  pending: { label: "Awaiting payment", tone: "warning" },
  paid: { label: "Paid", tone: "success" },
  confirmed: { label: "Confirmed", tone: "success" },
  shipped: { label: "On its way", tone: "info" },
  delivered: { label: "Delivered", tone: "success" },
  picked_up: { label: "Picked up", tone: "success" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  expired: { label: "Reservation expired", tone: "neutral" },
  needs_review: { label: "Under review", tone: "warning" },
  returned: { label: "Returned", tone: "neutral" },
  refunded: { label: "Refunded", tone: "neutral" },
};

export const CANCELLABLE_STATUSES = ["pending", "paid", "confirmed"];
export const RETURNABLE_STATUSES = ["paid", "confirmed", "shipped", "delivered", "picked_up"];

export const RETURN_REASONS = [
  { id: "size_mismatch", label: "Size or fit isn't right", defective: false },
  { id: "defective_garment", label: "Damaged or defective", defective: true },
  { id: "not_as_described", label: "Not what I expected", defective: false },
];

export const ASSISTANT = {
  name: "Atelier Stylist",
  tagline: "Ask about fabrics, sizes, orders or returns",
  inputPlaceholder: "Ask about a piece, your order or a return…",
  welcome:
    "Hello! I'm your Atelier Stylist. I can help you find the right piece, add it to your bag, place an order, or sort out a return.",
  personas: {
    catalog_agent: "Personal Stylist",
    cart_agent: "Bag Concierge",
    order_agent: "Order Concierge",
    fulfillment_agent: "Delivery Concierge",
    returns_agent: "Returns Specialist",
    support_agent: "Client Care",
    inventory_agent: "Stock Specialist",
    analytics_agent: "Store Insights",
    config_agent: "Policy Guide",
  },
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
