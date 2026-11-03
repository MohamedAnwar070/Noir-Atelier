from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import ActorContext
from ..models import Category, Inventory, Product, ProductImage, ProductReview, Recommendation
from ..schemas.product_schema import InventoryUpdateRequest, ProductCreateRequest, ProductUpdateRequest
from ..utils.exceptions import AppError
from .audit_service import next_entity_id, record_audit

SYNONYM_MAP: Dict[str, List[str]] = {
    "tee": ["tee", "t-shirt", "cotton"],
    "t-shirt": ["t-shirt", "tee", "cotton"],
    "shirt": ["shirt", "linen", "overshirt"],
    "pullover": ["crewneck", "merino", "knit", "sweater"],
    "sweater": ["crewneck", "merino", "knit", "sweater"],
    "jacket": ["overshirt", "outerwear", "wool"],
    "dress": ["dress", "midi", "silk"],
    "kids": ["kids", "children", "merino"],
    "men": ["men", "linen", "overshirt"],
    "women": ["women", "silk", "pima", "dress", "tee"],
}


def serialize_product(p: Product, db: Optional[Session] = None) -> Dict[str, Any]:
    inv = p.inventory
    sorted_imgs = sorted(p.images, key=lambda x: x.display_order)
    images = [img.url for img in sorted_imgs]
    image_gallery = [
        {"url": img.url, "alt_text": img.alt_text, "display_order": img.display_order}
        for img in sorted_imgs
    ]
    accent_tag = sorted_imgs[0].alt_text if sorted_imgs and sorted_imgs[0].alt_text else p.department

    avg_rating = 5.0
    review_count = 0
    reviews_list: List[Dict[str, Any]] = []
    if db is not None:
        rev_rows = db.scalars(
            select(ProductReview)
            .where(
                ProductReview.product_id == p.product_id,
                ProductReview.is_active.is_(True),
            )
            .order_by(ProductReview.review_id.desc())
        ).all()
        if rev_rows:
            review_count = len(rev_rows)
            avg_rating = round(sum(int(r.rating) for r in rev_rows) / review_count, 1)
            reviews_list = [
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
        "department": p.department,
        "mrp_inr": p.mrp_inr,
        "hsn_code": p.hsn_code,
        "color": p.color,
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
    max_price: Optional[Decimal] = None,
    in_stock_only: bool = False,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    stmt = select(Product).where(Product.is_active.is_(True))

    if category:
        cat_norm = category.strip().upper()
        if cat_norm in ("MEN", "WOMEN", "KIDS"):
            stmt = stmt.where(func.upper(Product.department) == cat_norm)
        else:
            stmt = stmt.where(func.upper(Product.category_id) == cat_norm)

    if department:
        stmt = stmt.where(func.upper(Product.department) == department.strip().upper())

    if max_price is not None:
        stmt = stmt.where(Product.mrp_inr <= max_price)

    candidates = db.scalars(stmt.order_by(Product.product_id)).all()

    if in_stock_only:
        candidates = [p for p in candidates if p.inventory and p.inventory.quantity_available > 0]

    if q and q.strip():
        raw_tokens = [
            t.strip(".,?!:;\"'").lower()
            for t in q.strip().split()
            if len(t.strip(".,?!:;\"'")) >= 2
        ]
        stop_words = {"show", "me", "find", "under", "below", "for", "the", "with", "in", "and", "or", "inr", "rs"}
        tokens = [t for t in raw_tokens if t not in stop_words and not t.isdigit()]

        if tokens:
            scored: List[tuple[int, Product]] = []
            for prod in candidates:
                blob = " ".join(
                    [
                        prod.product_id,
                        prod.sku,
                        prod.name,
                        prod.description,
                        prod.department,
                        prod.color,
                        prod.fabric_and_care,
                    ]
                ).lower()
                score = 0
                for tok in tokens:
                    expanded = SYNONYM_MAP.get(tok, [tok])
                    if any(term in blob for term in expanded):
                        score += 2
                        if any(term in prod.name.lower() for term in expanded):
                            score += 3
                if score > 0:
                    scored.append((score, prod))
            scored.sort(key=lambda item: (-item[0], item[1].product_id))
            candidates = [item[1] for item in scored]

    return [serialize_product(p, db) for p in candidates[:limit]]


def get_product_by_id_or_sku(db: Session, identifier: str) -> Product:
    clean = identifier.strip().upper()
    prod = db.scalar(
        select(Product).where(
            Product.is_active.is_(True),
            (func.upper(Product.product_id) == clean) | (func.upper(Product.sku) == clean),
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
    rev = ProductReview(
        product_id=prod.product_id,
        customer_id=actor.actor_id if actor.actor_type == "customer" else "CUS-001",
        rating=clamped_rating,
        fit_feedback=fit_feedback or "true_to_size",
        comment=comment.strip() or "Verified Noir Atelier garment review.",
    )
    db.add(rev)
    record_audit(
        db,
        actor,
        "product_review",
        prod.product_id,
        "create_review",
        {"rating": clamped_rating, "fit_feedback": fit_feedback},
        "customer_review_submission",
    )
    db.commit()
    db.refresh(prod)
    return serialize_product(prod, db)


def list_categories(db: Session) -> List[Dict[str, Any]]:
    cats = db.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.category_id)).all()
    result = []
    for c in cats:
        active_count = sum(1 for p in c.products if p.is_active)
        result.append(
            {
                "category_id": c.category_id,
                "name": c.name,
                "department": c.department,
                "product_count": active_count,
            }
        )
    return result


def create_product(db: Session, actor: ActorContext, req: ProductCreateRequest) -> Dict[str, Any]:
    dept = req.department.strip().upper()
    if dept not in ("MEN", "WOMEN", "KIDS"):
        raise AppError("invalid_department", "Noir Atelier supports MEN, WOMEN, and KIDS garments only.", 422)
    if not req.hsn_code.startswith(("61", "62")):
        raise AppError("invalid_hsn", "Only HSN Chapter 61 and 62 garments are permitted.", 422)

    pid = req.product_id or next_entity_id(db, Product, Product.product_id, "product", start_seq=1)
    prod = Product(
        product_id=pid,
        sku=req.sku.strip().upper(),
        name=req.name.strip(),
        description=req.description.strip(),
        category_id=req.category_id.strip().upper(),
        department=dept,
        mrp_inr=req.mrp_inr,
        hsn_code=req.hsn_code,
        color=req.color,
        sizes_available=req.sizes_available,
        fit_guide=req.fit_guide,
        fabric_and_care=req.fabric_and_care,
        final_sale=req.final_sale,
        security_tag_required=True,
    )
    db.add(prod)
    default_img = "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?auto=format&fit=crop&w=900&q=80"
    db.add(ProductImage(product_id=pid, url=default_img, alt_text=f"{dept} Atelier Edition", display_order=1))
    db.add(
        Inventory(
            product_id=pid,
            quantity_available=req.initial_stock,
            quantity_reserved=0,
            quantity_damaged=0,
            size_breakdown={sz: max(1, req.initial_stock // max(1, len(req.sizes_available))) for sz in req.sizes_available},
        )
    )
    record_audit(db, actor, "product", pid, "create_product", {"sku": prod.sku, "mrp_inr": float(prod.mrp_inr)}, "admin_catalog_create")
    db.commit()
    db.refresh(prod)
    return serialize_product(prod, db)


def update_product(db: Session, actor: ActorContext, product_id: str, req: ProductUpdateRequest) -> Dict[str, Any]:
    prod = get_product_by_id_or_sku(db, product_id)
    changes: Dict[str, Any] = {}
    for field_name in ("name", "description", "mrp_inr", "fit_guide", "fabric_and_care", "final_sale"):
        val = getattr(req, field_name)
        if val is not None:
            setattr(prod, field_name, val)
            changes[field_name] = float(val) if isinstance(val, Decimal) else val

    record_audit(db, actor, "product", prod.product_id, "update_product", changes, "admin_catalog_update")
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
