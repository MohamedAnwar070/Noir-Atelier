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

export function validateCheckoutForm(fields = {}) {
  const errors = {};
  const pin = String(fields.pinCode || "").trim();
  const street = String(fields.street || "").trim();
  const coupon = String(fields.couponCode || "").trim().toUpperCase();

  if (!street || street.length < 6) {
    errors.street = "Enter a valid delivery street address (minimum 6 characters).";
  }
  if (!/^[1-9][0-9]{5}$/.test(pin)) {
    errors.pinCode = "Enter a valid 6-digit Indian PIN code.";
  }
  if (coupon && !/^[A-Z0-9]{4,16}$/.test(coupon)) {
    errors.couponCode = "Coupon code must be 4–16 alphanumeric characters.";
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors,
  };
}

export function validateReturnForm(fields = {}) {
  const errors = {};
  const orderId = String(fields.orderId || "").trim().toUpperCase();
  const reason = String(fields.reasonNotes || "").trim();

  if (!/^ORD-\d{4}$/.test(orderId)) {
    errors.orderId = "Order ID must match format ORD-####.";
  }
  if (!reason || reason.length < 5) {
    errors.reasonNotes = "Please provide a return reason (minimum 5 characters).";
  }
  if (fields.tagIntact === false) {
    errors.tagIntact = "Atelier security ribbon must be intact per database policy POL-RET-01.";
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors,
  };
}
