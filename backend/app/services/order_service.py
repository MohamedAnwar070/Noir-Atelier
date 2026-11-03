from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import ActorContext
from ..models import (
    Cart,
    Coupon,
    CouponUsage,
    Customer,
    CustomerAddress,
    Invoice,
    Order,
    OrderItem,
    Payment,
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
from .tax_service import calculate_order_financials


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
        "currency": order.currency,
        "payment_status": payment.status if payment else "pending",
        "payment_id": payment.payment_id if payment else None,
        "invoice_id": invoice.invoice_id if invoice else None,
        "tracking_number": shipment.tracking_number if shipment else None,
        "signature_required": order.signature_required,
    }


def calculate_order_preview(db: Session, req: OrderCalculateRequest) -> Dict[str, Any]:
    raw_lines: List[Dict[str, Any]] = []
    for item in req.items:
        prod = get_product_by_id_or_sku(db, item.product_id)
        raw_lines.append(
            {
                "product_id": prod.product_id,
                "sku": prod.sku,
                "product_name": prod.name,
                "size": item.size,
                "quantity": item.quantity,
                "unit_mrp_inr": prod.mrp_inr,
                "final_sale": prod.final_sale,
            }
        )
    return calculate_order_financials(
        db,
        raw_lines,
        coupon_code=req.coupon_code,
        destination_state=req.destination_state,
        destination_pin=req.destination_pin,
    )


def create_order(db: Session, actor: ActorContext, req: OrderCreateRequest) -> Dict[str, Any]:
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

    if req.items:
        for line in req.items:
            prod = get_product_by_id_or_sku(db, line.product_id)
            raw_lines.append(
                {
                    "product_id": prod.product_id,
                    "sku": prod.sku,
                    "product_name": prod.name,
                    "size": line.size,
                    "quantity": line.quantity,
                    "unit_mrp_inr": prod.mrp_inr,
                    "final_sale": prod.final_sale,
                }
            )
    else:
        sess_id = req.session_id or f"sess-{customer_id}"
        cart_rows_to_clear = list(
            db.scalars(select(Cart).where((Cart.session_id == sess_id) | (Cart.customer_id == customer_id))).all()
        )
        if not cart_rows_to_clear:
            raise AppError("empty_cart", "Cannot create order: no items provided and cart is empty.", 422)
        for c in cart_rows_to_clear:
            prod = get_product_by_id_or_sku(db, c.product_id)
            raw_lines.append(
                {
                    "product_id": prod.product_id,
                    "sku": prod.sku,
                    "product_name": prod.name,
                    "size": c.size,
                    "quantity": c.quantity,
                    "unit_mrp_inr": prod.mrp_inr,
                    "final_sale": prod.final_sale,
                }
            )

    for line in raw_lines:
        prod = get_product_by_id_or_sku(db, line["product_id"])
        inv = prod.inventory
        if inv is None or inv.quantity_available < int(line["quantity"]):
            raise AppError(
                "insufficient_stock",
                f"Insufficient stock for '{prod.name}' ({prod.product_id}).",
                422,
            )

    fin = calculate_order_financials(
        db,
        raw_lines,
        coupon_code=req.coupon_code,
        destination_state=dest_state,
        destination_pin=dest_pin,
    )

    cfg = get_business_config_map(db)
    order_id = next_entity_id(db, Order, Order.order_id, "order", start_seq=1001)
    order = Order(
        order_id=order_id,
        customer_id=customer_id,
        shipping_address_id=address.address_id if address else None,
        status="confirmed",
        subtotal_mrp_inr=fin["subtotal_mrp_inr"],
        discount_inr=fin["discount_inr"],
        taxable_value_inr=fin["taxable_value_inr"],
        cgst_inr=fin["cgst_inr"],
        sgst_inr=fin["sgst_inr"],
        igst_inr=fin["igst_inr"],
        total_gst_inr=fin["total_gst_inr"],
        shipping_fee_inr=fin["shipping_fee_inr"],
        grand_total_inr=fin["grand_total_inr"],
        currency="INR",
        coupon_code=req.coupon_code.strip().upper() if req.coupon_code else None,
        signature_required=fin["signature_required"],
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
        prod = get_product_by_id_or_sku(db, cl["product_id"])
        assert prod.inventory is not None
        prod.inventory.quantity_available -= int(cl["quantity"])

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

    payment_id = next_entity_id(db, Payment, Payment.payment_id, "payment", start_seq=1001)
    txn_id = f"TXN-{uuid.uuid4().hex[:10].upper()}"
    payment = Payment(
        payment_id=payment_id,
        order_id=order_id,
        method=method,
        status="confirmed",
        amount_inr=fin["grand_total_inr"],
        transaction_id=txn_id,
        gateway_response={"provider": "mock", "status": "captured", "transaction_id": txn_id},
    )
    db.add(payment)

    invoice_id = next_entity_id(db, Invoice, Invoice.invoice_id, "invoice", start_seq=1001)
    month_folder = datetime.now(timezone.utc).strftime("%Y-%m")
    object_store = LocalObjectStore()
    invoice_payload = {
        "invoice_id": invoice_id,
        "order_id": order_id,
        "customer_id": customer_id,
        "seller_gstin": fin["seller_gstin"],
        "place_of_supply_state": dest_state,
        "is_intra_state": fin["is_intra_state"],
        "subtotal_mrp_inr": str(fin["subtotal_mrp_inr"]),
        "discount_inr": str(fin["discount_inr"]),
        "taxable_value_inr": str(fin["taxable_value_inr"]),
        "cgst_inr": str(fin["cgst_inr"]),
        "sgst_inr": str(fin["sgst_inr"]),
        "igst_inr": str(fin["igst_inr"]),
        "shipping_fee_inr": str(fin["shipping_fee_inr"]),
        "grand_total_inr": str(fin["grand_total_inr"]),
    }
    storage_key = object_store.put_json("invoices", month_folder, f"{invoice_id}.json", invoice_payload)

    db.add(
        Invoice(
            invoice_id=invoice_id,
            order_id=order_id,
            seller_gstin=fin["seller_gstin"],
            place_of_supply_state=dest_state,
            is_intra_state=fin["is_intra_state"],
            taxable_value_inr=fin["taxable_value_inr"],
            cgst_inr=fin["cgst_inr"],
            sgst_inr=fin["sgst_inr"],
            igst_inr=fin["igst_inr"],
            total_inr=fin["grand_total_inr"],
            storage_key=storage_key,
        )
    )

    for c in cart_rows_to_clear:
        db.delete(c)

    record_audit(
        db,
        actor,
        "order",
        order_id,
        "create_order",
        {"grand_total_inr": float(fin["grand_total_inr"]), "payment_id": payment_id, "invoice_id": invoice_id},
        "order_created_and_paid",
    )
    db.flush()
    response_data = serialize_order(db, order)
    save_idempotent_result(db, req.request_key, actor.actor_id, "order", order_id, "create_order", response_data)
    db.commit()
    return response_data


def get_order_details(db: Session, actor: ActorContext, order_id: str) -> Dict[str, Any]:
    order = db.scalar(select(Order).where(Order.order_id == order_id.strip().upper()))
    if order is None:
        raise AppError("order_not_found", f"Order '{order_id}' was not found.", 404)
    _assert_order_access(actor, order)
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

    order = db.scalar(select(Order).where(Order.order_id == order_id.strip().upper()))
    if order is None:
        raise AppError("order_not_found", f"Order '{order_id}' was not found.", 404)
    _assert_order_access(actor, order)

    if order.status in ("shipped", "delivered", "returned", "refunded"):
        raise AppError(
            "cancel_not_eligible",
            f"Order '{order.order_id}' is in '{order.status}' status and cannot be cancelled pre-shipment (per POL-CAN-01).",
            422,
        )
    if order.status == "cancelled":
        return serialize_order(db, order)

    order.status = "cancelled"
    for item in order.items:
        prod = get_product_by_id_or_sku(db, item.product_id)
        if prod.inventory:
            prod.inventory.quantity_available += item.quantity

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
        approved_date=datetime.now(timezone.utc),
        processed_date=datetime.now(timezone.utc),
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
