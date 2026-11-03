from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Coupon, ShippingZone
from ..utils.exceptions import AppError
from .config_service import get_business_config_map

TWO_PLACES = Decimal("0.01")


def _q(val: Decimal) -> Decimal:
    return val.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def resolve_garment_gst_rate(unit_net_sale_inr: Decimal, tax_cfg: Dict[str, Any]) -> Decimal:
    threshold = Decimal(str(tax_cfg.get("garment_slab_threshold_inr", 2500)))
    low_rate = Decimal(str(tax_cfg.get("rate_upto_threshold", "0.05")))
    high_rate = Decimal(str(tax_cfg.get("rate_above_threshold", "0.18")))
    if unit_net_sale_inr <= threshold:
        return low_rate
    return high_rate


def validate_and_compute_coupon(
    db: Session,
    coupon_code: Optional[str],
    subtotal_mrp_inr: Decimal,
) -> Decimal:
    if not coupon_code or not coupon_code.strip():
        return Decimal("0.00")

    code = coupon_code.strip().upper()
    coupon = db.scalar(select(Coupon).where(Coupon.code == code, Coupon.is_active.is_(True)))
    if coupon is None:
        raise AppError("invalid_coupon", f"Coupon code '{code}' is invalid or inactive.", 400)
    if coupon.uses_remaining <= 0:
        raise AppError("coupon_exhausted", f"Coupon code '{code}' has no remaining uses.", 400)
    if subtotal_mrp_inr < coupon.min_order_value_inr:
        raise AppError(
            "coupon_min_order_not_met",
            f"Coupon '{code}' requires a minimum order of INR {coupon.min_order_value_inr}.",
            400,
        )

    if coupon.discount_type == "percent":
        raw_discount = _q(subtotal_mrp_inr * (coupon.discount_value / Decimal("100")))
    else:
        raw_discount = _q(coupon.discount_value)

    return min(raw_discount, _q(coupon.max_discount_inr), subtotal_mrp_inr)


def resolve_shipping_fee(
    db: Session,
    post_discount_total_inr: Decimal,
    destination_pin: str,
    shipping_cfg: Dict[str, Any],
) -> Decimal:
    free_threshold = Decimal(str(shipping_cfg.get("free_shipping_threshold_inr", 1999)))
    if post_discount_total_inr >= free_threshold or post_discount_total_inr <= Decimal("0.00"):
        return Decimal("0.00")

    pin_prefix = (destination_pin or "600001").strip()[:3]
    zones = db.scalars(select(ShippingZone).where(ShippingZone.is_active.is_(True))).all()
    for z in zones:
        if pin_prefix in (z.pin_prefixes or []):
            return _q(z.base_fee_inr)

    return _q(Decimal(str(shipping_cfg.get("default_shipping_fee_inr", 99))))


def calculate_order_financials(
    db: Session,
    line_items: List[Dict[str, Any]],
    coupon_code: Optional[str] = None,
    destination_state: str = "Tamil Nadu",
    destination_pin: str = "600086",
) -> Dict[str, Any]:
    cfg = get_business_config_map(db)
    tax_cfg = cfg["tax"]
    shipping_cfg = cfg["shipping"]

    subtotal_mrp = sum((_q(Decimal(str(i["unit_mrp_inr"]))) * int(i["quantity"]) for i in line_items), Decimal("0.00"))
    total_discount = validate_and_compute_coupon(db, coupon_code, subtotal_mrp)

    origin_state = str(tax_cfg.get("origin_state", "Tamil Nadu")).strip().lower()
    is_intra_state = (destination_state or "Tamil Nadu").strip().lower() == origin_state

    computed_lines: List[Dict[str, Any]] = []
    total_taxable = Decimal("0.00")
    total_gst = Decimal("0.00")
    allocated_discount = Decimal("0.00")

    for idx, item in enumerate(line_items):
        qty = int(item["quantity"])
        unit_mrp = _q(Decimal(str(item["unit_mrp_inr"])))
        line_mrp = _q(unit_mrp * qty)

        if subtotal_mrp > Decimal("0.00") and total_discount > Decimal("0.00"):
            if idx == len(line_items) - 1:
                line_discount = _q(total_discount - allocated_discount)
            else:
                line_discount = _q(total_discount * (line_mrp / subtotal_mrp))
                allocated_discount += line_discount
        else:
            line_discount = Decimal("0.00")

        unit_discount = _q(line_discount / qty)
        unit_sale_val = _q(unit_mrp - unit_discount)
        line_sale_val = _q(line_mrp - line_discount)

        gst_rate = resolve_garment_gst_rate(unit_sale_val, tax_cfg)
        line_taxable = _q(line_sale_val / (Decimal("1.00") + gst_rate))
        line_gst = _q(line_sale_val - line_taxable)

        total_taxable += line_taxable
        total_gst += line_gst

        computed_lines.append(
            {
                "product_id": item["product_id"],
                "sku": item["sku"],
                "product_name": item["product_name"],
                "size": item.get("size", "M"),
                "quantity": qty,
                "unit_mrp_inr": unit_mrp,
                "unit_discount_inr": unit_discount,
                "unit_sale_value_inr": unit_sale_val,
                "line_sale_value_inr": line_sale_val,
                "gst_rate_pct": _q(gst_rate * Decimal("100")),
                "taxable_value_inr": line_taxable,
                "gst_amount_inr": line_gst,
                "final_sale": bool(item.get("final_sale", False)),
            }
        )

    post_discount_merchandise = _q(subtotal_mrp - total_discount)
    shipping_fee = resolve_shipping_fee(db, post_discount_merchandise, destination_pin, shipping_cfg)

    if is_intra_state:
        cgst = _q(total_gst / Decimal("2"))
        sgst = _q(total_gst - cgst)
        igst = Decimal("0.00")
    else:
        cgst = Decimal("0.00")
        sgst = Decimal("0.00")
        igst = total_gst

    grand_total = _q(post_discount_merchandise + shipping_fee)
    sig_threshold = Decimal(str(shipping_cfg.get("signature_required_above_inr", 5000)))

    return {
        "items": computed_lines,
        "subtotal_mrp_inr": subtotal_mrp,
        "discount_inr": total_discount,
        "taxable_value_inr": total_taxable,
        "cgst_inr": cgst,
        "sgst_inr": sgst,
        "igst_inr": igst,
        "total_gst_inr": total_gst,
        "shipping_fee_inr": shipping_fee,
        "grand_total_inr": grand_total,
        "free_shipping_applied": shipping_fee == Decimal("0.00") and post_discount_merchandise > Decimal("0.00"),
        "is_intra_state": is_intra_state,
        "seller_gstin": str(tax_cfg.get("mock_gstin", "33MOCKA1234Z1Z5")),
        "signature_required": grand_total > sig_threshold,
    }
