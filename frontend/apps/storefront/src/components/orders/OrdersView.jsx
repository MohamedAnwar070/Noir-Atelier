"use client";

import React, { useEffect, useState } from "react";
import { useStore } from "@/store/StoreProvider";
import { Modal } from "@/components/ui/Overlay";
import { Icon } from "@/components/ui/Icon";
import { Button } from "@/components/ui/Controls";
import { StatePanel, ListSkeleton } from "@/components/ui/StatePanel";
import { formatInr, validateReturnForm } from "@noir/utils/formatters.js";

const ORDER_DATE_FORMAT = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });

export function OrdersView() {
  const {
    orders,
    isLoadingOrders,
    ordersError,
    refreshOrders,
    apiClient,
    currentActor,
    catalogMeta,
    business,
    notify,
    navigateTo,
  } = useStore();

  const returnReasons = catalogMeta?.return_reasons || [];
  const returnDays = business?.returns_and_refunds?.return_window_days ?? 7;

  const [invoiceOrder, setInvoiceOrder] = useState(null);

  // Return modal state
  const [returnOrder, setReturnOrder] = useState(null);
  const [returnReason, setReturnReason] = useState("");
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
    setReturnReason(returnReasons[0]?.code || "");
    setTagIntact(true);
    setCustomerNote("");
    setReturnErrors({});
  };

  const selectedReasonMeta = returnReasons.find((r) => r.code === returnReason) || null;

  const handleSubmitReturn = async (e) => {
    e.preventDefault();
    const { valid, errors } = validateReturnForm({
      orderId: returnOrder?.order_id,
      reasonCategory: returnReason,
      customer_note: customerNote,
      optionalNotes: true,
      tagIntact,
    });
    if (!valid) {
      setReturnErrors(errors);
      return;
    }
    setReturnErrors({});
    setIsSubmittingReturn(true);

    try {
      const res = await apiClient.initiateReturn({
        orderId: returnOrder.order_id,
        reasonCategory: returnReason,
        customerNotes: customerNote.trim() || selectedReasonMeta?.label || "",
        tagIntact,
        isDefectiveClaim: Boolean(selectedReasonMeta?.is_defect_claim),
      });

      notify({
        type: "success",
        title: "Return requested",
        description: `Return #${res.return_id} created · Tier ${res.approval_tier ?? 1} refund review.`,
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
    <div className="page-container orders-page-container">
      {/* Editorial Header */}
      <div className="page-header">
        <div>
          <span className="hero-eyebrow">Client Order History</span>
          <h1 className="page-heading">Your Atelier Dispatches</h1>
          <p className="page-subheading">
            Track status, view GST invoices, and manage {returnDays}-day atelier garment returns.
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
          {orders.map((order) => (
            <article key={order.order_id} className="order-record-card">
              <header className="order-card-header">
                <div className="order-id-group">
                  <span className="order-ref-label">Order Ref:</span>
                  <strong className="order-id-value">#{order.order_id}</strong>
                  <span className={`badge order-status-pill status-${order.status}`}>
                    {order.statusLabel}
                  </span>
                </div>

                <div className="order-header-meta">
                  {order.placedAt && (
                    <time className="order-date" dateTime={order.placedAt.toISOString()}>
                      {ORDER_DATE_FORMAT.format(order.placedAt)}
                    </time>
                  )}
                  <span className="order-grand-total">{formatInr(order.grandTotal)}</span>
                </div>
              </header>

              {/* Items in this order */}
              <div className="order-items-grid">
                {order.items.map((item) => (
                  <div key={`${item.product_id}-${item.size}`} className="order-item-snippet">
                    <div className="order-item-lead">
                      <span className="order-item-name">{item.name}</span>
                      <span className="order-item-sub">
                        Size: {item.size} · Qty: {item.quantity}
                        {item.quantity > 1 && ` · ${formatInr(item.unitPrice)} each`}
                      </span>
                    </div>
                    <span className="order-item-price">{formatInr(item.lineTotal)}</span>
                  </div>
                ))}
              </div>

              {/* Footer Actions: Cancel, Return, Invoice */}
              <footer className="order-card-footer">
                <div className="order-meta-info">
                  {order.gstTotal > 0 && (
                    <span className="badge gst-badge">Incl. GST {formatInr(order.gstTotal)}</span>
                  )}
                  {order.paymentStatus && (
                    <span className="badge payment-status-badge">
                      Payment: {order.paymentStatus.replace(/_/g, " ")}
                    </span>
                  )}
                </div>

                <div className="order-actions-group">
                  {order.canCancel && (
                    <button
                      type="button"
                      className="btn-pill btn-pill-outline btn-sm btn-danger-tone"
                      onClick={() => handleCancelOrder(order.order_id)}
                      disabled={cancellingOrderId === order.order_id}
                    >
                      {cancellingOrderId === order.order_id ? "Cancelling..." : "Cancel Order"}
                    </button>
                  )}

                  {order.canReturn && (
                    <button
                      type="button"
                      className="btn-pill btn-pill-outline btn-sm"
                      onClick={() => handleOpenReturnModal(order)}
                    >
                      <Icon name="refresh" size={13} />
                      <span>Request return</span>
                    </button>
                  )}

                  {order.invoice_id && (
                    <button
                      type="button"
                      className="btn-pill btn-pill-outline btn-sm"
                      onClick={() => setInvoiceOrder(order)}
                    >
                      <Icon name="file" size={13} />
                      <span>View invoice</span>
                    </button>
                  )}
                </div>
              </footer>
            </article>
          ))}
        </div>
      )}

      {/* 4-Tier Garment Return Modal (Database-Driven Return Reasons) */}
      <Modal
        isOpen={!!returnOrder}
        onClose={() => setReturnOrder(null)}
        title={`Initiate Return — Order #${returnOrder?.order_id}`}
        size="md"
      >
        <form onSubmit={handleSubmitReturn} className="form-stack">
          <p className="return-policy-note">
            Noir Atelier honors a {returnDays}-day return window. Garments must have original security
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
              {returnReasons.map((r) => (
                <option key={r.code} value={r.code}>
                  {r.label}
                </option>
              ))}
            </select>
            {selectedReasonMeta?.is_defect_claim && (
              <span style={{ fontSize: "11px", color: "var(--text-secondary)", marginTop: "0.25rem", display: "block" }}>
                Defect &amp; transit claims are eligible across all garments, including Final Sale pieces.
              </span>
            )}
            {returnErrors.reasonCategory && (
              <span className="field-error-msg">{returnErrors.reasonCategory}</span>
            )}
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
              <span className="field-warning-msg" role="alert">
                We can only accept returns with the security ribbon and care tag intact (policy POL-RET-01).
              </span>
            )}
          </div>

          <div className="form-field-group">
            <label className="field-label" htmlFor="return-note-input">
              Client Fitting Notes (Optional)
            </label>
            <textarea
              id="return-note-input"
              className={`textarea-control ${returnErrors.reasonNotes ? "error" : ""}`}
              rows={3}
              placeholder="Provide specific notes regarding fit, drape, or replacement size desired…"
              value={customerNote}
              onChange={(e) => setCustomerNote(e.target.value)}
            />
            {returnErrors.reasonNotes && (
              <span className="field-error-msg">{returnErrors.reasonNotes}</span>
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
              disabled={!tagIntact || !returnReason}
            >
              Submit Return Claim
            </Button>
          </div>
        </form>
      </Modal>

      <InvoiceModal order={invoiceOrder} onClose={() => setInvoiceOrder(null)} />
    </div>
  );
}

/**
 * GST invoice for an order. Fetched through the authenticated API client
 * (a plain link can't send the bearer token) and printable via the browser.
 */
function InvoiceModal({ order, onClose }) {
  const { apiClient } = useStore();
  const [state, setState] = useState({ status: "idle", invoice: null, error: null });

  useEffect(() => {
    if (!order) return undefined;
    let cancelled = false;
    setState({ status: "loading", invoice: null, error: null });
    apiClient
      .getInvoice(order.order_id)
      .then((invoice) => !cancelled && setState({ status: "ready", invoice, error: null }))
      .catch((error) => !cancelled && setState({ status: "error", invoice: null, error }));
    return () => {
      cancelled = true;
    };
  }, [order, apiClient]);

  const { invoice } = state;
  const taxLines = invoice
    ? invoice.is_intra_state
      ? [
          ["CGST", invoice.cgst_inr],
          ["SGST", invoice.sgst_inr],
        ]
      : [["IGST", invoice.igst_inr]]
    : [];

  return (
    <Modal
      isOpen={Boolean(order)}
      onClose={onClose}
      title={invoice ? `Tax invoice ${invoice.invoice_id}` : "Tax invoice"}
      size="sm"
    >
      {state.status === "loading" && <ListSkeleton count={2} />}

      {state.status === "error" && (
        <StatePanel
          type="error"
          compact
          title="Couldn't load this invoice"
          description={state.error?.message}
        />
      )}

      {invoice && (
        <div className="form-stack">
          <div className="bag-summary-card">
            <div className="summary-line">
              <span>Order</span>
              <span>#{invoice.order_id}</span>
            </div>
            <div className="summary-line">
              <span>Seller GSTIN</span>
              <span>{invoice.seller_gstin}</span>
            </div>
            <div className="summary-line">
              <span>Place of supply</span>
              <span>{invoice.place_of_supply_state}</span>
            </div>
          </div>

          <div className="bag-summary-card">
            <div className="summary-line">
              <span>Taxable value</span>
              <span>{formatInr(invoice.taxable_value_inr)}</span>
            </div>
            {taxLines.map(([label, amount]) => (
              <div key={label} className="summary-line tax">
                <span>{label}</span>
                <span>{formatInr(amount)}</span>
              </div>
            ))}
            <div className="summary-line grand-total">
              <span>Invoice total</span>
              <span className="grand-price">{formatInr(invoice.total_inr)}</span>
            </div>
          </div>

          <div className="modal-actions-bar">
            <Button variant="ghost" onClick={onClose}>
              Close
            </Button>
            <Button variant="primary" icon="file" onClick={() => window.print()}>
              Print
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
