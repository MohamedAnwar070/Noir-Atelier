"use client";

import React, { useState } from "react";
import { useStore } from "@/store/StoreProvider";
import { Drawer, Modal } from "@/components/ui/Overlay";
import { Icon } from "@/components/ui/Icon";
import { QuantityStepper, Button, TextField } from "@/components/ui/Controls";
import { StatePanel } from "@/components/ui/StatePanel";
import {
  formatInr,
  getProductImage,
  validateAddressForm,
  validateCouponCode,
} from "@noir/utils/formatters.js";

/** Used only if the config endpoint returned no methods. IDs match the backend's PaymentMethod.method_id. */
const FALLBACK_PAYMENT_METHODS = [
  { id: "upi", label: "UPI (Instant)", minOrder: 0 },
  { id: "card", label: "Credit / Debit Card", minOrder: 0 },
];

export function ShoppingBagDrawer({ isOpen, onClose }) {
  const {
    cart,
    cartTotals,
    updateQuantity,
    removeFromBag,
    appliedCoupon,
    applyCoupon,
    removeCoupon,
    customerAddresses,
    addCustomerAddress,
    paymentMethods,
    placeOrder,
    freeShippingMin,
    taxRules,
    notify,
    navigateTo,
  } = useStore();

  const [couponInput, setCouponInput] = useState("");
  const [couponError, setCouponError] = useState("");
  const [isApplyingCoupon, setIsApplyingCoupon] = useState(false);

  // Explicit user choices; until one is made, fall back to the first loaded option
  // (addresses/methods load asynchronously, so a default can't be captured in useState).
  const [chosenAddressId, setSelectedAddressId] = useState(null);
  const [chosenPaymentMethod, setSelectedPaymentMethod] = useState(null);
  const methods = paymentMethods.length ? paymentMethods : FALLBACK_PAYMENT_METHODS;
  const selectedAddressId = chosenAddressId ?? customerAddresses?.[0]?.address_id ?? null;
  const selectedPaymentMethod = chosenPaymentMethod ?? methods[0]?.id ?? "upi";

  // New Address Modal state
  const [showAddressModal, setShowAddressModal] = useState(false);
  const [addrForm, setAddrForm] = useState({
    street: "",
    city: "Mumbai",
    state: "Maharashtra",
    postal_code: "",
    phone: "",
    landmark: "",
  });
  const [addrErrors, setAddrErrors] = useState({});
  const [isSavingAddr, setIsSavingAddr] = useState(false);

  // Checkout submission state
  const [isPlacingOrder, setIsPlacingOrder] = useState(false);
  const [checkoutError, setCheckoutError] = useState(null);

  const subtotal = cartTotals.subtotal || 0;
  const freeShippingProgress = Math.min(100, (subtotal / freeShippingMin) * 100);
  const remainingForFreeShipping = Math.max(0, freeShippingMin - subtotal);

  const handleApplyCoupon = async (e) => {
    e.preventDefault();
    if (isApplyingCoupon) return;
    setCouponError("");
    const code = couponInput.trim().toUpperCase();
    const formatError = validateCouponCode(code);
    if (formatError) {
      setCouponError(formatError);
      return;
    }
    setIsApplyingCoupon(true);
    const result = await applyCoupon(code);
    setIsApplyingCoupon(false);
    if (result.ok) {
      setCouponInput("");
      notify({ type: "success", title: "Coupon applied", description: result.message });
    } else {
      setCouponError(result.message);
    }
  };

  const handleSaveAddress = async (e) => {
    e.preventDefault();
    const errors = validateAddressForm(addrForm);
    if (Object.keys(errors).length > 0) {
      setAddrErrors(errors);
      return;
    }
    setAddrErrors({});
    setIsSavingAddr(true);
    try {
      const added = await addCustomerAddress(addrForm);
      setSelectedAddressId(added.address_id);
      setShowAddressModal(false);
      setAddrForm({ street: "", city: "Mumbai", state: "Maharashtra", postal_code: "", phone: "" });
      notify({
        type: "success",
        title: "Address saved",
        description: "Delivery destination has been updated.",
      });
    } catch (err) {
      notify({
        type: "error",
        title: "Could not save address",
        description: err.message || "Please check your address fields.",
      });
    } finally {
      setIsSavingAddr(false);
    }
  };

  const handlePlaceOrder = async () => {
    if (cart.length === 0 || isPlacingOrder) return;
    setCheckoutError(null);
    setIsPlacingOrder(true);

    try {
      // The server checks out its own copy of the cart (hold → pay, idempotent);
      // we only send the shopper's choices.
      const order = await placeOrder({
        addressId: selectedAddressId,
        paymentMethod: selectedPaymentMethod,
        couponCode: appliedCoupon?.code || null,
      });

      onClose();
      notify({
        type: "success",
        title: "Order placed",
        description: `Order #${order?.order_id || ""} is confirmed. Your invoice has been generated.`,
      });
      navigateTo("orders");
    } catch (err) {
      setCheckoutError(err.message || "Failed to confirm order. Please try again.");
      notify({
        type: "error",
        title: "Order confirmation error",
        description: err.message || "Could not reserve garment inventory.",
      });
    } finally {
      setIsPlacingOrder(false);
    }
  };

  return (
    <>
      <Drawer
        isOpen={isOpen}
        onClose={onClose}
        title={`Shopping Bag (${cart.reduce((sum, i) => sum + i.quantity, 0)})`}
        width="460px"
      >
        {/* Principle 1: Empty State */}
        {cart.length === 0 ? (
          <div className="bag-empty-wrap">
            <StatePanel
              type="empty"
              title="Your Shopping Bag is Empty"
              description="Add a tailored garment from the collection to compute real-time HSN 61/62 GST slabs and free shipping eligibility."
              actionLabel="Explore Garments"
              onAction={onClose}
            />
          </div>
        ) : (
          <div className="bag-content-layout">
            {/* Free Shipping Tier Bar */}
            <div className="shipping-progress-box">
              <div className="shipping-progress-text">
                {remainingForFreeShipping === 0 ? (
                  <span className="unlocked-label">
                    <Icon name="check" size={13} /> You unlocked Free Boutique Delivery
                  </span>
                ) : (
                  <span>
                    Add <strong>{formatInr(remainingForFreeShipping)}</strong> more for Free Delivery
                  </span>
                )}
              </div>
              <div className="shipping-progress-track">
                <div
                  className="shipping-progress-fill"
                  style={{ width: `${freeShippingProgress}%` }}
                />
              </div>
            </div>

            {/* Line items list */}
            <div className="bag-items-list" role="list">
              {cart.map((item) => {
                const img = getProductImage(item);
                return (
                  <div key={`${item.product_id}-${item.size}`} className="bag-line-item" role="listitem">
                    <div className="bag-item-thumb-wrap">
                      {img.url ? (
                        <img src={img.url} alt={img.alt} className="bag-item-thumb" />
                      ) : (
                        <div className="bag-item-thumb placeholder" />
                      )}
                    </div>

                    <div className="bag-item-details">
                      <div className="bag-item-header">
                        <h4 className="bag-item-title">{item.name}</h4>
                        <button
                          type="button"
                          className="icon-btn-subtle"
                          onClick={() => removeFromBag(item.product_id, item.size)}
                          aria-label={`Remove ${item.name} size ${item.size} from bag`}
                        >
                          <Icon name="close" size={14} />
                        </button>
                      </div>

                      <div className="bag-item-sub">
                        <span className="bag-size-pill">Size: {item.size}</span>
                        <span className="bag-unit-price">{formatInr(item.price)} each</span>
                      </div>

                      <div className="bag-item-footer">
                        <QuantityStepper
                          value={item.quantity}
                          onChange={(newQty) => updateQuantity(item.product_id, item.size, newQty)}
                          min={1}
                          max={10}
                        />
                        <span className="bag-item-total">
                          {formatInr(item.lineTotal)}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Coupon Code Section */}
            <div className="bag-coupon-section">
              {appliedCoupon ? (
                <div className="applied-coupon-pill">
                  <div className="coupon-lead">
                    <Icon name="check" size={14} />
                    <span>
                      <strong>{appliedCoupon.code}</strong> applied ({appliedCoupon.description || "Promo"})
                    </span>
                  </div>
                  <button
                    type="button"
                    className="coupon-remove-btn"
                    onClick={removeCoupon}
                    aria-label="Remove coupon"
                  >
                    Remove
                  </button>
                </div>
              ) : (
                <form className="coupon-form" onSubmit={handleApplyCoupon}>
                  <input
                    type="text"
                    className={`input coupon-input ${couponError ? "input--invalid" : ""}`}
                    aria-invalid={Boolean(couponError)}
                    placeholder="Promo code (e.g. ATELIER10)"
                    value={couponInput}
                    onChange={(e) => {
                      setCouponInput(e.target.value);
                      setCouponError("");
                    }}
                    aria-label="Promo code"
                  />
                  <button
                    type="submit"
                    className="btn-pill btn-sm"
                    disabled={isApplyingCoupon}
                    aria-busy={isApplyingCoupon || undefined}
                  >
                    {isApplyingCoupon ? "Checking…" : "Apply"}
                  </button>
                </form>
              )}
              {couponError && <p className="coupon-error-text">{couponError}</p>}
            </div>

            {/* Delivery Address Selector */}
            <div className="bag-checkout-section">
              <div className="checkout-subhead-row">
                <span className="control-label">Delivery Destination</span>
                <button
                  type="button"
                  className="link-subtle"
                  onClick={() => setShowAddressModal(true)}
                >
                  + Add Address
                </button>
              </div>

              <div className="addresses-picker" role="radiogroup" aria-label="Select Delivery Address">
                {(customerAddresses || []).map((addr) => (
                  <label
                    key={addr.address_id}
                    className={`address-option-card ${selectedAddressId === addr.address_id ? "selected" : ""}`}
                  >
                    <input
                      type="radio"
                      name="delivery_address"
                      value={addr.address_id}
                      checked={selectedAddressId === addr.address_id}
                      onChange={() => setSelectedAddressId(addr.address_id)}
                      className="sr-only"
                    />
                    <div className="address-card-body">
                      <div className="address-street">{addr.street}</div>
                      <div className="address-city-state">
                        {addr.city}, {addr.state} — {addr.postal_code}
                      </div>
                    </div>
                    {selectedAddressId === addr.address_id && (
                      <span className="address-check">
                        <Icon name="check" size={14} />
                      </span>
                    )}
                  </label>
                ))}
              </div>
            </div>

            {/* Payment Method Selector */}
            <div className="bag-checkout-section">
              <span className="control-label">Payment Method</span>
              <div className="payment-options-grid" role="radiogroup" aria-label="Payment method">
                {methods.map((pm) => {
                  // e.g. EMI has a minimum order value enforced by the backend
                  const belowMinimum = cartTotals.grandTotal < (pm.minOrder || 0);
                  return (
                    <button
                      key={pm.id}
                      type="button"
                      className={`payment-method-chip ${selectedPaymentMethod === pm.id ? "active" : ""}`}
                      onClick={() => setSelectedPaymentMethod(pm.id)}
                      role="radio"
                      aria-checked={selectedPaymentMethod === pm.id}
                      disabled={belowMinimum}
                      title={belowMinimum ? `Available on orders above ${formatInr(pm.minOrder)}` : undefined}
                    >
                      {pm.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Price Breakdown / GST Calculation */}
            <div className="bag-summary-card">
              <div className="summary-line">
                <span>Subtotal ({cart.reduce((s, i) => s + i.quantity, 0)} items)</span>
                <span>{formatInr(cartTotals.subtotal)}</span>
              </div>

              {cartTotals.discount > 0 && (
                <div className="summary-line discount">
                  <span>Promo Discount ({appliedCoupon?.code})</span>
                  <span>−{formatInr(cartTotals.discount)}</span>
                </div>
              )}

              {/* Prices are GST-inclusive: these lines show the tax inside the subtotal */}
              {cartTotals.gstLines.map(({ rate, amount }) => (
                <div key={rate} className="summary-line tax">
                  <span>
                    Incl. GST {rate}% (garments {taxRules.describe(rate)})
                  </span>
                  <span>{formatInr(amount)}</span>
                </div>
              ))}

              <div className="summary-line">
                <span>Boutique Delivery</span>
                <span>{cartTotals.shipping === 0 ? "Complimentary" : formatInr(cartTotals.shipping)}</span>
              </div>

              <div className="summary-line grand-total">
                <span>Grand Total</span>
                <span className="grand-price">{formatInr(cartTotals.grandTotal)}</span>
              </div>
            </div>

            {/* Error Message if checkout fails */}
            {checkoutError && (
              <div className="checkout-error-banner" role="alert">
                <Icon name="alert" size={16} />
                <span>{checkoutError}</span>
              </div>
            )}

            {/* Place Order CTA */}
            <div className="bag-actions-footer">
              <Button
                variant="primary"
                size="lg"
                onClick={handlePlaceOrder}
                isLoading={isPlacingOrder}
                style={{ width: "100%" }}
              >
                Confirm & Place Order · {formatInr(cartTotals.grandTotal)}
              </Button>
              <p className="checkout-guarantee-note">
                <Icon name="lock" size={12} /> 256-bit Secure Encryption · 7-Day Guarantee
              </p>
            </div>
          </div>
        )}
      </Drawer>

      {/* Add Address Modal (Principle 9: Form Validation) */}
      <Modal
        isOpen={showAddressModal}
        onClose={() => setShowAddressModal(false)}
        title="Add Delivery Address"
        size="md"
      >
        <form onSubmit={handleSaveAddress} className="form-stack" noValidate>
          <TextField
            label="Street Address / Residence"
            value={addrForm.street}
            onChange={(e) => setAddrForm({ ...addrForm, street: e.target.value })}
            error={addrErrors.street}
            placeholder="e.g. 14 Crescent Bay, Colaba"
            required
          />

          <div className="form-two-col">
            <TextField
              label="City"
              value={addrForm.city}
              onChange={(e) => setAddrForm({ ...addrForm, city: e.target.value })}
              error={addrErrors.city}
              required
            />
            <TextField
              label="State"
              value={addrForm.state}
              onChange={(e) => setAddrForm({ ...addrForm, state: e.target.value })}
              error={addrErrors.state}
              required
            />
          </div>

          <div className="form-two-col">
            <TextField
              label="Postal / PIN Code"
              value={addrForm.postal_code}
              onChange={(e) => setAddrForm({ ...addrForm, postal_code: e.target.value })}
              error={addrErrors.postal_code}
              placeholder="e.g. 400005"
              required
            />
            <TextField
              label="Contact Phone"
              value={addrForm.phone}
              onChange={(e) => setAddrForm({ ...addrForm, phone: e.target.value })}
              error={addrErrors.phone}
              placeholder="e.g. 9820012345"
              required
            />
          </div>

          <div className="modal-actions-bar">
            <Button type="button" variant="ghost" onClick={() => setShowAddressModal(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" isLoading={isSavingAddr}>
              Save Address
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
