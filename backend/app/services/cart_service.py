from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ActorContext
from ..models import Cart
from ..schemas.cart_schema import CartAddRequest
from ..utils.exceptions import AppError
from .audit_service import next_entity_id, record_audit
from .product_service import get_product_by_id_or_sku
from .tax_service import calculate_order_financials, validate_and_compute_coupon
from .variant_service import build_line_item, get_variant, variant_size_for_sku


def _resolve_session_and_customer(
    actor: ActorContext,
    session_id: Optional[str],
    customer_id: Optional[str],
) -> tuple[str, Optional[str]]:
    resolved_cust = customer_id or actor.on_behalf_of or (actor.actor_id if actor.actor_type == "customer" else None)
    resolved_sess = session_id or (f"sess-{resolved_cust}" if resolved_cust else "sess-guest")
    return resolved_sess, resolved_cust


def add_item_to_cart(db: Session, actor: ActorContext, req: CartAddRequest) -> Dict[str, Any]:
    prod = get_product_by_id_or_sku(db, req.product_id)
    # A SKU identifies one size: if the caller passed a variant SKU, it decides the size.
    sku_size = variant_size_for_sku(prod, req.product_id)
    variant = get_variant(prod, sku_size or req.size)
    avail = variant.stock.quantity_available if variant.stock else 0
    if avail < req.quantity:
        raise AppError(
            "insufficient_stock",
            f"'{prod.name}' ({prod.product_id}) has only {avail} available in size {variant.size}.",
            422,
            details={"product_id": prod.product_id, "size": variant.size, "available": avail},
        )

    sess_id, cust_id = _resolve_session_and_customer(actor, req.session_id, req.customer_id)
    existing = db.scalar(
        select(Cart).where(
            Cart.session_id == sess_id,
            Cart.product_id == prod.product_id,
            Cart.size == variant.size,
        )
    )
    if existing:
        if avail < existing.quantity + req.quantity:
            raise AppError(
                "insufficient_stock",
                f"Cannot add {req.quantity} more of '{prod.name}' in size {variant.size}; available stock is {avail}.",
                422,
                details={"product_id": prod.product_id, "size": variant.size, "available": avail},
            )
        existing.quantity += req.quantity
        existing.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        cart_row = existing
    else:
        cid = next_entity_id(db, Cart, Cart.cart_id, "cart", start_seq=1)
        cart_row = Cart(
            cart_id=cid,
            customer_id=cust_id,
            session_id=sess_id,
            product_id=prod.product_id,
            sku=variant.sku,
            size=variant.size,
            quantity=req.quantity,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        db.add(cart_row)

    record_audit(
        db,
        actor,
        "cart",
        cart_row.cart_id,
        "add_to_cart",
        {"product_id": prod.product_id, "sku": variant.sku, "size": variant.size, "quantity": cart_row.quantity},
        "customer_or_agent_cart_add",
    )
    db.commit()
    return get_cart_summary(db, actor, session_id=sess_id, customer_id=cust_id)


def get_cart_summary(
    db: Session,
    actor: ActorContext,
    session_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    coupon_code: Optional[str] = None,
) -> Dict[str, Any]:
    sess_id, cust_id = _resolve_session_and_customer(actor, session_id, customer_id)
    stmt = select(Cart).where(Cart.session_id == sess_id)
    if cust_id:
        stmt = select(Cart).where((Cart.session_id == sess_id) | (Cart.customer_id == cust_id))

    rows = db.scalars(stmt.order_by(Cart.cart_id)).all()
    raw_lines: List[Dict[str, Any]] = []
    row_by_key: Dict[str, Cart] = {}
    unavailable: List[Dict[str, Any]] = []
    for r in rows:
        prod = get_product_by_id_or_sku(db, r.product_id)
        try:
            line = build_line_item(prod, r.size, r.quantity)
        except AppError as exc:
            # The size was retired after it was added: keep the cart usable and
            # report the line so the shopper can remove it.
            unavailable.append(
                {"cart_id": r.cart_id, "product_id": prod.product_id, "product_name": prod.name,
                 "size": r.size, "quantity": r.quantity, "reason": exc.message}
            )
            continue
        raw_lines.append(line)
        row_by_key[f"{prod.product_id}:{line['size']}"] = r

    financials = calculate_order_financials(db, raw_lines, coupon_code=coupon_code)
    items_dto = []
    for line in financials["items"]:
        matched_row = row_by_key.get(f"{line['product_id']}:{line['size']}")
        items_dto.append(
            {
                "cart_id": matched_row.cart_id if matched_row else "CRT-000",
                "product_id": line["product_id"],
                "sku": line["sku"],
                "product_name": line["product_name"],
                "size": line["size"],
                "quantity": line["quantity"],
                "unit_mrp_inr": line["unit_mrp_inr"],
                "line_mrp_inr": line["line_sale_value_inr"],
                "gst_rate_pct": line["gst_rate_pct"],
                "included_gst_inr": line["gst_amount_inr"],
            }
        )

    return {
        "session_id": sess_id,
        "customer_id": cust_id,
        "items": items_dto,
        "subtotal_mrp_inr": financials["subtotal_mrp_inr"],
        "discount_inr": financials["discount_inr"],
        "taxable_value_inr": financials["taxable_value_inr"],
        "cgst_inr": financials["cgst_inr"],
        "sgst_inr": financials["sgst_inr"],
        "igst_inr": financials["igst_inr"],
        "total_gst_inr": financials["total_gst_inr"],
        "shipping_fee_inr": financials["shipping_fee_inr"],
        "grand_total_inr": financials["grand_total_inr"],
        "free_shipping_applied": financials["free_shipping_applied"],
        "unavailable_items": unavailable,
    }


def remove_cart_item(db: Session, actor: ActorContext, item_id: str) -> Dict[str, Any]:
    row = db.scalar(select(Cart).where(Cart.cart_id == item_id.strip().upper()))
    if row is None:
        raise AppError("cart_item_not_found", f"Cart item '{item_id}' not found.", 404)
    sess_id, cust_id = row.session_id, row.customer_id
    db.delete(row)
    record_audit(db, actor, "cart", item_id, "remove_from_cart", {"cart_id": item_id}, "cart_item_removed")
    db.commit()
    return get_cart_summary(db, actor, session_id=sess_id, customer_id=cust_id)


def clear_cart(
    db: Session,
    actor: ActorContext,
    session_id: Optional[str] = None,
    customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    sess_id, cust_id = _resolve_session_and_customer(actor, session_id, customer_id)
    rows = db.scalars(select(Cart).where((Cart.session_id == sess_id) | (Cart.customer_id == cust_id))).all()
    for r in rows:
        db.delete(r)
    record_audit(db, actor, "cart", sess_id, "clear_cart", {"deleted_count": len(rows)}, "cart_cleared")
    db.commit()
    return {"status": "cleared", "session_id": sess_id, "deleted_items": len(rows)}


def validate_coupon_endpoint(db: Session, code: str, cart_total_inr: Decimal) -> Dict[str, Any]:
    discount = validate_and_compute_coupon(db, code, cart_total_inr)
    new_total = cart_total_inr - discount
    return {
        "valid": True,
        "code": code.strip().upper(),
        "discount_inr": discount,
        "new_total_inr": new_total,
        "message": f"Coupon '{code.strip().upper()}' applied: saved INR {discount}.",
    }
