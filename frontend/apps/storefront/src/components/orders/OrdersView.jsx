"use client";

import React, { useState } from "react";
import { useStore } from "@/store/StoreProvider";
import { Modal } from "@/components/ui/Overlay";
import { Icon } from "@/components/ui/Icon";
import { Button } from "@/components/ui/Controls";
import { StatePanel, ListSkeleton } from "@/components/ui/StatePanel";
import { formatInr, validateReturnForm } from "@noir/utils/formatters.js";

const RETURN_REASONS = [
  { id: "size_fit", label: "Size / Fit Adjustment Required" },
  { id: "fabric_defect", label: "Fabric or Weave Inconsistency" },
  { id: "damaged_transit", label: "Damaged in Transit" },
  { id: "changed_mind", label: "Changed Mind / Prefer Different Silhouette" },
];

export function OrdersView() {
  const {
    orders,
    isLoadingOrders,
    ordersError,
    refreshOrders,
    apiClient,
    currentActor,
    notify,
    navigateTo,
  } = useStore();

  // Return modal state
  const [returnOrder, setReturnOrder] = useState(null);
  const [returnItem, setReturnItem] = useState(null);
  const [returnReason, setReturnReason] = useState("size_fit");
  const [tagIntact, setTagIntact] = useState(true);
  const [customerNote, setCustomerNote] = useState("");
  const [returnErrors, setReturnErrors] = useState({});
  const [isSubmittingReturn, setIsSubmittingReturn] = useState(false);

  // Cancelling order state
  const [cancellingOrderId, setCancellingOrderId] = useState(null);

  const handleCancelOrder = async (orderId) => {
    if (!window.confirm(`Are you sure you want to cancel order #${orderId}?`)) return;
    setCancellingOrderId(orderId);
    try {
      await apiClient.cancelOrder(orderId, "Customer requested pre-dispatch cancellation");
      notify({
        type: "success",
        title: "Order Cancelled",
        description: `Order #${orderId} was cancelled. Pre-auth hold released.`,
      });
      await refreshOrders();
    } catch (err) {
      notify({
        type: "error",
        title: "Cancellation Failed",
        description: err.message || "Order cannot be cancelled at this stage.",
      });
    } finally {
      setCancellingOrderId(null);
    }
  };

  const handleOpenReturnModal = (order) => {
    setReturnOrder(order);
    setReturnItem(order.items?.[0] || null);
    setReturnReason("size_fit");
    setTagIntact(true);
    setCustomerNote("");
    setReturnErrors({});
  };

  const handleSubmitReturn = async (e) => {
    e.preventDefault();
    const errors = validateReturnForm({
      reason: returnReason,
      condition: tagIntact ? "tags_intact" : "tags_missing",
      customer_note: customerNote,
    });
    if (Object.keys(errors).length > 0) {
      setReturnErrors(errors);
      return;
    }
    setReturnErrors({});
    setIsSubmittingReturn(true);

    try {
      const res = await apiClient.createReturn({
        order_id: returnOrder.order_id,
        item_id: returnItem?.product_id || returnOrder.items?.[0]?.product_id,
        reason: returnReason,
        condition: tagIntact ? "tags_intact" : "tags_missing",
        customer_note: customerNote.trim(),
      });

      notify({
        type: "success",
        title: "Return Request Created",
        description: `Return #${res.return_id || "RMA-NEW"} created. Refund Tier: ${
          res.refund_tier || "Tier 1 Instant"
        }.`,
      });
      setReturnOrder(null);
      await refreshOrders();
    } catch (err) {
      notify({
        type: "error",
        title: "Return submission failed",
        description: err.message || "Could not submit return claim.",
      });
    } finally {
      setIsSubmittingReturn(false);
    }
  };

  return (
    <div className="orders-page-container">
      {/* Editorial Header */}
      <div className="orders-header-bar">
        <div>
          <span className="hero-eyebrow">Client Order History</span>
          <h1 className="page-heading">Your Atelier Dispatches</h1>
          <p className="page-subheading">
            Track status, view GST invoices, and manage 7-day atelier garment returns.
          </p>
        </div>
        <button
          type="button"
          className="btn-pill btn-pill-outline btn-sm"
          onClick={refreshOrders}
          disabled={isLoadingOrders}
        >
          <Icon name="refresh" size={14} />
          <span>Refresh Orders</span>
        </button>
      </div>

      {/* Principle 2: Loading State */}
      {isLoadingOrders && <ListSkeleton count={3} />}

      {/* Principle 3: Error State */}
      {!isLoadingOrders && ordersError && (
        <StatePanel
          type="error"
          title="Could not load orders"
          description={ordersError}
          actionLabel="Retry loading"
          onAction={refreshOrders}
        />
      )}

      {/* Principle 1: Empty State */}
      {!isLoadingOrders && !ordersError && (!orders || orders.length === 0) && (
        <StatePanel
          type="empty"
          title="No Orders on Record"
          description={`No past garment dispatches found for actor ${currentActor?.label || "CUS-001"}. Start your luxury collection with our tailored pieces.`}
          actionLabel="Explore The Edit"
          onAction={() => navigateTo("shop")}
        />
      )}

      {/* Orders List */}
      {!isLoadingOrders && !ordersError && orders && orders.length > 0 && (
        <div className="orders-list-stack">
          {orders.map((order) => {
            const isCancellable = ["HOLD", "CONFIRMED", "PENDING"].includes(
              (order.status || "").toUpperCase()
            );
            const isDelivered = (order.status || "").toUpperCase() === "DELIVERED";

            return (
              <article key={order.order_id} className="order-record-card">
                <header className="order-card-header">
                  <div className="order-id-group">
                    <span className="order-ref-label">Order Ref:</span>
                    <strong className="order-id-value">#{order.order_id}</strong>
                    <span className={`order-status-pill status-${(order.status || "").toLowerCase()}`}>
                      {order.status || "CONFIRMED"}
                    </span>
                  </div>

                  <div className="order-header-meta">
                    <span className="order-date">
                      {order.created_at
                        ? new Date(order.created_at).toLocaleDateString("en-IN", {
                            day: "numeric",
                            month: "short",
                            year: "numeric",
                          })
                        : "Recent"}
                    </span>
                    <span className="order-grand-total">
                      {formatInr(order.grand_total || order.total_amount || 0)}
                    </span>
                  </div>
                </header>

                {/* Items in this order */}
                <div className="order-items-grid">
                  {(order.items || []).map((item, idx) => (
                    <div key={idx} className="order-item-snippet">
                      <div className="order-item-lead">
                        <span className="order-item-name">
                          {item.product_name || item.name || item.product_id}
                        </span>
                        <span className="order-item-sub">
                          Size: {item.size || "M"} · Qty: {item.quantity || 1}
                        </span>
                      </div>
                      <span className="order-item-price">
                        {formatInr((item.unit_price || item.price || 0) * (item.quantity || 1))}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Footer Actions: Cancel, Return, Invoice */}
                <footer className="order-card-footer">
                  <div className="order-meta-info">
                    {order.gst_total ? (
                      <span className="gst-badge">
                        GST: {formatInr(order.gst_total)} (HSN compliant)
                      </span>
                    ) : null}
                    {order.payment_status && (
                      <span className="payment-status-badge">
                        Payment: {order.payment_status}
                      </span>
                    )}
                  </div>

                  <div className="order-actions-group">
                    {isCancellable && (
                      <button
                        type="button"
                        className="btn-pill btn-pill-outline btn-sm btn-danger-tone"
                        onClick={() => handleCancelOrder(order.order_id)}
                        disabled={cancellingOrderId === order.order_id}
                      >
                        {cancellingOrderId === order.order_id ? "Cancelling..." : "Cancel Order"}
                      </button>
                    )}

                    {isDelivered && (
                      <button
                        type="button"
                        className="btn-pill btn-pill-outline btn-sm"
                        onClick={() => handleOpenReturnModal(order)}
                      >
                        <Icon name="refresh" size={13} />
                        <span>Initiate 7-Day Return</span>
                      </button>
                    )}

                    <a
                      href={`/api/orders/${order.order_id}/invoice`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-pill btn-pill-outline btn-sm"
                    >
                      <Icon name="file" size={13} />
                      <span>Download Invoice</span>
                    </a>
                  </div>
                </footer>
              </article>
            );
          })}
        </div>
      )}

      {/* 4-Tier Garment Return Modal (Principle 9: Form Validation) */}
      <Modal
        isOpen={!!returnOrder}
        onClose={() => setReturnOrder(null)}
        title={`Initiate Return — Order #${returnOrder?.order_id}`}
        size="md"
      >
        <form onSubmit={handleSubmitReturn} className="return-form-layout">
          <p className="return-policy-note">
            Noir Atelier honors a 7-day return window. Garments must have original security
            tags intact for Tier 1 instant full refund.
          </p>

          <div className="form-field-group">
            <label className="field-label" htmlFor="return-reason-select">
              Reason for Return
            </label>
            <select
              id="return-reason-select"
              className="select-control"
              value={returnReason}
              onChange={(e) => setReturnReason(e.target.value)}
            >
              {RETURN_REASONS.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>

          <div className="form-field-group">
            <label className="checkbox-control-label">
              <input
                type="checkbox"
                checked={tagIntact}
                onChange={(e) => setTagIntact(e.target.checked)}
              />
              <span>Original luxury security ribbon &amp; care tag are attached and untampered</span>
            </label>
            {!tagIntact && (
              <span className="field-warning-msg">
                Note: Missing tags require physical studio verification and will route to Tier 2 review.
              </span>
            )}
          </div>

          <div className="form-field-group">
            <label className="field-label" htmlFor="return-note-input">
              Client Fitting Notes (Optional)
            </label>
            <textarea
              id="return-note-input"
              className={`textarea-control ${returnErrors.customer_note ? "error" : ""}`}
              rows={3}
              placeholder="Provide specific notes regarding fit, drape, or replacement size desired…"
              value={customerNote}
              onChange={(e) => setCustomerNote(e.target.value)}
            />
            {returnErrors.customer_note && (
              <span className="field-error-msg">{returnErrors.customer_note}</span>
            )}
          </div>

          <div className="modal-actions-bar">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setReturnOrder(null)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              isLoading={isSubmittingReturn}
            >
              Submit Return Claim
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
