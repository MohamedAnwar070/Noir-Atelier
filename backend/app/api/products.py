from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import (
    ActorContext,
    require_admin,
    require_agent_or_admin,
    require_authenticated,
    require_permissions,
    resolve_actor,
    resolve_optional_actor,
)
from ..database import get_db
from ..schemas.product_schema import (
    InventoryReserveRequest,
    InventoryUpdateRequest,
    ProductCreateRequest,
    ProductReviewCreateRequest,
    ProductUpdateRequest,
    VariantUpdateRequest,
)
from ..services.order_service import get_orders_analytics
from ..services.product_service import (
    add_product_review,
    create_product,
    discontinue_product,
    get_catalog_meta,
    get_product_by_id_or_sku,
    get_product_recommendations,
    list_categories,
    list_inventory,
    search_products,
    serialize_product,
    update_inventory_stock,
    update_product,
    update_variant,
)
from ..services.search_service import search_catalog

router = APIRouter()


@router.get("/api/catalog/meta")
def api_get_catalog_meta(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(resolve_optional_actor),
) -> Dict[str, Any]:
    return get_catalog_meta(db)


@router.get("/api/catalog/search")
def api_search_catalog(
    q: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    department: Optional[str] = Query(default=None),
    color: Optional[str] = Query(default=None),
    material: Optional[str] = Query(default=None),
    min_price: Optional[Decimal] = Query(default=None),
    max_price: Optional[Decimal] = Query(default=None),
    in_stock_only: bool = Query(default=False),
    sort: str = Query(default="featured"),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(resolve_optional_actor),
) -> Dict[str, Any]:
    return search_catalog(
        db=db,
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


@router.get("/api/products/search")
def api_search_products(
    q: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    department: Optional[str] = Query(default=None),
    color: Optional[str] = Query(default=None),
    material: Optional[str] = Query(default=None),
    min_price: Optional[Decimal] = Query(default=None),
    max_price: Optional[Decimal] = Query(default=None),
    in_stock_only: bool = Query(default=False),
    sort: str = Query(default="featured"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(resolve_optional_actor),
) -> List[Dict[str, Any]]:
    return search_products(
        db=db,
        q=q,
        category=category,
        department=department,
        color=color,
        material=material,
        min_price=min_price,
        max_price=max_price,
        in_stock_only=in_stock_only,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/api/products/analytics")
def api_products_analytics(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_agent_or_admin),
) -> Dict[str, Any]:
    return {
        "inventory": list_inventory(db, low_stock_only=False),
        "sales": get_orders_analytics(db),
    }


@router.get("/api/products/{product_id}")
def api_get_product(
    product_id: str,
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(resolve_optional_actor),
) -> Dict[str, Any]:
    prod = get_product_by_id_or_sku(db, product_id)
    return serialize_product(prod, db)


@router.get("/api/products/{product_id}/recommendations")
def api_get_recommendations(
    product_id: str,
    limit: int = Query(default=4, ge=1, le=10),
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(resolve_optional_actor),
) -> List[Dict[str, Any]]:
    return get_product_recommendations(db, product_id, limit=limit)


@router.post("/api/products/{product_id}/reviews", status_code=201)
def api_create_product_review(
    product_id: str,
    req: ProductReviewCreateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return add_product_review(db, actor, product_id, req.rating, req.fit_feedback, req.comment)


@router.post("/api/products", status_code=201)
def api_create_product(
    req: ProductCreateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("catalog:write")),
) -> Dict[str, Any]:
    return create_product(db, actor, req)


@router.put("/api/products/{product_id}")
def api_update_product(
    product_id: str,
    req: ProductUpdateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("catalog:write")),
) -> Dict[str, Any]:
    return update_product(db, actor, product_id, req)


@router.put("/api/products/{product_id}/variants/{size}")
def api_update_variant(
    product_id: str,
    size: str,
    req: VariantUpdateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("catalog:write")),
) -> Dict[str, Any]:
    """Set the price of one size (adds the size if new) and/or retire it."""
    return update_variant(db, actor, product_id, size, req)


@router.delete("/api/products/{product_id}")
@router.post("/api/products/{product_id}/discontinue")
def api_discontinue_product(
    product_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("catalog:write", allow_agent=True)),
) -> Dict[str, Any]:
    return discontinue_product(db, actor, product_id)


@router.get("/api/categories")
def api_list_categories(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(resolve_optional_actor),
) -> List[Dict[str, Any]]:
    return list_categories(db)


@router.get("/api/inventory/list")
def api_list_inventory(
    low_stock_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_permissions("inventory:read", allow_agent=True)),
) -> List[Dict[str, Any]]:
    return list_inventory(db, low_stock_only=low_stock_only)


@router.put("/api/inventory/{product_id}")
def api_update_inventory(
    product_id: str,
    req: InventoryUpdateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("inventory:write", allow_agent=True)),
) -> Dict[str, Any]:
    return update_inventory_stock(db, actor, product_id, req)


@router.post("/api/inventory/reserve")
def api_reserve_inventory(
    req: InventoryReserveRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("inventory:write", allow_agent=True)),
) -> Dict[str, Any]:
    prod = get_product_by_id_or_sku(db, req.product_id)
    assert prod.inventory is not None
    prod.inventory.quantity_available = max(0, prod.inventory.quantity_available - req.quantity)
    prod.inventory.quantity_reserved += req.quantity
    db.commit()
    return {
        "product_id": prod.product_id,
        "quantity_available": prod.inventory.quantity_available,
        "quantity_reserved": prod.inventory.quantity_reserved,
    }


@router.post("/api/inventory/restock")
def api_restock_inventory(
    req: InventoryReserveRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("inventory:write", allow_agent=True)),
) -> Dict[str, Any]:
    prod = get_product_by_id_or_sku(db, req.product_id)
    assert prod.inventory is not None
    prod.inventory.quantity_available += req.quantity
    db.commit()
    return {
        "product_id": prod.product_id,
        "quantity_available": prod.inventory.quantity_available,
    }
