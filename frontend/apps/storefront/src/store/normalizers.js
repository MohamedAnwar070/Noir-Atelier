/**
 * API → view-model normalizers: the one place where backend wire formats are
 * translated for the UI. Views must read the normalized fields defined here,
 * never raw API keys, so a backend rename is fixed in one file.
 *
 * Money arrives as numbers or decimal strings ("2499.00"); everything here is
 * converted with toNumber() so views can format it directly.
 */

const toNumber = (value, fallback = 0) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
};

/* -------------------------------------------------------------------------- */
/* Tax                                                                         */
/* -------------------------------------------------------------------------- */

/**
 * Garment GST slab rule, mirrored from the backend's tax_service using the
 * `business_config.tax` block, so storefront labels match what checkout charges.
 * Rates arrive as fractions (0.05) and are exposed as percentages (5).
 */
export function buildTaxRules(taxConfig = {}) {
  const threshold = toNumber(taxConfig.garment_slab_threshold_inr, 2500);
  const lowRate = Math.round(toNumber(taxConfig.rate_upto_threshold, 0.05) * 100);
  const highRate = Math.round(toNumber(taxConfig.rate_above_threshold, 0.18) * 100);
  return {
    threshold,
    lowRate,
    highRate,
    hsnChapters: taxConfig.hsn_chapters || ["61", "62"],
    /** GST % applied to a garment at this unit sale price. */
    rateFor: (unitPrice) => (toNumber(unitPrice) <= threshold ? lowRate : highRate),
    /** Human description of the slab a rate belongs to. */
    describe: (rate) => (rate === lowRate ? `up to ₹${threshold.toLocaleString("en-IN")}` : `above ₹${threshold.toLocaleString("en-IN")}`),
  };
}

/** Sums GST per rate across lines: [{ rate, amount }], highest rate last. */
function gstByRate(lines, { rateKey, amountKey }) {
  const totals = new Map();
  for (const line of lines) {
    const rate = toNumber(line[rateKey]);
    totals.set(rate, (totals.get(rate) || 0) + toNumber(line[amountKey]));
  }
  return [...totals.entries()]
    .filter(([, amount]) => amount > 0)
    .sort(([a], [b]) => a - b)
    .map(([rate, amount]) => ({ rate, amount }));
}

/* -------------------------------------------------------------------------- */
/* Catalog                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * Products have one variant per size, each with its own SKU and price
 * (backend: product_variants). `price` is the "from" price (cheapest size) for
 * listing/sorting; anything that shows or charges a specific size must use
 * `priceFor(size)`. Stock is per size too: use `stockFor(size)` (live sellable
 * units of that size); `stock` is the total across sizes.
 */
export function normalizeProduct(p) {
  if (!p) return p;
  const fromPrice = toNumber(p.mrp_inr ?? p.price);
  const stock = toNumber(p.stock_quantity ?? p.stock);
  const variants = (p.variants || [])
    .filter((v) => v.is_active !== false)
    .map((v) => ({
      size: v.size,
      sku: v.sku,
      price: toNumber(v.mrp_inr),
      stock: toNumber(p.stock_by_size?.[v.size] ?? v.stock),
    }));
  const priceBySize = new Map(variants.map((v) => [v.size, v.price]));
  const stockBySize = new Map(variants.map((v) => [v.size, v.stock]));
  const prices = variants.map((v) => v.price);
  const priceRange = prices.length
    ? { min: Math.min(...prices), max: Math.max(...prices) }
    : { min: fromPrice, max: fromPrice };
  const sizes = variants.length
    ? variants.map((v) => v.size)
    : Array.isArray(p.sizes_available)
    ? p.sizes_available
    : [];
  const rating = toNumber(p.average_rating ?? p.rating, 5);
  const reviewCount = toNumber(p.review_count ?? p.reviews?.length, 0);
  const materials = Array.isArray(p.materials) ? p.materials : [];
  const compositionLabel = materials.length
    ? materials
        .map((m) => (m.percentage != null ? `${m.percentage}% ${m.name}` : m.name))
        .join(" · ")
    : p.accent_tag || "";
  const category = p.category || null;
  const accentTag = p.accent_tag || compositionLabel || category?.name || "";

  return {
    ...p,
    price: fromPrice,
    mrp_inr: fromPrice,
    variants,
    priceRange,
    /** True when sizes are priced differently. */
    hasSizePricing: priceRange.max > priceRange.min,
    /** Price of one size; falls back to the "from" price for unknown sizes. */
    priceFor: (size) => priceBySize.get(size) ?? fromPrice,
    stock,
    stock_quantity: stock,
    /** Sellable units of one size (0 for unknown sizes — never assume stock). */
    stockFor: (size) => stockBySize.get(size) ?? 0,
    sizes,
    sizes_available: sizes,
    average_rating: rating,
    rating,
    review_count: reviewCount,
    category,
    categoryName: category?.name || null,
    categorySlug: category?.slug || null,
    color: p.color || null,
    colorFamily: p.color_family || null,
    colorHex: p.color_hex || null,
    materials,
    compositionLabel,
    accent_tag: accentTag,
  };
}

/* -------------------------------------------------------------------------- */
/* Cart                                                                        */
/* -------------------------------------------------------------------------- */

/**
 * Cart API → view model. The API returns totals at the top level and lines as
 * { cart_id, product_id, product_name, unit_mrp_inr, line_mrp_inr, gst_rate_pct,
 * included_gst_inr }. The applied coupon is not echoed back, so the code we
 * priced the cart with is attached here.
 */
export function normalizeCart(raw, couponCode = null) {
  if (!raw) return null;
  const items = (raw.items || []).map((line) => {
    const price = toNumber(line.unit_mrp_inr ?? line.price);
    const quantity = toNumber(line.quantity);
    return {
      ...line,
      name: line.product_name || line.name || line.product_id,
      price,
      quantity,
      lineTotal: toNumber(line.line_mrp_inr, price * quantity),
    };
  });
  const discount = toNumber(raw.discount_inr);
  return {
    ...raw,
    items,
    gstLines: gstByRate(raw.items || [], { rateKey: "gst_rate_pct", amountKey: "included_gst_inr" }),
    coupon: couponCode ? { code: couponCode, discount, description: discount > 0 ? "Discount applied" : "Applied" } : null,
  };
}

/** Payment method API → view model ({ method_id, name } → { id, label }). */
export function normalizePaymentMethod(m) {
  return {
    ...m,
    id: m.method_id ?? m.id,
    label: m.name ?? m.label ?? m.method_id,
    minOrder: toNumber(m.min_order_inr),
    maxOrder: m.max_order_inr != null ? toNumber(m.max_order_inr) : Infinity,
  };
}

/* -------------------------------------------------------------------------- */
/* Orders                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * Order API → view model. Status labels, tones, and cancellation/return
 * eligibility are resolved directly from the database (`order_statuses` table)
 * via server serialization (`status_label`, `status_tone`, `can_cancel`, `can_return`)
 * or `orderStatusMap` from `GET /api/catalog/meta`.
 */
export function normalizeOrder(raw, orderStatusMap = {}) {
  if (!raw) return raw;
  const status = String(raw.status || "pending").toLowerCase();
  const statusMeta = orderStatusMap[status] || null;
  const items = (raw.items || []).map((line) => {
    const quantity = toNumber(line.quantity, 1);
    const unitPrice = toNumber(line.unit_sale_value_inr ?? line.unit_mrp_inr);
    return {
      ...line,
      name: line.product_name || line.product_id,
      quantity,
      unitPrice,
      lineTotal: unitPrice * quantity,
      gstRate: toNumber(line.gst_rate_pct),
    };
  });
  const placedAt = raw.order_date ? new Date(raw.order_date) : null;

  return {
    ...raw,
    status,
    statusLabel: raw.status_label || statusMeta?.label || status.replace(/_/g, " "),
    statusTone: raw.status_tone || statusMeta?.ui_tone || "neutral",
    placedAt: placedAt && !Number.isNaN(placedAt.getTime()) ? placedAt : null,
    items,
    subtotal: toNumber(raw.subtotal_mrp_inr),
    discount: toNumber(raw.discount_inr),
    shipping: toNumber(raw.shipping_fee_inr),
    gstTotal: toNumber(raw.total_gst_inr),
    grandTotal: toNumber(raw.grand_total_inr),
    paymentStatus: raw.payment_status || null,
    canCancel: Boolean(raw.can_cancel ?? statusMeta?.is_cancellable),
    canReturn: Boolean(raw.can_return ?? statusMeta?.is_returnable),
  };
}
