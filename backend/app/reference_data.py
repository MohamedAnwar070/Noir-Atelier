"""Reference (lookup) data shipped with the application.

Single definition used by:
  * migration 0003 — to populate existing databases,
  * scripts/seed_demo.py — to populate fresh databases.

``ensure_reference_data`` only INSERTs rows that are missing; it never
overwrites a row, so labels/flags edited by an admin survive deploys.
After the first install this data is owned by the database (admin APIs),
not by this file.
"""

from typing import Any, Dict, List, Type

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Category,
    Color,
    Department,
    Material,
    OrderStatus,
    RefundStatus,
    ReturnReason,
    SearchSynonym,
)

DEPARTMENTS: List[Dict[str, Any]] = [
    {"code": "MEN", "name": "Men", "display_order": 1},
    {"code": "WOMEN", "name": "Women", "display_order": 2},
    {"code": "KIDS", "name": "Kids", "display_order": 3},
]

# Product-type taxonomy. IDs follow the CAT-<2 digits> convention (utils/id_generator).
CATEGORIES: List[Dict[str, Any]] = [
    {"category_id": "CAT-10", "slug": "tops", "name": "Tops", "parent_id": None, "display_order": 10},
    {"category_id": "CAT-11", "slug": "shirt", "name": "Shirts", "parent_id": "CAT-10", "display_order": 11},
    {"category_id": "CAT-12", "slug": "t-shirt", "name": "T-Shirts", "parent_id": "CAT-10", "display_order": 12},
    {"category_id": "CAT-20", "slug": "outerwear", "name": "Outerwear", "parent_id": None, "display_order": 20},
    {"category_id": "CAT-21", "slug": "overshirt", "name": "Overshirts", "parent_id": "CAT-20", "display_order": 21},
    {"category_id": "CAT-30", "slug": "knitwear", "name": "Knitwear", "parent_id": None, "display_order": 30},
    {"category_id": "CAT-40", "slug": "dress", "name": "Dresses", "parent_id": None, "display_order": 40},
]

COLORS: List[Dict[str, Any]] = [
    {"name": "Noir Black", "family": "black", "hex_code": "#111111"},
    {"name": "Obsidian", "family": "black", "hex_code": "#0B0B0C"},
    {"name": "Charcoal", "family": "grey", "hex_code": "#36454F"},
    {"name": "Ivory", "family": "white", "hex_code": "#FFFFF0"},
    {"name": "Midnight Navy", "family": "blue", "hex_code": "#191970"},
]

MATERIALS: List[Dict[str, Any]] = [
    {"name": "Belgian Linen", "family": "linen"},
    {"name": "Merino Wool", "family": "wool"},
    {"name": "Mulberry Silk", "family": "silk"},
    {"name": "Pima Cotton", "family": "cotton"},
    {"name": "Recycled Polyamide", "family": "polyamide"},
]

# term → (dimension, value). Values are department codes, category slugs,
# colour families or material families. Plural/singular forms of names and
# families are matched automatically by the search engine; synonyms cover
# genuinely different words.
SYNONYMS: List[Dict[str, Any]] = [
    # product types
    *({"term": t, "dimension": "product_type", "value": "t-shirt"} for t in ("tee", "tees", "tshirt", "tshirts", "t shirt")),
    *({"term": t, "dimension": "product_type", "value": "shirt"} for t in ("button-up", "button up", "button down", "button-down")),
    *({"term": t, "dimension": "product_type", "value": "knitwear"} for t in ("sweater", "sweaters", "jumper", "jumpers", "pullover", "pullovers", "crewneck", "crewnecks", "knit", "knits")),
    *({"term": t, "dimension": "product_type", "value": "outerwear"} for t in ("jacket", "jackets", "coat", "coats")),
    *({"term": t, "dimension": "product_type", "value": "overshirt"} for t in ("shacket", "shackets", "shirt jacket")),
    *({"term": t, "dimension": "product_type", "value": "dress"} for t in ("gown", "gowns", "frock", "frocks")),
    *({"term": t, "dimension": "product_type", "value": "tops"} for t in ("top",)),
    # departments
    *({"term": t, "dimension": "department", "value": "MEN"} for t in ("mens", "men's", "man", "gents", "male")),
    *({"term": t, "dimension": "department", "value": "WOMEN"} for t in ("womens", "women's", "woman", "ladies", "female")),
    *({"term": t, "dimension": "department", "value": "KIDS"} for t in ("kid", "kids'", "children", "child", "boys", "girls")),
    # colours
    *({"term": t, "dimension": "color", "value": "blue"} for t in ("navy",)),
    *({"term": t, "dimension": "color", "value": "grey"} for t in ("gray",)),
    *({"term": t, "dimension": "color", "value": "white"} for t in ("cream", "off-white", "off white")),
    # materials
    *({"term": t, "dimension": "material", "value": "wool"} for t in ("merino", "woolen", "woollen")),
    *({"term": t, "dimension": "material", "value": "linen"} for t in ("flax",)),
]

# Every status the order/refund state machines can produce.
ORDER_STATUSES: List[Dict[str, Any]] = [
    {"code": "pending", "label": "Awaiting payment", "tone": "warning", "is_cancellable": True, "display_order": 1},
    {"code": "paid", "label": "Paid", "tone": "success", "is_cancellable": True, "display_order": 2},
    {"code": "confirmed", "label": "Confirmed", "tone": "info", "is_cancellable": True, "display_order": 3},
    {"code": "needs_review", "label": "Under review", "tone": "warning", "display_order": 4},
    {"code": "shipped", "label": "Shipped", "tone": "info", "display_order": 5},
    {"code": "delivered", "label": "Delivered", "tone": "success", "is_returnable": True, "display_order": 6},
    {"code": "picked_up", "label": "Collected", "tone": "success", "is_returnable": True, "display_order": 7},
    {"code": "pending_return", "label": "Return in progress", "tone": "warning", "display_order": 8},
    {"code": "returned", "label": "Returned", "tone": "neutral", "display_order": 9},
    {"code": "refunded", "label": "Refunded", "tone": "neutral", "display_order": 10},
    {"code": "cancelled", "label": "Cancelled", "tone": "error", "display_order": 11},
    {"code": "expired", "label": "Hold expired", "tone": "error", "display_order": 12},
]

REFUND_STATUSES: List[Dict[str, Any]] = [
    {"code": "qc_passed", "label": "Ready to refund", "tone": "info", "display_order": 1},
    {"code": "pending_approval", "label": "Awaiting approval", "tone": "warning", "awaiting_approval": True, "display_order": 2},
    {"code": "awaiting_secondary_approval", "label": "Awaiting 2nd approval", "tone": "warning", "awaiting_approval": True, "display_order": 3},
    {"code": "approved", "label": "Approved", "tone": "success", "display_order": 4},
    {"code": "processed", "label": "Refunded", "tone": "success", "display_order": 5},
]

RETURN_REASONS: List[Dict[str, Any]] = [
    {"code": "size_mismatch", "label": "Size or fit isn't right", "display_order": 1},
    {"code": "style_preference", "label": "Style or silhouette preference", "display_order": 2},
    {"code": "changed_mind", "label": "Changed my mind", "display_order": 3},
    {"code": "not_as_described", "label": "Not as described", "display_order": 4},
    {"code": "fabric_defect", "label": "Fabric or stitching defect", "is_defect_claim": True, "display_order": 5},
    {"code": "damaged_in_transit", "label": "Damaged in transit", "is_defect_claim": True, "display_order": 6},
]

FIT_FEEDBACK_OPTIONS: List[Dict[str, str]] = [
    {"code": "true_to_size", "label": "Fits true to size"},
    {"code": "runs_small", "label": "Runs slightly small"},
    {"code": "runs_large", "label": "Runs slightly relaxed"},
]

# (model, natural key used to detect existing rows, rows) — insertion order respects FKs.
_REGISTRY: List[tuple] = [
    (Department, "code", DEPARTMENTS),
    (Category, "category_id", CATEGORIES),
    (Color, "name", COLORS),
    (Material, "name", MATERIALS),
    (SearchSynonym, "term", SYNONYMS),
    (OrderStatus, "code", ORDER_STATUSES),
    (RefundStatus, "code", REFUND_STATUSES),
    (ReturnReason, "code", RETURN_REASONS),
]


def _insert_missing(session: Session, model: Type, key: str, rows: List[Dict[str, Any]]) -> int:
    existing = set(session.scalars(select(getattr(model, key))).all())
    missing = [row for row in rows if row[key] not in existing]
    session.add_all(model(**row) for row in missing)
    session.flush()
    return len(missing)


def ensure_reference_data(session: Session) -> Dict[str, int]:
    """Insert any missing reference rows. Returns {table: rows_inserted}."""
    return {model.__tablename__: _insert_missing(session, model, key, rows) for model, key, rows in _REGISTRY}
