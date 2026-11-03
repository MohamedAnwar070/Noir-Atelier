from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import random
import threading
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import ActorContext
from ..config import get_settings
from ..models import (
    Cart,
    Coupon,
    CouponUsage,
    Customer,
    CustomerAddress,
    IdempotencyKey,
    Inventory,
    Invoice,
    Order,
    OrderItem,
    Payment,
    Product,
    Refund,
    Shipment,
)
from ..schemas.order_schema import (
    OrderCalculateRequest,
    OrderCancelRequest,
    OrderCreateRequest,
    PaymentInitiateRequest,
    ShipmentScheduleRequest,
)
from ..storage.object_store import LocalObjectStore
from ..utils.exceptions import AppError
from .audit_service import get_idempotent_result, next_entity_id, record_audit, save_idempotent_result
from .config_service import get_business_config_map
from .product_service import get_product_by_id_or_sku
from .variant_service import build_line_item
from .tax_service import calculate_order_financials

MAX_ORDER_LINES = 25
MAX_ORDER_QUANTITY = 99
_ORDER_CONCURRENCY_LOCK = threading.RLock()


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def merge_order_lines(raw_lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not raw_lines:
        raise AppError("validation_error", "items must be a non-empty array.", 400)
    if len(raw_lines) > MAX_ORDER_LINES:
        raise AppError("validation_error", f"No more than {MAX_ORDER_LINES} line items per order.", 400)

    merged: Dict[tuple, Dict[str, Any]] = {}
    per_product_totals: Dict[str, int] = {}

    for line in raw_lines:
        pid = str(line["product_id"]).strip().upper()
        size = str(line.get("size") or "M").strip().upper()
        qty = int(line["quantity"])
        if qty < 1 or qty > MAX_ORDER_QUANTITY:
            raise AppError(
                "validation_error",
                f"quantity must be an integer between 1 and {MAX_ORDER_QUANTITY}.",
                400,
            )
        per_product_totals[pid] = per_product_totals.get(pid, 0) + qty
        if per_product_totals[pid] > MAX_ORDER_QUANTITY:
            raise AppError(
                "validation_error",
                f"Combined quantity for {pid} exceeds {MAX_ORDER_QUANTITY}.",
                400,
            )
        key = (pid, size)
        if key in merged:
            merged[key]["quantity"] += qty
        else:
            copied = dict(line)
            copied["product_id"] = pid
            copied["size"] = size
            copied["quantity"] = qty
            merged[key] = copied

    return sorted(merged.values(), key=lambda x: (x["product_id"], x["size"]))


def build_product_order_idempotency_key(
    customer_id: str,
    merged_lines: List[Dict[str, Any]],
    coupon_code: Optional[str] = None,
    explicit_key: Optional[str] = None,
) -> Optional[str]:
    if not explicit_key or not explicit_key.strip():
        return None
    raw_key = explicit_key.strip()
    if raw_key.lower() == "auto":
        canonical = json.dumps(
            {
                "customer_id": customer_id,
                "coupon": (coupon_code or "").strip().upper(),
                "items": [
                    {"product_id": l["product_id"], "size": l["size"], "quantity": int(l["quantity"])}
                    for l in sorted(merged_lines, key=lambda x: (x["product_id"], x["size"]))
                ],
            },
            sort_keys=True,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
        return f"ord:{customer_id}:{digest}"
    return raw_key[:128]


def _assert_order_access(actor: ActorContext, order: Order) -> None:
    if actor.actor_type == "admin":
        return
    if actor.actor_type == "customer" and actor.actor_id != order.customer_id:
        raise AppError("forbidden_order_access", "You do not have permission to access this order.", 403)
    if actor.actor_type == "agent" and actor.on_behalf_of and actor.on_behalf_of != order.customer_id:
        raise AppError("forbidden_order_access", "Order ownership verification failed for this customer.", 403)


def serialize_order(db: Session, order: Order) -> Dict[str, Any]:
    payment = db.scalar(select(Payment).where(Payment.order_id == order.order_id).order_by(Payment.created_at.desc()))
    invoice = db.scalar(select(Invoice).where(Invoice.order_id == order.order_id))
    shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.order_id).order_by(Shipment.created_at.desc()))

    now = datetime.now(timezone.utc)
    hold_exp = _ensure_utc(order.hold_expires_at)
    expires_in_seconds = (
        max(0, int((hold_exp - now).total_seconds()))
        if order.status == "pending" and hold_exp is not None
        else 0
    )
    total_paise = order.total_paise if order.total_paise else int(round(float(order.grand_total_inr) * 100))

    return {
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "status": order.status,
        "order_date": order.order_date.isoformat(),
        "items": [
            {
                "product_id": i.product_id,
                "sku": i.sku,
                "product_name": i.product_name,
                "size": i.size,
                "quantity": i.quantity,
                "unit_mrp_inr": float(i.unit_mrp_inr),
                "unit_discount_inr": float(i.unit_discount_inr),
                "unit_sale_value_inr": float(i.unit_sale_value_inr),
                "gst_rate_pct": float(i.gst_rate_pct),
                "gst_amount_inr": float(i.gst_amount_inr),
                "final_sale": i.final_sale,
            }
            for i in order.items
        ],
        "subtotal_mrp_inr": float(order.subtotal_mrp_inr),
        "discount_inr": float(order.discount_inr),
        "taxable_value_inr": float(order.taxable_value_inr),
        "cgst_inr": float(order.cgst_inr),
        "sgst_inr": float(order.sgst_inr),
        "igst_inr": float(order.igst_inr),
        "total_gst_inr": float(order.total_gst_inr),
        "shipping_fee_inr": float(order.shipping_fee_inr),
        "grand_total_inr": float(order.grand_total_inr),
        "total_paise": total_paise,
        "currency": order.currency,
        "payment_status": payment.status if payment else ("paid" if order.status in ("paid", "confirmed", "picked_up") else "pending"),
        "payment_id": payment.payment_id if payment else None,
        "invoice_id": invoice.invoice_id if invoice else None,
        "tracking_number": shipment.tracking_number if shipment else None,
        "signature_required": order.signature_required,
        "hold_expires_at": hold_exp.isoformat() if hold_exp else None,
        "expires_at": hold_exp.isoformat() if hold_exp else None,
        "expires_in_seconds": expires_in_seconds,
        "paid_at": _ensure_utc(order.paid_at).isoformat() if order.paid_at else None,
        "paid_amount_paise": order.paid_amount_paise,
        "cancelled_at": _ensure_utc(order.cancelled_at).isoformat() if order.cancelled_at else None,
        "picked_up_at": _ensure_utc(order.picked_up_at).isoformat() if order.picked_up_at else None,
        "review_reason": order.review_reason,
        "refund_flag": bool(order.refund_flag),
        "locker_number": order.locker_number,
        "pickup_code": order.pickup_code,
    }


def _lock_inventories_asc(db: Session, product_ids: List[str]) -> Dict[str, Inventory]:
    sorted_pids = sorted(set(product_ids))
    if not sorted_pids:
        return {}
    rows = db.scalars(
        select(Inventory)
        .where(Inventory.product_id.in_(sorted_pids))
        .order_by(Inventory.product_id.asc())
        .with_for_update()
    ).all()
    return {inv.product_id: inv for inv in rows}


def _release_reserved_stock_for_order(db: Session, order: Order) -> None:
    pids = [item.product_id for item in order.items]
    inv_map = _lock_inventories_asc(db, pids)
    for item in sorted(order.items, key=lambda x: (x.product_id, x.size)):
        inv = inv_map.get(item.product_id)
        if inv is not None:
            inv.quantity_available += int(item.quantity)
            inv.quantity_reserved = max(0, int(inv.quantity_reserved or 0) - int(item.quantity))


def expire_order_if_due(db: Session, order: Order) -> bool:
    if order.status != "pending" or order.hold_expires_at is None:
        return False
    now = datetime.now(timezone.utc)
    hold_exp = _ensure_utc(order.hold_expires_at)
    if hold_exp is not None and hold_exp <= now:
        _release_reserved_stock_for_order(db, order)
        order.status = "expired"
        db.commit()
        return True
    return False


def sweep_expired_orders(db: Session) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    pending_orders = db.scalars(
        select(Order).where(Order.status == "pending", Order.hold_expires_at.is_not(None)).with_for_update()
    ).all()
    released_ids: List[str] = []
    for order in pending_orders:
        hold_exp = _ensure_utc(order.hold_expires_at)
        if hold_exp is not None and hold_exp <= now:
            _release_reserved_stock_for_order(db, order)
            order.status = "expired"
            released_ids.append(order.order_id)
    if released_ids:
        db.commit()
    return {"released_count": len(released_ids), "expired_order_ids": released_ids}


def _ensure_invoice_for_order(db: Session, order: Order, dest_state: str = "Tamil Nadu") -> Invoice:
    existing = db.scalar(select(Invoice).where(Invoice.order_id == order.order_id))
    if existing is not None:
        return existing
    invoice_id = next_entity_id(db, Invoice, Invoice.invoice_id, "invoice", start_seq=1001)
    month_folder = datetime.now(timezone.utc).strftime("%Y-%m")
    object_store = LocalObjectStore()
    is_intra = dest_state.strip().lower() == "tamil nadu"
    seller_gstin = "33AABCN1234F1Z5"
    invoice_payload = {
        "invoice_id": invoice_id,
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "seller_gstin": seller_gstin,
        "place_of_supply_state": dest_state,
        "is_intra_state": is_intra,
        "subtotal_mrp_inr": str(order.subtotal_mrp_inr),
        "discount_inr": str(order.discount_inr),
        "taxable_value_inr": str(order.taxable_value_inr),
        "cgst_inr": str(order.cgst_inr),
        "sgst_inr": str(order.sgst_inr),
        "igst_inr": str(order.igst_inr),
        "shipping_fee_inr": str(order.shipping_fee_inr),
        "grand_total_inr": str(order.grand_total_inr),
    }
    storage_key = object_store.put_json("invoices", month_folder, f"{invoice_id}.json", invoice_payload)
    inv_row = Invoice(
        invoice_id=invoice_id,
        order_id=order.order_id,
        seller_gstin=seller_gstin,
        place_of_supply_state=dest_state,
        is_intra_state=is_intra,
        taxable_value_inr=order.taxable_value_inr,
        cgst_inr=order.cgst_inr,
        sgst_inr=order.sgst_inr,
        igst_inr=order.igst_inr,
        total_inr=order.grand_total_inr,
        storage_key=storage_key,
    )
    db.add(inv_row)
    return inv_row


def calculate_order_preview(db: Session, req: OrderCalculateRequest) -> Dict[str, Any]:
    raw_lines: List[Dict[str, Any]] = []
    for item in req.items:
        prod = get_product_by_id_or_sku(db, item.product_id)
        raw_lines.append(build_line_item(prod, item.size, item.quantity))
    merged_lines = merge_order_lines(raw_lines)
    return calculate_order_financials(
        db,
        merged_lines,
        coupon_code=req.coupon_code,
        destination_state=req.destination_state,
        destination_pin=req.destination_pin,
    )


def create_order(db: Session, actor: ActorContext, req: OrderCreateRequest) -> Dict[str, Any]:
    with _ORDER_CONCURRENCY_LOCK:
        return _create_order_locked(db, actor, req)


def _create_order_locked(db: Session, actor: ActorContext, req: OrderCreateRequest) -> Dict[str, Any]:
    if req.request_key and req.request_key.strip().lower() != "auto":
        cached = get_idempotent_result(db, req.request_key)
        if cached is not None:
            return dict(cached.response_snapshot)

    method = req.payment_method.strip().lower()
    if method == "cod":
        raise AppError("cod_not_allowed", "Cash on delivery (COD) is disabled for Noir Atelier orders.", 422)

    customer_id = req.customer_id or actor.on_behalf_of or (actor.actor_id if actor.actor_type == "customer" else "CUS-001")
    customer = db.scalar(select(Customer).where(Customer.customer_id == customer_id))
    if customer is None:
        raise AppError("customer_not_found", f"Customer '{customer_id}' not found.", 404)

    address = None
    if req.shipping_address_id:
        address = db.scalar(select(CustomerAddress).where(CustomerAddress.address_id == req.shipping_address_id))
    if address is None:
        address = db.scalar(
            select(CustomerAddress).where(CustomerAddress.customer_id == customer_id).order_by(CustomerAddress.is_primary.desc())
        )

    dest_state = address.state if address else "Tamil Nadu"
    dest_pin = address.pin_code if address else "600086"

    raw_lines: List[Dict[str, Any]] = []
    cart_rows_to_clear: List[Cart] = []

    if req.items is not None:
        if len(req.items) == 0:
            raise AppError("validation_error", "items must be a non-empty array.", 400)
        for line in req.items:
            prod = get_product_by_id_or_sku(db, line.product_id)
            raw_lines.append(build_line_item(prod, line.size, line.quantity))
    else:
        sess_id = req.session_id or f"sess-{customer_id}"
        cart_rows_to_clear = list(
            db.scalars(select(Cart).where((Cart.session_id == sess_id) | (Cart.customer_id == customer_id))).all()
        )
        if not cart_rows_to_clear:
            raise AppError("empty_cart", "Cannot create order: no items provided and cart is empty.", 422)
        for c in cart_rows_to_clear:
            prod = get_product_by_id_or_sku(db, c.product_id)
            raw_lines.append(build_line_item(prod, c.size, c.quantity))

    merged_lines = merge_order_lines(raw_lines)
    effective_idem_key = build_product_order_idempotency_key(
        customer_id=customer_id,
        merged_lines=merged_lines,
        coupon_code=req.coupon_code,
        explicit_key=req.request_key,
    )
    if effective_idem_key:
        cached = get_idempotent_result(db, effective_idem_key)
        if cached is not None:
            return dict(cached.response_snapshot)

    sorted_pids = sorted({line["product_id"] for line in merged_lines})
    locked_products = {
        p.product_id: p
        for p in db.scalars(
            select(Product).where(Product.product_id.in_(sorted_pids)).order_by(Product.product_id.asc()).with_for_update()
        ).all()
    }
    locked_inventories = _lock_inventories_asc(db, sorted_pids)

    shortages: List[Dict[str, Any]] = []
    for line in merged_lines:
        prod = locked_products[line["product_id"]]
        inv = locked_inventories.get(prod.product_id)
        avail = int(inv.quantity_available) if inv is not None else 0
        req_qty = int(line["quantity"])
        if avail < req_qty:
            shortages.append(
                {
                    "product_id": prod.product_id,
                    "productId": prod.product_id,
                    "name": prod.name,
                    "size": line["size"],
                    "requested": req_qty,
                    "available": avail,
                }
            )

    if shortages:
        first = shortages[0]
        raise AppError(
            "insufficient_stock",
            f"Not enough stock for '{first['name']}' ({first['product_id']}): requested {first['requested']}, available {first['available']}.",
            409,
            details={"shortages": shortages},
        )

    fin = calculate_order_financials(
        db,
        merged_lines,
        coupon_code=req.coupon_code,
        destination_state=dest_state,
        destination_pin=dest_pin,
    )

    now = datetime.now(timezone.utc)
    settings = get_settings()
    hold_seconds = int(req.hold_seconds if req.hold_seconds is not None else settings.hold_seconds)
    total_paise = int(round(float(fin["grand_total_inr"]) * 100))
    locker_number = random.randint(1, 24)
    pickup_code = f"{random.randint(0, 9999):04d}"

    order_id = next_entity_id(db, Order, Order.order_id, "order", start_seq=1001)
    order = Order(
        order_id=order_id,
        customer_id=customer_id,
        shipping_address_id=address.address_id if address else None,
        status="pending" if req.hold_only else "confirmed",
        subtotal_mrp_inr=fin["subtotal_mrp_inr"],
        discount_inr=fin["discount_inr"],
        taxable_value_inr=fin["taxable_value_inr"],
        cgst_inr=fin["cgst_inr"],
        sgst_inr=fin["sgst_inr"],
        igst_inr=fin["igst_inr"],
        total_gst_inr=fin["total_gst_inr"],
        shipping_fee_inr=fin["shipping_fee_inr"],
        grand_total_inr=fin["grand_total_inr"],
        total_paise=total_paise,
        currency="INR",
        coupon_code=req.coupon_code.strip().upper() if req.coupon_code else None,
        signature_required=fin["signature_required"],
        hold_expires_at=(now + timedelta(seconds=hold_seconds)) if req.hold_only else None,
        paid_at=None if req.hold_only else now,
        paid_amount_paise=None if req.hold_only else total_paise,
        locker_number=locker_number,
        pickup_code=pickup_code,
    )
    db.add(order)

    for cl in fin["items"]:
        db.add(
            OrderItem(
                order_id=order_id,
                product_id=cl["product_id"],
                sku=cl["sku"],
                product_name=cl["product_name"],
                size=cl["size"],
                quantity=cl["quantity"],
                unit_mrp_inr=cl["unit_mrp_inr"],
                unit_discount_inr=cl["unit_discount_inr"],
                unit_sale_value_inr=cl["unit_sale_value_inr"],
                gst_rate_pct=cl["gst_rate_pct"],
                gst_amount_inr=cl["gst_amount_inr"],
                final_sale=cl["final_sale"],
            )
        )
        inv = locked_inventories[cl["product_id"]]
        qty = int(cl["quantity"])
        inv.quantity_available -= qty
        if req.hold_only:
            inv.quantity_reserved = int(inv.quantity_reserved or 0) + qty

    if req.coupon_code and fin["discount_inr"] > Decimal("0.00"):
        coupon = db.scalar(select(Coupon).where(Coupon.code == req.coupon_code.strip().upper()))
        if coupon:
            coupon.uses_remaining -= 1
            db.add(
                CouponUsage(
                    coupon_id=coupon.coupon_id,
                    order_id=order_id,
                    customer_id=customer_id,
                    discount_applied_inr=fin["discount_inr"],
                )
            )

    payment_id = None
    invoice_id = None
    if not req.hold_only:
        payment_id = next_entity_id(db, Payment, Payment.payment_id, "payment", start_seq=1001)
        txn_id = f"TXN-{uuid.uuid4().hex[:10].upper()}"
        payment = Payment(
            payment_id=payment_id,
            order_id=order_id,
            method=method,
            status="confirmed",
            amount_inr=fin["grand_total_inr"],
            amount_paise=total_paise,
            outcome="paid",
            transaction_id=txn_id,
            gateway_response={"provider": "mock", "status": "captured", "transaction_id": txn_id},
        )
        db.add(payment)
        inv_row = _ensure_invoice_for_order(db, order, dest_state=dest_state)
        invoice_id = inv_row.invoice_id

    for c in cart_rows_to_clear:
        db.delete(c)

    record_audit(
        db,
        actor,
        "order",
        order_id,
        "create_order_hold" if req.hold_only else "create_order",
        {
            "grand_total_inr": float(fin["grand_total_inr"]),
            "total_paise": total_paise,
            "hold_only": req.hold_only,
            "payment_id": payment_id,
            "invoice_id": invoice_id,
        },
        "order_hold_reserved" if req.hold_only else "order_created_and_paid",
    )
    db.flush()
    response_data = serialize_order(db, order)
    if effective_idem_key:
        save_idempotent_result(db, effective_idem_key, actor.actor_id, "order", order_id, "create_order", response_data)
    db.commit()
    return response_data


def get_order_details(db: Session, actor: ActorContext, order_id: str) -> Dict[str, Any]:
    order = db.scalar(select(Order).where(Order.order_id == order_id.strip().upper()))
    if order is None:
        raise AppError("order_not_found", f"Order '{order_id}' was not found.", 404)
    _assert_order_access(actor, order)
    expire_order_if_due(db, order)
    return serialize_order(db, order)


def list_customer_orders(
    db: Session,
    actor: ActorContext,
    customer_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    target_cust = customer_id or actor.on_behalf_of or (actor.actor_id if actor.actor_type == "customer" else None)
    if actor.actor_type == "customer" and target_cust != actor.actor_id:
        raise AppError("forbidden", "Cannot list another customer's orders.", 403)

    stmt = select(Order).order_by(Order.order_date.desc())
    if target_cust:
        stmt = stmt.where(Order.customer_id == target_cust)

    orders = db.scalars(stmt).all()
    for o in orders:
        expire_order_if_due(db, o)
    return [serialize_order(db, o) for o in orders]


def cancel_order(
    db: Session,
    actor: ActorContext,
    order_id: str,
    req: OrderCancelRequest,
) -> Dict[str, Any]:
    cached = get_idempotent_result(db, req.request_key)
    if cached is not None:
        return dict(cached.response_snapshot)

    order = db.scalar(select(Order).where(Order.order_id == order_id.strip().upper()).with_for_update())
    if order is None:
        raise AppError("order_not_found", f"Order '{order_id}' was not found.", 404)
    _assert_order_access(actor, order)

    expire_order_if_due(db, order)

    if order.status == "cancelled":
        return serialize_order(db, order)

    if order.status == "expired":
        raise AppError(
            "not_cancellable",
            f"Order '{order.order_id}' hold has expired and cannot be cancelled.",
            409,
            details={"status": order.status},
        )

    if order.status in ("shipped", "delivered", "returned", "refunded", "picked_up", "needs_review"):
        raise AppError(
            "cancel_not_eligible",
            f"Order '{order.order_id}' is in '{order.status}' status and cannot be cancelled pre-shipment (per POL-CAN-01).",
            422,
        )

    now = datetime.now(timezone.utc)
    was_pending_hold = order.status == "pending"

    if was_pending_hold:
        _release_reserved_stock_for_order(db, order)
        order.status = "cancelled"
        order.cancelled_at = now
        record_audit(
            db,
            actor,
            "order",
            order.order_id,
            "cancel_order_hold",
            {"released_hold": True},
            req.reason,
        )
        db.flush()
        result = serialize_order(db, order)
        save_idempotent_result(db, req.request_key, actor.actor_id, "order", order.order_id, "cancel_order", result)
        db.commit()
        return result

    order.status = "cancelled"
    order.cancelled_at = now
    inv_map = _lock_inventories_asc(db, [item.product_id for item in order.items])
    for item in sorted(order.items, key=lambda x: (x.product_id, x.size)):
        inv = inv_map.get(item.product_id)
        if inv is not None:
            inv.quantity_available += item.quantity

    refund_id = next_entity_id(db, Refund, Refund.refund_id, "refund", start_seq=1001)
    refund = Refund(
        refund_id=refund_id,
        return_id=None,
        order_id=order.order_id,
        amount_inr=order.grand_total_inr,
        approval_tier=0,
        status="processed",
        reason=req.reason,
        approved_by=actor.actor_id,
        approved_date=now,
        processed_date=now,
        payment_refund_id=f"RFD-TXN-{uuid.uuid4().hex[:8].upper()}",
    )
    db.add(refund)

    record_audit(
        db,
        actor,
        "order",
        order.order_id,
        "cancel_order_tier_0",
        {"refund_id": refund_id, "amount_inr": float(order.grand_total_inr)},
        req.reason,
    )
    db.flush()
    result = serialize_order(db, order)
    result["refund_id"] = refund_id
    save_idempotent_result(db, req.request_key, actor.actor_id, "order", order.order_id, "cancel_order", result)
    db.commit()
    return result


def normalize_webhook_payload(body: Any) -> Dict[str, Any]:
    if not isinstance(body, dict):
        raise AppError("validation_error", "Webhook body must be a JSON object.", 400)
    event_id = body.get("eventId") if body.get("eventId") is not None else body.get("event_id")
    order_id = body.get("orderId") if body.get("orderId") is not None else body.get("order_id")
    amount_paise = body.get("amountPaise") if body.get("amountPaise") is not None else body.get("amount_paise")
    status = body.get("status")

    if not isinstance(event_id, str) or not event_id.strip() or len(event_id) > 120:
        raise AppError("validation_error", "event_id / eventId is required (max 120 chars).", 400)
    if not isinstance(order_id, str) or not order_id.strip() or len(order_id) > 64:
        raise AppError("validation_error", "order_id / orderId is required.", 400)
    if isinstance(amount_paise, bool) or not isinstance(amount_paise, int) or amount_paise < 0:
        raise AppError("validation_error", "amount_paise / amountPaise must be a non-negative integer.", 400)
    if not isinstance(status, str) or not status.strip() or len(status) > 40:
        raise AppError("validation_error", "status is required.", 400)

    return {
        "event_id": event_id.strip(),
        "order_id": order_id.strip().upper(),
        "amount_paise": int(amount_paise),
        "status": status.strip().lower(),
    }


def decide_webhook_outcome(
    order_status: str,
    order_total_paise: int,
    is_expired: bool,
    webhook_status: str,
    amount_paise: int,
) -> Dict[str, Any]:
    if webhook_status != "captured":
        return {"action": "ignore"}
    if order_status in ("paid", "confirmed", "picked_up", "needs_review"):
        return {"action": "ignore"}
    if order_status == "cancelled":
        return {"action": "flag_review", "reason": "payment_after_cancel", "refund": True, "release_hold": False}
    if amount_paise != order_total_paise:
        return {
            "action": "flag_review",
            "reason": "amount_mismatch",
            "refund": False,
            "release_hold": order_status == "pending" and not is_expired,
        }
    if order_status == "pending" and not is_expired:
        return {"action": "mark_paid"}
    return {"action": "attempt_late_recovery"}


def handle_payment_webhook(
    db: Session,
    actor: ActorContext,
    payload: Dict[str, Any],
    raw_body: str,
) -> Dict[str, Any]:
    norm = normalize_webhook_payload(payload)
    event_id = norm["event_id"]
    order_id = norm["order_id"]
    amount_paise = norm["amount_paise"]
    webhook_status = norm["status"]
    idem_key = f"webhook:{event_id}"

    existing_event = db.scalar(select(Payment).where(Payment.event_id == event_id))
    if existing_event is not None or get_idempotent_result(db, idem_key) is not None:
        return {"duplicate": True}

    order = db.scalar(select(Order).where(Order.order_id == order_id).with_for_update())
    if order is None:
        raise AppError("order_not_found", f"Order '{order_id}' not found.", 404)

    inv_map = _lock_inventories_asc(db, [item.product_id for item in order.items])

    now = datetime.now(timezone.utc)
    hold_exp = _ensure_utc(order.hold_expires_at)
    order_total_paise = order.total_paise if order.total_paise else int(round(float(order.grand_total_inr) * 100))
    order.total_paise = order_total_paise

    is_expired = order.status == "expired" or (hold_exp is not None and hold_exp <= now)
    if order.status == "pending" and is_expired:
        for item in sorted(order.items, key=lambda x: (x.product_id, x.size)):
            inv = inv_map.get(item.product_id)
            if inv is not None:
                inv.quantity_available += int(item.quantity)
                inv.quantity_reserved = max(0, int(inv.quantity_reserved or 0) - int(item.quantity))
        order.status = "expired"

    decision = decide_webhook_outcome(
        order_status=order.status,
        order_total_paise=order_total_paise,
        is_expired=is_expired,
        webhook_status=webhook_status,
        amount_paise=amount_paise,
    )

    action = decision["action"]
    outcome = "ignored"

    if action == "ignore":
        outcome = "ignored"
    elif action == "flag_review":
        if decision.get("release_hold"):
            for item in sorted(order.items, key=lambda x: (x.product_id, x.size)):
                inv = inv_map.get(item.product_id)
                if inv is not None:
                    inv.quantity_available += int(item.quantity)
                    inv.quantity_reserved = max(0, int(inv.quantity_reserved or 0) - int(item.quantity))
        order.status = "needs_review"
        order.review_reason = decision["reason"]
        order.refund_flag = bool(decision["refund"])
        outcome = "needs_review"
    elif action == "mark_paid":
        for item in sorted(order.items, key=lambda x: (x.product_id, x.size)):
            inv = inv_map.get(item.product_id)
            if inv is not None:
                inv.quantity_reserved = max(0, int(inv.quantity_reserved or 0) - int(item.quantity))
        order.status = "paid"
        order.paid_at = now
        order.paid_amount_paise = amount_paise
        _ensure_invoice_for_order(db, order)
        outcome = "paid"
    elif action == "attempt_late_recovery":
        can_fulfill_late = all(
            inv_map.get(item.product_id) is not None
            and int(inv_map[item.product_id].quantity_available) >= int(item.quantity)
            for item in order.items
        )
        if can_fulfill_late:
            for item in sorted(order.items, key=lambda x: (x.product_id, x.size)):
                inv = inv_map[item.product_id]
                inv.quantity_available -= int(item.quantity)
            order.status = "paid"
            order.paid_at = now
            order.paid_amount_paise = amount_paise
            _ensure_invoice_for_order(db, order)
            outcome = "paid_late"
        else:
            order.status = "needs_review"
            order.review_reason = "late_payment_stock_gone"
            order.refund_flag = True
            outcome = "needs_review"

    pay_id = next_entity_id(db, Payment, Payment.payment_id, "payment", start_seq=1001)
    pay_row = Payment(
        payment_id=pay_id,
        order_id=order.order_id,
        method="webhook",
        status="confirmed" if outcome in ("paid", "paid_late") else outcome,
        amount_inr=(Decimal(amount_paise) / Decimal("100")).quantize(Decimal("0.01")),
        amount_paise=amount_paise,
        event_id=event_id,
        outcome=outcome,
        raw_body=raw_body,
        transaction_id=f"EVT-{event_id[:64]}",
        gateway_response={"event_id": event_id, "webhook_status": webhook_status, "outcome": outcome},
    )
    db.add(pay_row)
    record_audit(
        db,
        actor,
        "payment",
        pay_id,
        f"webhook_{outcome}",
        {"event_id": event_id, "order_id": order.order_id, "amount_paise": amount_paise, "outcome": outcome},
        order.review_reason or outcome,
    )

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"duplicate": True}

    order_snapshot = serialize_order(db, order)
    result = {"duplicate": False, "outcome": outcome, "order": order_snapshot}
    save_idempotent_result(db, idem_key, actor.actor_id, "payment", pay_id, "payment_webhook", result)
    db.commit()
    return result


def handle_demo_payment(db: Session, actor: ActorContext, order_id: str) -> Dict[str, Any]:
    order = db.scalar(select(Order).where(Order.order_id == order_id.strip().upper()))
    if order is None:
        raise AppError("order_not_found", f"Order '{order_id}' not found.", 404)
    total_paise = order.total_paise if order.total_paise else int(round(float(order.grand_total_inr) * 100))
    payload = {
        "eventId": f"demo_{uuid.uuid4()}",
        "orderId": order.order_id,
        "amountPaise": total_paise,
        "status": "captured",
    }
    return handle_payment_webhook(db, actor, payload, json.dumps(payload))


def claim_order_pickup(db: Session, actor: ActorContext, order_id: str) -> Dict[str, Any]:
    order = db.scalar(select(Order).where(Order.order_id == order_id.strip().upper()).with_for_update())
    if order is None:
        raise AppError("order_not_found", f"Order '{order_id}' not found.", 404)
    _assert_order_access(actor, order)

    if order.status == "picked_up":
        raise AppError(
            "already_claimed",
            "Order has already been picked up.",
            409,
            details={"picked_up_at": _ensure_utc(order.picked_up_at).isoformat() if order.picked_up_at else None},
        )

    if order.status not in ("paid", "confirmed"):
        raise AppError(
            "not_claimable",
            f"Order in status '{order.status}' cannot be claimed for pickup.",
            409,
            details={"status": order.status},
        )

    now = datetime.now(timezone.utc)
    order.status = "picked_up"
    order.picked_up_at = now
    record_audit(
        db,
        actor,
        "order",
        order.order_id,
        "claim_pickup",
        {"locker_number": order.locker_number, "picked_up_at": now.isoformat()},
        "boutique_locker_pickup_claimed",
    )
    db.commit()
    return serialize_order(db, order)


def initiate_payment(db: Session, actor: ActorContext, req: PaymentInitiateRequest) -> Dict[str, Any]:
    order = db.scalar(select(Order).where(Order.order_id == req.order_id.strip().upper()))
    if order is None:
        raise AppError("order_not_found", f"Order '{req.order_id}' not found.", 404)

    payment = db.scalar(select(Payment).where(Payment.order_id == order.order_id).order_by(Payment.created_at.desc()))
    if payment and payment.status == "confirmed":
        return {
            "payment_id": payment.payment_id,
            "order_id": order.order_id,
            "status": payment.status,
            "amount_inr": float(payment.amount_inr),
            "transaction_id": payment.transaction_id,
        }

    pay_id = next_entity_id(db, Payment, Payment.payment_id, "payment", start_seq=1001)
    txn_id = f"TXN-{uuid.uuid4().hex[:10].upper()}"
    new_pay = Payment(
        payment_id=pay_id,
        order_id=order.order_id,
        method=req.method.strip().lower(),
        status="confirmed",
        amount_inr=req.amount_inr or order.grand_total_inr,
        transaction_id=txn_id,
        gateway_response={"provider": "mock", "status": "captured"},
    )
    order.status = "confirmed"
    db.add(new_pay)
    record_audit(db, actor, "payment", pay_id, "payment_confirmed", {"order_id": order.order_id}, "payment_initiated")
    db.commit()
    return {
        "payment_id": pay_id,
        "order_id": order.order_id,
        "status": "confirmed",
        "amount_inr": float(new_pay.amount_inr),
        "transaction_id": txn_id,
    }


def schedule_shipment(db: Session, actor: ActorContext, req: ShipmentScheduleRequest) -> Dict[str, Any]:
    order = db.scalar(select(Order).where(Order.order_id == req.order_id.strip().upper()))
    if order is None:
        raise AppError("order_not_found", f"Order '{req.order_id}' not found.", 404)

    existing = db.scalar(select(Shipment).where(Shipment.order_id == order.order_id))
    if existing:
        return {
            "shipment_id": existing.shipment_id,
            "order_id": existing.order_id,
            "carrier": existing.carrier,
            "tracking_number": existing.tracking_number,
            "status": existing.status,
            "label_storage_key": existing.label_storage_key,
        }

    shp_id = next_entity_id(db, Shipment, Shipment.shipment_id, "shipment", start_seq=1001)
    awb = f"AWB-NA-{shp_id.split('-')[1]}"
    now = datetime.now(timezone.utc)
    object_store = LocalObjectStore()

    label_key = object_store.put_json(
        "labels",
        shp_id,
        f"{shp_id}.json",
        {"shipment_id": shp_id, "order_id": order.order_id, "carrier": req.carrier, "awb": awb},
    )
    object_store.put_json(
        "packing",
        order.order_id,
        f"{order.order_id}.json",
        {
            "order_id": order.order_id,
            "shipment_id": shp_id,
            "items": [{"sku": i.sku, "size": i.size, "qty": i.quantity} for i in order.items],
        },
    )

    shp = Shipment(
        shipment_id=shp_id,
        order_id=order.order_id,
        carrier=req.carrier,
        tracking_number=awb,
        status="shipped",
        scheduled_pickup=now + timedelta(hours=4),
        shipped_date=now,
        label_storage_key=label_key,
    )
    order.status = "shipped"
    db.add(shp)
    record_audit(db, actor, "shipment", shp_id, "shipment_scheduled", {"order_id": order.order_id, "awb": awb}, "fulfillment_dispatch")
    db.commit()
    return {
        "shipment_id": shp_id,
        "order_id": order.order_id,
        "carrier": shp.carrier,
        "tracking_number": shp.tracking_number,
        "status": shp.status,
        "label_storage_key": shp.label_storage_key,
    }


def get_orders_analytics(db: Session) -> Dict[str, Any]:
    orders = db.scalars(select(Order).where(Order.status != "cancelled")).all()
    total_revenue = sum((o.grand_total_inr for o in orders), Decimal("0.00"))
    item_rows = db.execute(
        select(
            OrderItem.product_id,
            OrderItem.product_name,
            func.sum(OrderItem.quantity).label("units_sold"),
            func.sum(OrderItem.unit_sale_value_inr * OrderItem.quantity).label("revenue_inr"),
        )
        .group_by(OrderItem.product_id, OrderItem.product_name)
        .order_by(func.sum(OrderItem.quantity).desc())
    ).all()

    return {
        "total_orders": len(orders),
        "total_revenue_inr": float(total_revenue),
        "top_products": [
            {
                "product_id": r.product_id,
                "product_name": r.product_name,
                "units_sold": int(r.units_sold or 0),
                "revenue_inr": float(r.revenue_inr or 0),
            }
            for r in item_rows
        ],
    }
