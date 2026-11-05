from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import ActorContext
from ..models import (
    Category,
    Color,
    Department,
    Inventory,
    Material,
    Occasion,
    OrderStatus,
    Palette,
    Product,
    ProductImage,
    ProductMaterial,
    ProductReview,
    ProductVariant,
    Recommendation,
    RefundStatus,
    ReturnReason,
    SearchSynonym,
)
from ..models.catalog import SYNONYM_DIMENSIONS
from ..schemas.product_schema import (
    CategoryCreateRequest,
    ColorCreateRequest,
    DepartmentCreateRequest,
    InventoryUpdateRequest,
    MaterialCreateRequest,
    ProductCreateRequest,
    ProductMaterialInput,
    ProductUpdateRequest,
    SynonymCreateRequest,
    VariantUpdateRequest,
)
from ..search.engine import SORT_OPTIONS
from ..utils.exceptions import AppError
from .audit_service import next_entity_id, record_audit
from .config_service import get_business_config_map, invalidate_config_cache
from .variant_service import (
    normalize_size,
    price_range,
    serialize_variants,
    set_variant_active,
    set_variant_prices,
)


def load_reviews(db: Session, product_ids: List[str]) -> Dict[str, List[ProductReview]]:
    """Active reviews for many products in ONE query (avoids N+1 on listing pages)."""
    grouped: Dict[str, List[ProductReview]] = {pid: [] for pid in product_ids}
    if not product_ids:
        return grouped
    rows = db.scalars(
        select(ProductReview)
        .where(ProductReview.product_id.in_(product_ids), ProductReview.is_active.is_(True))
        .order_by(ProductReview.review_id.desc())
    ).all()
    for r in rows:
        grouped[r.product_id].append(r)
    return grouped


def serialize_product(
    p: Product,
    db: Optional[Session] = None,
    reviews: Optional[List[ProductReview]] = None,
) -> Dict[str, Any]:
    """Product API shape. Pass ``reviews`` (from load_reviews) when serializing many products."""
    inv = p.inventory
    sorted_imgs = sorted(p.images, key=lambda x: x.display_order)
    images = [img.url for img in sorted_imgs]
    image_gallery = [
        {"url": img.url, "alt_text": img.alt_text, "display_order": img.display_order}
        for img in sorted_imgs
    ]
    accent_tag = sorted_imgs[0].alt_text if sorted_imgs and sorted_imgs[0].alt_text else p.department

    if reviews is None and db is not None:
        reviews = load_reviews(db, [p.product_id])[p.product_id]
    rev_rows = reviews or []
    review_count = len(rev_rows)
    avg_rating = round(sum(int(r.rating) for r in rev_rows) / review_count, 1) if rev_rows else 5.0
    reviews_list: List[Dict[str, Any]] = [
        {
            "review_id": r.review_id,
            "customer_id": r.customer_id,
            "rating": int(r.rating),
            "fit_feedback": r.fit_feedback,
            "comment": r.comment,
        }
        for r in rev_rows
    ]

    return {
        "product_id": p.product_id,
        "sku": p.sku,
        "name": p.name,
        "description": p.description,
        "category_id": p.category_id,
        "category": {"id": p.category.category_id, "slug": p.category.slug, "name": p.category.name},
        "department": p.department,
        # "From" price (lowest active size). Per-size prices are in `variants`.
        "mrp_inr": p.mrp_inr,
        "price_range": price_range(p),
        "variants": serialize_variants(p),
        "hsn_code": p.hsn_code,
        # Colour and fabric are structured data (searchable); "color" stays a display name.
        "color": p.color.name,
        "color_family": p.color.family,
        "color_hex": p.color.hex_code,
        # Curated style attributes (empty until the reviewed tag file is applied).
        "color_palettes": sorted(cp.palette_code for cp in p.color.palettes),
        "occasions": sorted(po.occasion_code for po in p.occasions),
        "materials": [
            {"name": pm.material.name, "family": pm.material.family, "percentage": float(pm.percentage)}
            for pm in p.materials
        ],
        "sizes_available": list(p.sizes_available or []),
        "fit_guide": p.fit_guide,
        "fabric_and_care": p.fabric_and_care,
        "country_of_origin": p.country_of_origin,
        "final_sale": p.final_sale,
        "security_tag_required": p.security_tag_required,
        "stock": inv.quantity_available if inv else 0,
        "quantity_reserved": inv.quantity_reserved if inv else 0,
        "size_breakdown": dict(inv.size_breakdown or {}) if inv else {},
        "images": images,
        "image_gallery": image_gallery,
        "accent_tag": accent_tag,
        "average_rating": avg_rating,
        "review_count": review_count,
        "reviews": reviews_list,
    }


def search_products(
    db: Session,
    q: Optional[str] = None,
    category: Optional[str] = None,
    department: Optional[str] = None,
    color: Optional[str] = None,
    material: Optional[str] = None,
    min_price: Optional[Decimal] = None,
    max_price: Optional[Decimal] = None,
    in_stock_only: bool = False,
    sort: str = "featured",
    limit: int = 20,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    from .search_service import search_catalog

    result = search_catalog(
        db,
        q=q,
        department=department,
        category=category,
        color=color,
        material=material,
        min_price=min_price,
        max_price=max_price,
        in_stock_only=in_stock_only,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return result["items"]


def get_product_by_id_or_sku(db: Session, identifier: str) -> Product:
    """Resolve a product by product ID, style code or any of its variant SKUs."""
    clean = identifier.strip().upper()
    variant_owner = select(ProductVariant.product_id).where(func.upper(ProductVariant.sku) == clean)
    prod = db.scalar(
        select(Product).where(
            Product.is_active.is_(True),
            (func.upper(Product.product_id) == clean)
            | (func.upper(Product.sku) == clean)
            | Product.product_id.in_(variant_owner),
        )
    )
    if prod is None:
        raise AppError("product_not_found", f"Product '{identifier}' was not found.", 404)
    return prod


def get_product_recommendations(db: Session, identifier: str, limit: int = 4) -> List[Dict[str, Any]]:
    source = get_product_by_id_or_sku(db, identifier)
    rec_rows = db.scalars(
        select(Recommendation)
        .where(Recommendation.source_product_id == source.product_id)
        .order_by(Recommendation.score.desc())
    ).all()

    results: List[Dict[str, Any]] = []
    seen_ids = {source.product_id}

    for rec in rec_rows:
        target = db.scalar(
            select(Product).where(
                Product.product_id == rec.recommended_product_id,
                Product.is_active.is_(True),
            )
        )
        if target and target.product_id not in seen_ids:
            seen_ids.add(target.product_id)
            serialized = serialize_product(target, db)
            serialized["relation_type"] = rec.relation_type
            serialized["recommendation_score"] = float(rec.score)
            results.append(serialized)
            if len(results) >= limit:
                return results

    others = db.scalars(
        select(Product).where(Product.is_active.is_(True), Product.product_id.notin_(seen_ids))
    ).all()
    ranked = sorted(
        others,
        key=lambda p: (0 if p.department == source.department else 1, abs(p.mrp_inr - source.mrp_inr)),
    )
    for p in ranked:
        if len(results) >= limit:
            break
        serialized = serialize_product(p, db)
        serialized["relation_type"] = "department_pair"
        serialized["recommendation_score"] = 0.85
        results.append(serialized)

    return results


def add_product_review(
    db: Session,
    actor: ActorContext,
    product_id: str,
    rating: int,
    fit_feedback: str = "true_to_size",
    comment: str = "",
) -> Dict[str, Any]:
    prod = get_product_by_id_or_sku(db, product_id)
    clamped_rating = max(1, min(5, int(rating)))
    cfg = get_business_config_map(db).get("catalog", {})
    allowed_fits = {
        opt["code"] for opt in cfg.get("fit_feedback_options", []) if isinstance(opt, dict) and "code" in opt
    }
    normalized_fit = (fit_feedback or "true_to_size").strip().lower()
    if allowed_fits and normalized_fit not in allowed_fits:
        raise AppError(
            "invalid_fit_feedback",
            f"Unsupported fit_feedback '{fit_feedback}'. Allowed: {', '.join(sorted(allowed_fits))}.",
            422,
        )
    rev = ProductReview(
        product_id=prod.product_id,
        customer_id=actor.actor_id if actor.actor_type == "customer" else "CUS-001",
        rating=clamped_rating,
        fit_feedback=normalized_fit,
        comment=comment.strip() or "Verified Noir Atelier garment review.",
    )
    db.add(rev)
    record_audit(
        db,
        actor,
        "product_review",
        prod.product_id,
        "create_review",
        {"rating": clamped_rating, "fit_feedback": normalized_fit},
        "customer_review_submission",
    )
    db.commit()
    db.refresh(prod)
    return serialize_product(prod, db)


def list_categories(db: Session) -> List[Dict[str, Any]]:
    cats = db.scalars(
        select(Category).where(Category.is_active.is_(True)).order_by(Category.display_order, Category.category_id)
    ).all()
    direct_counts: Dict[str, int] = dict(
        db.execute(
            select(Product.category_id, func.count(Product.product_id))
            .where(Product.is_active.is_(True))
            .group_by(Product.category_id)
        ).all()
    )
    children_by_parent: Dict[str, List[str]] = {}
    cat_ids = {c.category_id for c in cats}
    for c in cats:
        if c.parent_id and c.parent_id in cat_ids:
            children_by_parent.setdefault(c.parent_id, []).append(c.category_id)

    def subtree_ids(cid: str) -> Set[str]:
        out = {cid}
        for child_id in children_by_parent.get(cid, []):
            out |= subtree_ids(child_id)
        return out

    result: List[Dict[str, Any]] = []
    for c in cats:
        direct = int(direct_counts.get(c.category_id, 0))
        total_in_subtree = sum(int(direct_counts.get(sid, 0)) for sid in subtree_ids(c.category_id))
        result.append(
            {
                "category_id": c.category_id,
                "slug": c.slug,
                "name": c.name,
                "parent_id": c.parent_id,
                "display_order": c.display_order,
                "product_count": total_in_subtree,
                "direct_product_count": direct,
            }
        )
    return result


def get_catalog_meta(db: Session) -> Dict[str, Any]:
    """Single database-driven vocabulary & filter metadata payload for UI and AI agents."""
    cfg = get_business_config_map(db)
    slab_threshold = int(cfg.get("tax", {}).get("garment_slab_threshold_inr", 2500))
    luxury_min = int(cfg.get("catalog", {}).get("luxury_tier_min_inr", 7000))
    fit_options = list(cfg.get("catalog", {}).get("fit_feedback_options", []))

    dept_counts: Dict[str, int] = dict(
        db.execute(
            select(Product.department, func.count(Product.product_id))
            .where(Product.is_active.is_(True))
            .group_by(Product.department)
        ).all()
    )
    departments = [
        {
            "code": d.code,
            "name": d.name,
            "display_order": d.display_order,
            "product_count": int(dept_counts.get(d.code, 0)),
        }
        for d in db.scalars(
            select(Department).where(Department.is_active.is_(True)).order_by(Department.display_order, Department.code)
        ).all()
    ]

    categories = list_categories(db)

    color_counts: Dict[int, int] = dict(
        db.execute(
            select(Product.color_id, func.count(Product.product_id))
            .where(Product.is_active.is_(True))
            .group_by(Product.color_id)
        ).all()
    )
    color_rows = db.scalars(select(Color).order_by(Color.family, Color.name)).all()
    colors: List[Dict[str, Any]] = []
    family_acc: Dict[str, Dict[str, Any]] = {}
    for c in color_rows:
        cnt = int(color_counts.get(c.color_id, 0))
        colors.append(
            {
                "color_id": c.color_id,
                "name": c.name,
                "family": c.family,
                "hex_code": c.hex_code,
                "product_count": cnt,
            }
        )
        fam = family_acc.setdefault(
            c.family,
            {"family": c.family, "label": c.family.capitalize(), "hex_code": c.hex_code, "product_count": 0},
        )
        if not fam["hex_code"] and c.hex_code:
            fam["hex_code"] = c.hex_code
        fam["product_count"] += cnt

    material_counts: Dict[int, int] = dict(
        db.execute(
            select(ProductMaterial.material_id, func.count(func.distinct(ProductMaterial.product_id)))
            .join(Product, Product.product_id == ProductMaterial.product_id)
            .where(Product.is_active.is_(True))
            .group_by(ProductMaterial.material_id)
        ).all()
    )
    material_rows = db.scalars(select(Material).order_by(Material.family, Material.name)).all()
    materials: List[Dict[str, Any]] = []
    mat_family_acc: Dict[str, Dict[str, Any]] = {}
    for m in material_rows:
        cnt = int(material_counts.get(m.material_id, 0))
        materials.append(
            {
                "material_id": m.material_id,
                "name": m.name,
                "family": m.family,
                "product_count": cnt,
            }
        )
        mfam = mat_family_acc.setdefault(
            m.family,
            {"family": m.family, "label": m.family.capitalize(), "product_count": 0},
        )
        mfam["product_count"] += cnt

    custom_tiers = cfg.get("catalog", {}).get("custom_price_tiers")
    if isinstance(custom_tiers, list) and custom_tiers:
        price_tiers = [dict(t) for t in custom_tiers]
    else:
        price_tiers = [
            {"id": "ALL", "label": "Any price", "min_price": None, "max_price": None},
            {"id": "ESSENTIAL", "label": f"Up to \u20b9{slab_threshold:,}", "min_price": None, "max_price": slab_threshold},
            {
                "id": "SIGNATURE",
                "label": f"\u20b9{slab_threshold + 1:,} \u2013 \u20b9{luxury_min - 1:,}",
                "min_price": slab_threshold + 1,
                "max_price": luxury_min - 1,
            },
            {"id": "ATELIER", "label": f"\u20b9{luxury_min:,}+", "min_price": luxury_min, "max_price": None},
        ]

    order_statuses = [
        {
            "code": s.code,
            "label": s.label,
            "tone": s.tone,
            "is_cancellable": s.is_cancellable,
            "is_returnable": s.is_returnable,
            "display_order": s.display_order,
        }
        for s in db.scalars(select(OrderStatus).order_by(OrderStatus.display_order, OrderStatus.code)).all()
    ]
    refund_statuses = [
        {
            "code": s.code,
            "label": s.label,
            "tone": s.tone,
            "awaiting_approval": s.awaiting_approval,
            "display_order": s.display_order,
        }
        for s in db.scalars(select(RefundStatus).order_by(RefundStatus.display_order, RefundStatus.code)).all()
    ]
    return_reasons = [
        {
            "code": r.code,
            "label": r.label,
            "is_defect_claim": r.is_defect_claim,
            "display_order": r.display_order,
        }
        for r in db.scalars(
            select(ReturnReason).where(ReturnReason.is_active.is_(True)).order_by(ReturnReason.display_order, ReturnReason.code)
        ).all()
    ]

    occasions = [
        {"code": o.code, "name": o.name}
        for o in db.scalars(
            select(Occasion).where(Occasion.is_active.is_(True)).order_by(Occasion.display_order, Occasion.code)
        ).all()
    ]
    palettes = [
        {"code": p.code, "name": p.name}
        for p in db.scalars(select(Palette).order_by(Palette.display_order, Palette.code)).all()
    ]
    # Server-owned synonym vocabulary: every dimension with its valid canonical targets,
    # so admin tooling never hardcodes (or drifts from) SYNONYM_DIMENSIONS.
    target_options = {
        "department": [{"value": d["code"], "label": d["name"]} for d in departments],
        "product_type": [{"value": c["slug"], "label": c["name"]} for c in categories],
        "color": [{"value": f["family"], "label": f["label"]} for f in family_acc.values()],
        "material": [{"value": f["family"], "label": f["label"]} for f in mat_family_acc.values()],
        "occasion": [{"value": o["code"], "label": o["name"]} for o in occasions],
        "palette": [{"value": p["code"], "label": p["name"]} for p in palettes],
    }
    synonym_dimensions = [
        {"code": dim, "label": _SYNONYM_TARGETS[dim][2], "options": target_options[dim]}
        for dim in SYNONYM_DIMENSIONS
    ]

    return {
        "departments": departments,
        "categories": categories,
        "colors": colors,
        "color_families": list(family_acc.values()),
        "materials": materials,
        "material_families": list(mat_family_acc.values()),
        "sort_options": [dict(opt) for opt in SORT_OPTIONS],
        "price_tiers": price_tiers,
        "order_statuses": order_statuses,
        "refund_statuses": refund_statuses,
        "return_reasons": return_reasons,
        "fit_feedback_options": fit_options,
        "occasions": occasions,
        "palettes": palettes,
        "synonym_dimensions": synonym_dimensions,
    }


def _resolve_department(db: Session, raw_dept: str) -> Department:
    dept_code = raw_dept.strip().upper()
    dept = db.scalar(select(Department).where(Department.code == dept_code, Department.is_active.is_(True)))
    if dept is None:
        valid = [
            d.code
            for d in db.scalars(select(Department).where(Department.is_active.is_(True)).order_by(Department.display_order)).all()
        ]
        raise AppError(
            "invalid_department",
            f"Unsupported department '{raw_dept}'. Active departments: {', '.join(valid)}.",
            422,
        )
    return dept


def _resolve_category(db: Session, raw_category: str) -> Category:
    cleaned = raw_category.strip()
    cat = db.scalar(
        select(Category).where(
            Category.is_active.is_(True),
            (func.upper(Category.category_id) == cleaned.upper()) | (Category.slug == cleaned.lower()),
        )
    )
    if cat is None:
        raise AppError("invalid_category", f"Category '{raw_category}' does not exist.", 422)
    return cat


def _resolve_or_create_color(
    db: Session, color_name: str, color_family: Optional[str] = None, color_hex: Optional[str] = None
) -> Color:
    clean_name = color_name.strip()
    if not clean_name:
        raise AppError("invalid_color", "Product colour name is required.", 422)
    hex_val = color_hex.strip().upper() if color_hex and color_hex.strip() else None
    if hex_val and not re.match(r"^#[0-9A-F]{6}$", hex_val):
        raise AppError("invalid_color_hex", "hex_code must be a 7-character hex colour such as '#111111'.", 422)
    existing = db.scalar(select(Color).where(func.lower(Color.name) == clean_name.lower()))
    if existing is not None:
        if hex_val and not existing.hex_code:
            existing.hex_code = hex_val
        return existing
    family = (color_family or clean_name.split()[-1]).strip().lower()
    col = Color(name=clean_name, family=family, hex_code=hex_val)
    db.add(col)
    db.flush()
    return col


def _set_product_materials(db: Session, prod: Product, items: List[ProductMaterialInput]) -> None:
    total_pct = sum((item.percentage for item in items), Decimal("0"))
    if total_pct > Decimal("100"):
        raise AppError("invalid_material_composition", "Material composition percentages cannot exceed 100%.", 422)
    prod.materials.clear()
    db.flush()
    seen_material_ids: Set[int] = set()
    for item in items:
        clean_name = item.name.strip()
        mat = db.scalar(select(Material).where(func.lower(Material.name) == clean_name.lower()))
        if mat is None:
            fam = (item.family or clean_name.split()[-1]).strip().lower()
            mat = Material(name=clean_name, family=fam)
            db.add(mat)
            db.flush()
        if mat.material_id in seen_material_ids:
            raise AppError("duplicate_material", f"Duplicate material '{clean_name}' in product composition.", 422)
        seen_material_ids.add(mat.material_id)
        prod.materials.append(
            ProductMaterial(product_id=prod.product_id, material_id=mat.material_id, percentage=item.percentage)
        )


def create_product(db: Session, actor: ActorContext, req: ProductCreateRequest) -> Dict[str, Any]:
    dept_row = _resolve_department(db, req.department)
    cat_row = _resolve_category(db, req.category_id)
    if not req.hsn_code.startswith(("61", "62")):
        raise AppError("invalid_hsn", "Only HSN Chapter 61 and 62 garments are permitted.", 422)

    color_row = _resolve_or_create_color(db, req.color, req.color_family, req.color_hex)

    # Per-size prices if given, otherwise every listed size at the base price.
    size_prices = req.variant_prices or {size: req.mrp_inr for size in req.sizes_available}
    sizes = [normalize_size(s) for s in size_prices]

    pid = req.product_id or next_entity_id(db, Product, Product.product_id, "product", start_seq=1)
    prod = Product(
        product_id=pid,
        sku=req.sku.strip().upper(),  # style code; variant SKUs are derived from it
        name=req.name.strip(),
        description=req.description.strip(),
        category_id=cat_row.category_id,
        department=dept_row.code,
        mrp_inr=req.mrp_inr,  # provisional; re-derived from variants below
        hsn_code=req.hsn_code,
        color_id=color_row.color_id,
        sizes_available=sizes,
        fit_guide=req.fit_guide,
        fabric_and_care=req.fabric_and_care,
        final_sale=req.final_sale,
        security_tag_required=True,
    )
    db.add(prod)
    db.flush()
    set_variant_prices(db, prod, size_prices)
    if req.materials:
        _set_product_materials(db, prod, req.materials)
    default_img = "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?auto=format&fit=crop&w=900&q=80"
    db.add(ProductImage(product_id=pid, url=default_img, alt_text=f"{dept_row.code} Atelier Edition", display_order=1))
    db.add(
        Inventory(
            product_id=pid,
            quantity_available=req.initial_stock,
            quantity_reserved=0,
            quantity_damaged=0,
            size_breakdown={sz: max(1, req.initial_stock // max(1, len(sizes))) for sz in sizes},
        )
    )
    record_audit(
        db,
        actor,
        "product",
        pid,
        "create_product",
        {
            "sku": prod.sku,
            "category_id": cat_row.category_id,
            "color": color_row.name,
            "variant_prices": {v.size: float(v.mrp_inr) for v in prod.variants},
        },
        "admin_catalog_create",
    )
    db.commit()
    db.refresh(prod)
    return serialize_product(prod, db)


def update_product(db: Session, actor: ActorContext, product_id: str, req: ProductUpdateRequest) -> Dict[str, Any]:
    prod = get_product_by_id_or_sku(db, product_id)
    changes: Dict[str, Any] = {}
    for field_name in ("name", "description", "fit_guide", "fabric_and_care", "final_sale"):
        val = getattr(req, field_name)
        if val is not None:
            setattr(prod, field_name, val)
            changes[field_name] = val

    if req.department is not None:
        dept_row = _resolve_department(db, req.department)
        prod.department = dept_row.code
        changes["department"] = dept_row.code

    if req.category_id is not None:
        cat_row = _resolve_category(db, req.category_id)
        prod.category_id = cat_row.category_id
        changes["category_id"] = cat_row.category_id

    if req.color is not None:
        color_row = _resolve_or_create_color(db, req.color, req.color_family, req.color_hex)
        prod.color_id = color_row.color_id
        changes["color"] = color_row.name

    if req.materials is not None:
        _set_product_materials(db, prod, req.materials)
        changes["materials"] = [{"name": m.name, "percentage": float(m.percentage)} for m in req.materials]

    # Price lives on variants. A single mrp_inr means "every active size at this
    # price"; per-size pricing goes through update_variant.
    if req.mrp_inr is not None:
        set_variant_prices(db, prod, {v.size: req.mrp_inr for v in prod.variants if v.is_active})
        changes["mrp_inr_all_sizes"] = float(req.mrp_inr)

    record_audit(db, actor, "product", prod.product_id, "update_product", changes, "admin_catalog_update")
    db.commit()
    db.refresh(prod)
    return serialize_product(prod, db)


def update_variant(
    db: Session, actor: ActorContext, product_id: str, size: str, req: VariantUpdateRequest
) -> Dict[str, Any]:
    """Reprice and/or activate/retire one size of a product."""
    prod = get_product_by_id_or_sku(db, product_id)
    size = normalize_size(size)
    before = next((v for v in prod.variants if v.size == size), None)
    previous = {"mrp_inr": float(before.mrp_inr), "is_active": before.is_active} if before else None

    if req.mrp_inr is not None:
        set_variant_prices(db, prod, {size: req.mrp_inr})
    if req.is_active is not None:
        set_variant_active(prod, size, req.is_active)

    variant = next((v for v in prod.variants if v.size == size), None)
    if variant is None:
        raise AppError("variant_not_found", f"Product '{prod.product_id}' has no size '{size}'. Provide mrp_inr to add it.", 404)

    record_audit(
        db,
        actor,
        "product_variant",
        variant.sku,
        "update_variant",
        {"before": previous, "after": {"mrp_inr": float(variant.mrp_inr), "is_active": variant.is_active}},
        "admin_variant_pricing",
    )
    db.commit()
    db.refresh(prod)
    return serialize_product(prod, db)


def discontinue_product(db: Session, actor: ActorContext, product_id: str, reason: str = "discontinued") -> Dict[str, Any]:
    prod = get_product_by_id_or_sku(db, product_id)
    prod.is_active = False
    prod.deleted_at = datetime.now(timezone.utc)
    record_audit(db, actor, "product", prod.product_id, "discontinue_product", {"is_active": False}, reason)
    db.commit()
    return {"product_id": prod.product_id, "status": "discontinued", "is_active": False}


def list_inventory(db: Session, low_stock_only: bool = False) -> List[Dict[str, Any]]:
    rows = db.scalars(select(Inventory).order_by(Inventory.product_id)).all()
    output = []
    for inv in rows:
        is_low = inv.quantity_available <= inv.low_stock_threshold
        if low_stock_only and not is_low:
            continue
        output.append(
            {
                "product_id": inv.product_id,
                "name": inv.product.name if inv.product else inv.product_id,
                "product_name": inv.product.name if inv.product else inv.product_id,
                "quantity_available": inv.quantity_available,
                "quantity_reserved": inv.quantity_reserved,
                "quantity_damaged": inv.quantity_damaged,
                "low_stock_threshold": inv.low_stock_threshold,
                "low_stock_alert": is_low,
                "size_breakdown": dict(inv.size_breakdown or {}),
            }
        )
    return output


def update_inventory_stock(
    db: Session,
    actor: ActorContext,
    product_id: str,
    req: InventoryUpdateRequest,
) -> Dict[str, Any]:
    prod = get_product_by_id_or_sku(db, product_id)
    inv = prod.inventory
    if inv is None:
        raise AppError("inventory_not_found", f"Inventory record missing for '{product_id}'.", 404)

    old_qty = inv.quantity_available
    inv.quantity_available = req.quantity_available
    if req.size_breakdown is not None:
        inv.size_breakdown = req.size_breakdown
    inv.last_sync = datetime.now(timezone.utc)

    record_audit(
        db,
        actor,
        "inventory",
        prod.product_id,
        "update_inventory",
        {"old_available": old_qty, "new_available": inv.quantity_available},
        req.reason,
    )
    db.commit()
    return {
        "product_id": prod.product_id,
        "quantity_available": inv.quantity_available,
        "quantity_reserved": inv.quantity_reserved,
    }


def list_search_synonyms(db: Session) -> List[Dict[str, Any]]:
    rows = db.scalars(select(SearchSynonym).order_by(SearchSynonym.dimension, SearchSynonym.term)).all()
    return [
        {
            "synonym_id": s.synonym_id,
            "term": s.term,
            "dimension": s.dimension,
            "value": s.value,
            "is_active": s.is_active,
        }
        for s in rows
    ]


# dimension -> (canonical column, case normaliser, label, extra filters).
# Every SYNONYM_DIMENSION must appear here (asserted below), so a newly added
# dimension can never silently fall through to another table's lookup.
_SYNONYM_TARGETS = {
    "department": (Department.code, str.upper, "Department", (Department.is_active.is_(True),)),
    "product_type": (Category.slug, str.lower, "Product type", (Category.is_active.is_(True),)),
    "color": (Color.family, str.lower, "Colour family", ()),
    "material": (Material.family, str.lower, "Material family", ()),
    "occasion": (Occasion.code, str.lower, "Occasion", (Occasion.is_active.is_(True),)),
    "palette": (Palette.code, str.lower, "Palette", ()),
}
assert set(_SYNONYM_TARGETS) == set(SYNONYM_DIMENSIONS), "synonym target map out of sync with SYNONYM_DIMENSIONS"


def _validate_synonym_target(db: Session, dimension: str, raw_value: str) -> str:
    target = _SYNONYM_TARGETS.get(dimension)
    if target is None:
        raise AppError(
            "invalid_synonym_dimension",
            f"dimension must be one of {', '.join(SYNONYM_DIMENSIONS)}.",
            422,
        )
    column, normalise, label, filters = target
    val = normalise(raw_value.strip())
    if db.scalar(select(column).where(column == val, *filters).limit(1)) is None:
        raise AppError("invalid_synonym_target", f"{label} '{val}' does not exist.", 422)
    return val


def create_search_synonym(db: Session, actor: ActorContext, req: SynonymCreateRequest) -> Dict[str, Any]:
    term = " ".join(req.term.strip().lower().replace("-", " ").split())
    if not term:
        raise AppError("invalid_synonym_term", "Synonym term cannot be empty.", 422)
    dimension = req.dimension.strip().lower()
    canonical_value = _validate_synonym_target(db, dimension, req.value)

    row = db.scalar(select(SearchSynonym).where(SearchSynonym.term == term))
    if row is None:
        row = SearchSynonym(term=term, dimension=dimension, value=canonical_value, is_active=True)
        db.add(row)
    else:
        row.dimension = dimension
        row.value = canonical_value
        row.is_active = True
    db.flush()
    record_audit(
        db,
        actor,
        "search_synonym",
        str(row.synonym_id),
        "upsert_synonym",
        {"term": term, "dimension": dimension, "value": canonical_value},
        "admin_vocabulary_update",
    )
    db.commit()
    return {
        "synonym_id": row.synonym_id,
        "term": row.term,
        "dimension": row.dimension,
        "value": row.value,
        "is_active": row.is_active,
    }


def delete_search_synonym(db: Session, actor: ActorContext, synonym_id: int) -> Dict[str, Any]:
    row = db.get(SearchSynonym, synonym_id)
    if row is None:
        raise AppError("synonym_not_found", f"Search synonym '{synonym_id}' not found.", 404)
    term = row.term
    db.delete(row)
    record_audit(db, actor, "search_synonym", str(synonym_id), "delete_synonym", {"term": term}, "admin_vocabulary_delete")
    db.commit()
    return {"synonym_id": synonym_id, "term": term, "deleted": True}


def create_catalog_color(db: Session, actor: ActorContext, req: ColorCreateRequest) -> Dict[str, Any]:
    col = _resolve_or_create_color(db, req.name, req.family, req.hex_code)
    col.family = req.family.strip().lower()
    if req.hex_code:
        col.hex_code = req.hex_code.strip().upper()
    record_audit(
        db,
        actor,
        "color",
        str(col.color_id),
        "upsert_color",
        {"name": col.name, "family": col.family, "hex_code": col.hex_code},
        "admin_vocabulary_update",
    )
    db.commit()
    return {"color_id": col.color_id, "name": col.name, "family": col.family, "hex_code": col.hex_code}


def create_catalog_material(db: Session, actor: ActorContext, req: MaterialCreateRequest) -> Dict[str, Any]:
    clean_name = req.name.strip()
    clean_family = req.family.strip().lower()
    mat = db.scalar(select(Material).where(func.lower(Material.name) == clean_name.lower()))
    if mat is None:
        mat = Material(name=clean_name, family=clean_family)
        db.add(mat)
    else:
        mat.family = clean_family
    db.flush()
    record_audit(
        db,
        actor,
        "material",
        str(mat.material_id),
        "upsert_material",
        {"name": mat.name, "family": mat.family},
        "admin_vocabulary_update",
    )
    db.commit()
    return {"material_id": mat.material_id, "name": mat.name, "family": mat.family}


def create_catalog_category(db: Session, actor: ActorContext, req: CategoryCreateRequest) -> Dict[str, Any]:
    slug = re.sub(r"[^a-z0-9-]+", "-", req.slug.strip().lower()).strip("-")
    if not slug:
        raise AppError("invalid_category_slug", "Category slug must contain lowercase letters or numbers.", 422)
    if db.scalar(select(Category).where(Category.slug == slug)) is not None:
        raise AppError("duplicate_category_slug", f"Category slug '{slug}' already exists.", 409)
    if req.parent_id:
        parent = db.get(Category, req.parent_id.strip().upper())
        if parent is None:
            raise AppError("invalid_parent_category", f"Parent category '{req.parent_id}' not found.", 422)
        parent_id: Optional[str] = parent.category_id
    else:
        parent_id = None
    cid = (req.category_id.strip().upper() if req.category_id else None) or next_entity_id(
        db, Category, Category.category_id, "category", start_seq=50
    )
    cat = Category(
        category_id=cid,
        slug=slug,
        name=req.name.strip(),
        parent_id=parent_id,
        display_order=req.display_order,
    )
    db.add(cat)
    record_audit(
        db,
        actor,
        "category",
        cid,
        "create_category",
        {"slug": slug, "name": cat.name, "parent_id": parent_id},
        "admin_vocabulary_update",
    )
    db.commit()
    return {
        "category_id": cat.category_id,
        "slug": cat.slug,
        "name": cat.name,
        "parent_id": cat.parent_id,
        "display_order": cat.display_order,
    }


def create_catalog_department(db: Session, actor: ActorContext, req: DepartmentCreateRequest) -> Dict[str, Any]:
    code = req.code.strip().upper()
    if not re.match(r"^[A-Z][A-Z0-9_]{1,15}$", code):
        raise AppError("invalid_department_code", "Department code must be 2–16 uppercase letters/digits.", 422)
    dept = db.get(Department, code)
    if dept is None:
        dept = Department(code=code, name=req.name.strip(), display_order=req.display_order, is_active=True)
        db.add(dept)
    else:
        dept.name = req.name.strip()
        dept.display_order = req.display_order
        dept.is_active = True
    record_audit(
        db,
        actor,
        "department",
        code,
        "upsert_department",
        {"code": code, "name": dept.name},
        "admin_vocabulary_update",
    )
    db.commit()
    invalidate_config_cache()
    return {"code": dept.code, "name": dept.name, "display_order": dept.display_order, "is_active": dept.is_active}
