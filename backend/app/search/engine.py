"""Executes a SearchIntent as a single SQL query (filter, sort, paginate in the database).

The engine never loads the whole catalogue into Python, so it behaves the same
for 5 products or 10,000. It returns ORM rows; serialization belongs to the
service layer.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Set

from sqlalchemy import Select, and_, case, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import Category, Color, Inventory, Material, Product, ProductMaterial, ProductReview, ProductVariant
from .interpreter import SearchIntent

# Sort options the engine supports. Exposed to clients via the catalog meta endpoint.
SORT_OPTIONS = [
    {"id": "featured", "label": "Featured"},
    {"id": "price_asc", "label": "Price: low to high"},
    {"id": "price_desc", "label": "Price: high to low"},
    {"id": "rating", "label": "Top rated"},
    {"id": "newest", "label": "Newest"},
]
SORT_IDS = {s["id"] for s in SORT_OPTIONS}


@dataclass
class SearchPage:
    products: List[Product]
    total: int
    # True when free-text words matched nothing and were dropped to return useful results.
    relaxed: bool = False
    ignored_terms: Optional[List[str]] = None


def _filtered(intent: SearchIntent, category_slugs: Set[str], in_stock_only: bool, use_text: bool) -> Select:
    stmt = select(Product).where(Product.is_active.is_(True))
    f = intent.filters

    if f["department"]:
        stmt = stmt.where(Product.department.in_(f["department"]))
    if category_slugs:
        stmt = stmt.where(Product.category_id.in_(select(Category.category_id).where(Category.slug.in_(category_slugs))))
    if f["color"]:
        stmt = stmt.where(Product.color_id.in_(select(Color.color_id).where(Color.family.in_(f["color"]))))
    if f["material"]:
        stmt = stmt.where(
            exists().where(
                ProductMaterial.product_id == Product.product_id,
                ProductMaterial.material_id == Material.material_id,
                Material.family.in_(f["material"]),
            )
        )
    if intent.min_price is not None or intent.max_price is not None:
        # A product matches if ANY active size is priced in range (sizes can differ in price).
        price_conditions = [ProductVariant.product_id == Product.product_id, ProductVariant.is_active.is_(True)]
        has_any_variant = exists().where(
            ProductVariant.product_id == Product.product_id, ProductVariant.is_active.is_(True)
        )
        fallback_conditions = [~has_any_variant]
        if intent.min_price is not None:
            price_conditions.append(ProductVariant.mrp_inr >= intent.min_price)
            fallback_conditions.append(Product.mrp_inr >= intent.min_price)
        if intent.max_price is not None:
            price_conditions.append(ProductVariant.mrp_inr <= intent.max_price)
            fallback_conditions.append(Product.mrp_inr <= intent.max_price)
        stmt = stmt.where(or_(exists().where(and_(*price_conditions)), and_(*fallback_conditions)))
    if in_stock_only:
        stmt = stmt.where(
            exists().where(Inventory.product_id == Product.product_id, Inventory.quantity_available > 0)
        )
    if use_text:
        for term in intent.text_terms:
            pattern = f"%{term}%"
            stmt = stmt.where(or_(Product.name.ilike(pattern), Product.description.ilike(pattern)))
    return stmt


def _ordered(stmt: Select, sort: str, intent: SearchIntent, use_text: bool) -> Select:
    if sort == "price_asc":
        return stmt.order_by(Product.mrp_inr.asc(), Product.product_id)
    if sort == "price_desc":
        top_price = (
            select(func.max(ProductVariant.mrp_inr))
            .where(ProductVariant.product_id == Product.product_id, ProductVariant.is_active.is_(True))
            .scalar_subquery()
        )
        return stmt.order_by(top_price.desc(), Product.product_id)
    if sort == "newest":
        return stmt.order_by(Product.created_at.desc(), Product.product_id)
    if sort == "rating":
        avg_rating = (
            select(func.avg(ProductReview.rating))
            .where(ProductReview.product_id == Product.product_id, ProductReview.is_active.is_(True))
            .scalar_subquery()
        )
        return stmt.order_by(func.coalesce(avg_rating, 0).desc(), Product.product_id)
    # featured: free-text hits in the name rank first
    if use_text and intent.text_terms:
        name_hits = sum(case((Product.name.ilike(f"%{t}%"), 1), else_=0) for t in intent.text_terms)
        return stmt.order_by(name_hits.desc(), Product.product_id)
    return stmt.order_by(Product.product_id)


def run_search(
    db: Session,
    intent: SearchIntent,
    *,
    category_subtree: Dict[str, Set[str]],
    in_stock_only: bool = False,
    sort: str = "featured",
    limit: int = 24,
    offset: int = 0,
) -> SearchPage:
    sort = sort if sort in SORT_IDS else "featured"
    # "tops" also matches its children (shirts, t-shirts).
    category_slugs: Set[str] = set()
    for slug in intent.filters["product_type"]:
        category_slugs |= category_subtree.get(slug, {slug})

    def page(use_text: bool) -> SearchPage:
        base = _filtered(intent, category_slugs, in_stock_only, use_text)
        total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = db.scalars(
            _ordered(base, sort, intent, use_text)
            .options(
                selectinload(Product.variants),
                selectinload(Product.images),
                selectinload(Product.materials),
                selectinload(Product.inventory),
                selectinload(Product.category),
            )
            .limit(limit)
            .offset(offset)
        ).all()
        return SearchPage(products=list(rows), total=total)

    result = page(use_text=True)
    has_structured = (
        any(intent.filters.values()) or intent.min_price is not None or intent.max_price is not None
    )
    if result.total == 0 and intent.text_terms and has_structured:
        # Unknown words ("comfortable", "summer") shouldn't hide products that match
        # everything else the shopper asked for.
        relaxed = page(use_text=False)
        relaxed.relaxed = True
        relaxed.ignored_terms = list(intent.text_terms)
        return relaxed
    return result
