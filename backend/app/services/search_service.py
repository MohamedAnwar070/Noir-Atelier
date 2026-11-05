"""Catalogue search — the single entry point used by the storefront and the AI agents.

Combines the data-driven vocabulary, the free-text interpreter and the SQL
engine, and serializes results in the standard product shape.

Explicit filters (from UI controls or an agent's context) override what the
free text implied: a shopper on the Women tab who types "shirt" stays in Women.
"""

from decimal import Decimal
from typing import Any, Dict, Optional, Set

from sqlalchemy.orm import Session

from ..search import interpret, load_vocabulary, run_search
from .product_service import load_reviews, serialize_product

MAX_PAGE_SIZE = 100


_LEGACY_CATEGORY_TO_DEPT = {"CAT-MEN": "MEN", "CAT-WMN": "WOMEN", "CAT-KID": "KIDS"}


def _resolve_explicit_category(raw_category: str, vocab) -> tuple[Optional[str], Optional[str]]:
    """Resolve explicit `category` param into (product_type_slug, legacy_department)."""
    cleaned = raw_category.strip()
    if not cleaned or cleaned.upper() == "ALL":
        return None, None
    upper = cleaned.upper()
    if upper in vocab.slug_by_category_id:
        return vocab.slug_by_category_id[upper], None
    if upper in vocab.department_codes:
        return None, upper
    if upper in _LEGACY_CATEGORY_TO_DEPT:
        return None, _LEGACY_CATEGORY_TO_DEPT[upper]
    lower = cleaned.lower()
    if lower in vocab.category_subtree:
        return lower, None
    norm = " ".join(lower.replace("-", " ").split())
    meaning = vocab.terms.get(norm)
    if meaning and meaning[0] == "product_type":
        return meaning[1], None
    if meaning and meaning[0] == "department":
        return None, meaning[1]
    return lower, None


def _csv_values(raw: Optional[str]) -> Set[str]:
    """'Black, white' → {'black', 'white'}; 'ALL' or empty → empty set."""
    if not raw or raw.strip().upper() == "ALL":
        return set()
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


# Descriptive tags inferred from free text that may be relaxed when nothing matches.
SOFT_DIMENSIONS = ("occasion", "palette")


def search_catalog(
    db: Session,
    q: Optional[str] = None,
    *,
    department: Optional[str] = None,
    category: Optional[str] = None,
    color: Optional[str] = None,
    material: Optional[str] = None,
    occasion: Optional[str] = None,
    palette: Optional[str] = None,
    min_price: Optional[Decimal] = None,
    max_price: Optional[Decimal] = None,
    in_stock_only: bool = False,
    sort: str = "featured",
    limit: int = 24,
    offset: int = 0,
) -> Dict[str, Any]:
    vocab = load_vocabulary(db)
    intent = interpret(q, vocab)

    cat_slug, cat_dept = _resolve_explicit_category(category, vocab) if category else (None, None)
    dept_val = department.strip().upper() if department and department.strip().upper() != "ALL" else cat_dept

    explicit = {
        "department": {dept_val} if dept_val else set(),
        "product_type": {cat_slug} if cat_slug else set(),
        # Comma-separated lists are allowed (e.g. palette=muted,pale) — used by the stylist.
        "color": _csv_values(color),
        "material": _csv_values(material),
        "occasion": _csv_values(occasion),
        "palette": _csv_values(palette),
    }
    for dimension, values in explicit.items():
        if values:
            intent.filters[dimension] = values

    # A dimension with no curated assignments yet (e.g. occasion tags awaiting
    # review) would match nothing; skip it and say so instead of hiding the catalogue.
    skipped = sorted(d for d in vocab.untagged_dimensions if intent.filters.get(d))
    for dimension in skipped:
        intent.filters[dimension] = set()
    if min_price is not None:
        intent.min_price = min_price
    if max_price is not None:
        intent.max_price = max_price

    limit = max(1, min(int(limit), MAX_PAGE_SIZE))

    def search():
        return run_search(
            db,
            intent,
            category_subtree=vocab.category_subtree,
            in_stock_only=in_stock_only,
            sort=sort,
            limit=limit,
            offset=max(0, int(offset)),
        )

    page = search()
    # Occasion and palette are curated, sparse "mood" tags. When one was only INFERRED
    # from the shopper's words ("summer" -> resort) and nothing matches, keep the hard
    # constraints (garment, colour, material, price) and say what was relaxed — never
    # drop a filter the caller set explicitly.
    relaxed_dimensions = []
    if page.total == 0:
        relaxed_dimensions = sorted(d for d in SOFT_DIMENSIONS if intent.filters.get(d) and not explicit[d])
        if relaxed_dimensions:
            for dimension in relaxed_dimensions:
                intent.filters[dimension] = set()
            page = search()
            page.relaxed = page.relaxed or page.total > 0
    reviews = load_reviews(db, [p.product_id for p in page.products])

    return {
        "query": q or "",
        "items": [serialize_product(p, reviews=reviews[p.product_id]) for p in page.products],
        "total": page.total,
        "limit": limit,
        "offset": offset,
        "interpretation": {
            "filters": {dim: sorted(values) for dim, values in intent.filters.items()},
            "min_price": float(intent.min_price) if intent.min_price is not None else None,
            "max_price": float(intent.max_price) if intent.max_price is not None else None,
            "text_terms": intent.text_terms,
            "recognized": intent.recognized,
            "relaxed": page.relaxed,
            "ignored_terms": page.ignored_terms or [],
            "skipped_dimensions": skipped,
            "relaxed_dimensions": relaxed_dimensions,
        },
    }
