"""Live catalogue attributes with product counts — what the stylist may filter by right now.

Consumed by the conversational stylist (GET /api/catalog/attributes):
  * the stylist maps a shopper's words onto these values only ("calm colours"
    → palette "muted" if it exists and has products);
  * a new colour, fabric or occasion appears here on the next request, with no
    code change;
  * the payload is deterministic (sorted, stable keys) and carries a content
    ``version`` hash, so it can sit inside a prompt-cached system prompt and
    callers can detect vocabulary changes cheaply.

Counts include active products only. Values with zero products are omitted:
offering them to a shopper would promise something we cannot show.
"""

import hashlib
import json
from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Category,
    Color,
    ColorPalette,
    Department,
    Material,
    Occasion,
    Palette,
    Product,
    ProductMaterial,
    ProductOccasion,
    ProductVariant,
)
from .config_service import get_business_config_map

_active = Product.is_active.is_(True)


def _departments(db: Session) -> List[Dict[str, Any]]:
    rows = db.execute(
        select(Department.code, Department.name, func.count(Product.product_id))
        .join(Product, Product.department == Department.code)
        .where(_active, Department.is_active.is_(True))
        .group_by(Department.code, Department.name, Department.display_order)
        .order_by(Department.display_order, Department.code)
    ).all()
    return [{"code": c, "name": n, "product_count": k} for c, n, k in rows]


def _product_types(db: Session) -> List[Dict[str, Any]]:
    parent = select(Category.category_id, Category.slug).subquery()
    rows = db.execute(
        select(Category.slug, Category.name, parent.c.slug, func.count(Product.product_id))
        .join(Product, Product.category_id == Category.category_id)
        .outerjoin(parent, parent.c.category_id == Category.parent_id)
        .where(_active, Category.is_active.is_(True))
        .group_by(Category.slug, Category.name, parent.c.slug, Category.display_order)
        .order_by(Category.display_order, Category.slug)
    ).all()
    return [{"slug": s, "name": n, "parent": p, "product_count": k} for s, n, p, k in rows]


def _colors(db: Session) -> List[Dict[str, Any]]:
    rows = db.execute(
        select(Color.family, func.count(Product.product_id), func.min(Color.hex_code))
        .join(Product, Product.color_id == Color.color_id)
        .where(_active)
        .group_by(Color.family)
        .order_by(Color.family)
    ).all()
    return [{"family": f, "product_count": k, "hex_code": h} for f, k, h in rows]


def _palettes(db: Session) -> List[Dict[str, Any]]:
    rows = db.execute(
        select(Palette.code, Palette.name, func.count(func.distinct(Product.product_id)))
        .join(ColorPalette, ColorPalette.palette_code == Palette.code)
        .join(Product, Product.color_id == ColorPalette.color_id)
        .where(_active)
        .group_by(Palette.code, Palette.name, Palette.display_order)
        .order_by(Palette.display_order, Palette.code)
    ).all()
    return [{"code": c, "name": n, "product_count": k} for c, n, k in rows]


def _materials(db: Session) -> List[Dict[str, Any]]:
    rows = db.execute(
        select(Material.family, func.count(func.distinct(Product.product_id)))
        .join(ProductMaterial, ProductMaterial.material_id == Material.material_id)
        .join(Product, Product.product_id == ProductMaterial.product_id)
        .where(_active)
        .group_by(Material.family)
        .order_by(Material.family)
    ).all()
    return [{"family": f, "product_count": k} for f, k in rows]


def _occasions(db: Session) -> List[Dict[str, Any]]:
    rows = db.execute(
        select(Occasion.code, Occasion.name, func.count(Product.product_id))
        .join(ProductOccasion, ProductOccasion.occasion_code == Occasion.code)
        .join(Product, Product.product_id == ProductOccasion.product_id)
        .where(_active, Occasion.is_active.is_(True))
        .group_by(Occasion.code, Occasion.name, Occasion.display_order)
        .order_by(Occasion.display_order, Occasion.code)
    ).all()
    return [{"code": c, "name": n, "product_count": k} for c, n, k in rows]


def _sizes_and_prices(db: Session) -> Dict[str, Any]:
    live = (ProductVariant.is_active.is_(True), _active)
    sizes = db.execute(
        select(ProductVariant.size, func.count(func.distinct(ProductVariant.product_id)), func.min(ProductVariant.position))
        .join(Product, Product.product_id == ProductVariant.product_id)
        .where(*live)
        .group_by(ProductVariant.size)
        .order_by(func.min(ProductVariant.position), ProductVariant.size)
    ).all()
    low, high = db.execute(
        select(func.min(ProductVariant.mrp_inr), func.max(ProductVariant.mrp_inr))
        .join(Product, Product.product_id == ProductVariant.product_id)
        .where(*live)
    ).one()
    return {
        "sizes": [{"size": s, "product_count": k} for s, k, _ in sizes],
        "price_range_inr": {"min": float(low) if low is not None else None, "max": float(high) if high is not None else None},
    }


def _pricing_rules(db: Session) -> Dict[str, Any]:
    cfg = get_business_config_map(db)
    tax, shipping = cfg.get("tax", {}), cfg.get("shipping", {})
    return {
        "currency": "INR",
        "prices_include_gst": bool(tax.get("mrp_inclusive", True)),
        "gst_slab_threshold_inr": tax.get("garment_slab_threshold_inr"),
        "gst_rate_upto_threshold": tax.get("rate_upto_threshold"),
        "gst_rate_above_threshold": tax.get("rate_above_threshold"),
        "free_shipping_threshold_inr": shipping.get("free_shipping_threshold_inr"),
        "default_shipping_fee_inr": shipping.get("default_shipping_fee_inr"),
    }


def get_catalog_attributes(db: Session) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "departments": _departments(db),
        "product_types": _product_types(db),
        "colors": _colors(db),
        "palettes": _palettes(db),
        "materials": _materials(db),
        "occasions": _occasions(db),
        **_sizes_and_prices(db),
        "pricing": _pricing_rules(db),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    payload["version"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return payload
