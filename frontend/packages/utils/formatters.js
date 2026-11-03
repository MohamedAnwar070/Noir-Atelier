export function formatInr(amount, currencySymbol = "₹") {
  const num = Number(amount || 0);
  return `${currencySymbol}${num.toLocaleString("en-IN", {
    minimumFractionDigits: num % 1 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  })}`;
}

export function computeGstSlabFromConfig(mrpInr, taxConfig = {}) {
  const mrp = Number(mrpInr || 0);
  const threshold = Number(taxConfig.garment_slab_threshold_inr ?? 0);
  const lowRate = Number(taxConfig.rate_upto_threshold ?? 0) * 100;
  const highRate = Number(taxConfig.rate_above_threshold ?? 0) * 100;
  const ratePct = mrp <= threshold ? lowRate : highRate;
  const taxable = ratePct > 0 ? mrp / (1 + ratePct / 100) : mrp;
  const gstAmount = mrp - taxable;
  return {
    ratePct,
    taxableInr: Number(taxable.toFixed(2)),
    gstAmountInr: Number(gstAmount.toFixed(2)),
    label: `${ratePct}% GST Included`,
  };
}

export function validateAddressForm(fields = {}) {
  const errors = {};
  const street = String(fields.street || "").trim();
  const city = String(fields.city || "").trim();
  const pin = String(fields.pinCode || "").trim();

  if (street.length < 6) errors.street = "Enter your full street address (at least 6 characters).";
  if (city.length < 2) errors.city = "Enter your city.";
  if (!/^[1-9][0-9]{5}$/.test(pin)) errors.pinCode = "Enter a valid 6-digit PIN code.";

  return { valid: Object.keys(errors).length === 0, errors };
}

export function validateCheckoutForm(fields = {}) {
  const errors = {};
  if (!fields.addressId) errors.addressId = "Choose where we should deliver your order.";
  if (!fields.paymentMethod) errors.paymentMethod = "Choose a payment method.";
  return { valid: Object.keys(errors).length === 0, errors };
}

export function validateCouponCode(code) {
  const value = String(code || "").trim().toUpperCase();
  if (!value) return "Enter a promo code.";
  if (!/^[A-Z0-9]{4,16}$/.test(value)) return "Promo codes are 4–16 letters or numbers.";
  return "";
}

export function validateReviewForm(fields = {}) {
  const errors = {};
  if (!fields.rating || fields.rating < 1) errors.rating = "Select a star rating.";
  if (String(fields.comment || "").trim().length < 10) {
    errors.comment = "Tell us a little more (at least 10 characters).";
  }
  return { valid: Object.keys(errors).length === 0, errors };
}

export function validateReturnForm(fields = {}) {
  const errors = {};
  const reason = String(fields.reasonNotes || "").trim();

  if (!fields.orderId) errors.orderId = "Select the order you'd like to return.";
  if (reason.length < 5) errors.reasonNotes = "Please tell us why you're returning this (at least 5 characters).";
  if (fields.tagIntact === false) {
    errors.tagIntact = "Returns need the security ribbon to be intact. Please contact concierge for damaged items.";
  }

  return { valid: Object.keys(errors).length === 0, errors };
}

export function validatePolicyConfigForm(fields = {}) {
  const errors = {};
  const threshold = Number(fields.freeShippingThresholdInr);
  const fee = Number(fields.standardShippingFeeInr);
  const reason = String(fields.reason || "").trim();

  if (!Number.isFinite(threshold) || threshold < 0 || threshold > 50000) {
    errors.freeShippingThresholdInr = "Free shipping threshold must be between ₹0 and ₹50,000.";
  }
  if (!Number.isFinite(fee) || fee < 0 || fee > 2500) {
    errors.standardShippingFeeInr = "Standard shipping fee must be between ₹0 and ₹2,500.";
  }
  if (!reason || reason.length < 5) {
    errors.reason = "Provide an audit governance reason (minimum 5 characters).";
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors,
  };
}

export function getProductImage(product = {}) {
  return {
    url: product.image_gallery?.[0]?.url || product.images?.[0] || "",
    alt: product.image_gallery?.[0]?.alt_text || product.name || "Noir Atelier garment",
  };
}

