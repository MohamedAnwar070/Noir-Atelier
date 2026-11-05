"""Product variants (sizes): SKU, pricing and size validation.

This module is the single source of truth for "what does size X of product Y
cost, and what is its SKU". Every pricing path — cart summary, order preview,
order creation and the AI agents (which call the same services) — builds its
line items through ``build_line_item`` so they can never disagree.

Invariants maintained here:
  * every sellable size is a ProductVariant row with its own SKU and price;
  * ``Product.mrp_inr`` is the lowest active variant price (the "from" price
    used for listing, sorting and filtering) and is never charged directly;
  * ``Product.sizes_available`` lists the active variant sizes in display order.
"""

from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional

from sqlalchemy.orm import Session

from ..models import Product, ProductVariant, VariantInventory
from ..utils.exceptions import AppError

# Display order for sizes; unknown sizes sort after these, alphabetically.
SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "2Y", "4Y", "6Y", "8Y", "10Y", "12Y", "14Y"]


def normalize_size(size: Optional[str]) -> str:
    return str(size or "").strip().upper()


def size_position(size: str) -> int:
    size = normalize_size(size)
    return SIZE_ORDER.index(size) if size in SIZE_ORDER else len(SIZE_ORDER)


def style_code(product: Product) -> str:
    """The product's size-independent code, used as the prefix of every variant SKU.

    Legacy products stored a size-specific SKU on the product (e.g. "PRD-002-CHR-L");
    that trailing size segment is stripped so all sizes share one style code.
    """
    sku = (product.sku or product.product_id).strip().upper()
    head, _, tail = sku.rpartition("-")
    if head and tail in {normalize_size(s) for s in (product.sizes_available or [])} | set(SIZE_ORDER):
        return head
    return sku


def variant_sku(style: str, size: str) -> str:
    return f"{style}-{normalize_size(size)}"


def active_variants(product: Product) -> List[ProductVariant]:
    return [v for v in product.variants if v.is_active]


def variant_size_for_sku(product: Product, identifier: Optional[str]) -> Optional[str]:
    """If ``identifier`` is one of the product's variant SKUs, return that variant's size."""
    wanted = str(identifier or "").strip().upper()
    return next((v.size for v in product.variants if v.sku == wanted), None)


def get_variant(product: Product, size: Optional[str]) -> ProductVariant:
    """Return the active variant for ``size`` or raise a 422 listing the sizes on offer."""
    wanted = normalize_size(size)
    for variant in active_variants(product):
        if variant.size == wanted:
            return variant
    available = [v.size for v in active_variants(product)]
    raise AppError(
        "size_unavailable",
        f"Size '{wanted or '?'}' is not available for '{product.name}'. Available sizes: {', '.join(available) or 'none'}.",
        422,
        details={"product_id": product.product_id, "size": wanted, "available_sizes": available},
    )


def build_line_item(product: Product, size: Optional[str], quantity: int) -> Dict[str, Any]:
    """Priced line for the financials engine — the only place a unit price is chosen."""
    variant = get_variant(product, size)
    return {
        "product_id": product.product_id,
        "sku": variant.sku,
        "product_name": product.name,
        "size": variant.size,
        "quantity": int(quantity),
        "unit_mrp_inr": variant.mrp_inr,
        "final_sale": product.final_sale,
    }


def sync_product_from_variants(product: Product) -> None:
    """Re-derive the product's "from" price and size list from its active variants."""
    live = sorted(active_variants(product), key=lambda v: (v.position, v.size))
    if not live:
        raise AppError(
            "no_active_variants",
            f"Product '{product.product_id}' must keep at least one active size.",
            422,
        )
    product.mrp_inr = min(v.mrp_inr for v in live)
    product.sizes_available = [v.size for v in live]


def set_variant_prices(db: Session, product: Product, prices: Mapping[str, Decimal]) -> None:
    """Create or reprice variants from a ``{size: price}`` map, then re-derive product fields.

    Sizes not in ``prices`` are left untouched (use ``set_variant_active`` to retire one).
    """
    if not prices:
        raise AppError("validation_error", "At least one size price is required.", 400)
    style = style_code(product)
    by_size = {v.size: v for v in product.variants}
    for raw_size, raw_price in prices.items():
        size = normalize_size(raw_size)
        price = Decimal(str(raw_price))
        if not size:
            raise AppError("validation_error", "Size must not be empty.", 400)
        if price <= 0:
            raise AppError("validation_error", f"Price for size {size} must be greater than zero.", 400)
        variant = by_size.get(size)
        if variant is None:
            variant = ProductVariant(
                size=size,
                sku=variant_sku(style, size),
                mrp_inr=price,
                position=size_position(size),
                is_active=True,
                # Every size owns a stock row from birth; units arrive via inventory_service.
                stock=VariantInventory(quantity_available=0, quantity_reserved=0, quantity_damaged=0),
            )
            product.variants.append(variant)
            by_size[size] = variant
        else:
            variant.mrp_inr = price
            variant.is_active = True
    product.sku = style
    db.flush()
    sync_product_from_variants(product)


def set_variant_active(product: Product, size: str, is_active: bool) -> ProductVariant:
    variant = next((v for v in product.variants if v.size == normalize_size(size)), None)
    if variant is None:
        raise AppError("variant_not_found", f"Product '{product.product_id}' has no size '{normalize_size(size)}'.", 404)
    variant.is_active = is_active
    sync_product_from_variants(product)
    return variant


def serialize_variants(product: Product) -> List[Dict[str, Any]]:
    return [
        {
            "size": v.size,
            "sku": v.sku,
            "mrp_inr": v.mrp_inr,
            "is_active": v.is_active,
            "stock": v.stock.quantity_available if v.stock else 0,
            "in_stock": bool(v.is_active and v.stock and v.stock.quantity_available > 0),
        }
        for v in sorted(product.variants, key=lambda v: (v.position, v.size))
    ]


def price_range(product: Product) -> Dict[str, Optional[Decimal]]:
    prices = [v.mrp_inr for v in active_variants(product)]
    return {"min": min(prices) if prices else None, "max": max(prices) if prices else None}
