from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import ActorContext, require_admin, require_agent_or_admin, resolve_actor
from ..database import get_db
from ..schemas.product_schema import (
    InventoryReserveRequest,
    InventoryUpdateRequest,
    ProductCreateRequest,
    ProductUpdateRequest,
)
from ..services.order_service import get_orders_analytics
from ..services.product_service import (
    create_product,
    discontinue_product,
    get_product_by_id_or_sku,
    get_product_recommendations,
    list_categories,
    list_inventory,
    search_products,
    serialize_product,
    update_inventory_stock,
    update_product,
)

router = APIRouter()


@router.get("/api/products/search")
def api_search_products(
    q: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    department: Optional[str] = Query(default=None),
    max_price: Optional[Decimal] = Query(default=None),
    in_stock_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(resolve_actor),
) -> List[Dict[str, Any]]:
    return search_products(
        db=db,
        q=q,
        category=category,
        department=department,
        max_price=max_price,
        in_stock_only=in_stock_only,
        limit=limit,
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
    _actor: ActorContext = Depends(resolve_actor),
) -> Dict[str, Any]:
    prod = get_product_by_id_or_sku(db, product_id)
    return serialize_product(prod, db)


@router.get("/api/products/{product_id}/recommendations")
def api_get_recommendations(
    product_id: str,
    limit: int = Query(default=4, ge=1, le=10),
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(resolve_actor),
) -> List[Dict[str, Any]]:
    return get_product_recommendations(db, product_id, limit=limit)


@router.post("/api/products", status_code=201)
def api_create_product(
    req: ProductCreateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_admin),
) -> Dict[str, Any]:
    return create_product(db, actor, req)


@router.put("/api/products/{product_id}")
def api_update_product(
    product_id: str,
    req: ProductUpdateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_admin),
) -> Dict[str, Any]:
    return update_product(db, actor, product_id, req)


@router.delete("/api/products/{product_id}")
@router.post("/api/products/{product_id}/discontinue")
def api_discontinue_product(
    product_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_agent_or_admin),
) -> Dict[str, Any]:
    return discontinue_product(db, actor, product_id)


@router.get("/api/categories")
def api_list_categories(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(resolve_actor),
) -> List[Dict[str, Any]]:
    return list_categories(db)


@router.get("/api/inventory/list")
def api_list_inventory(
    low_stock_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_agent_or_admin),
) -> List[Dict[str, Any]]:
    return list_inventory(db, low_stock_only=low_stock_only)


@router.put("/api/inventory/{product_id}")
def api_update_inventory(
    product_id: str,
    req: InventoryUpdateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_agent_or_admin),
) -> Dict[str, Any]:
    return update_inventory_stock(db, actor, product_id, req)


@router.post("/api/inventory/reserve")
def api_reserve_inventory(
    req: InventoryReserveRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_agent_or_admin),
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
    actor: ActorContext = Depends(require_agent_or_admin),
) -> Dict[str, Any]:
    prod = get_product_by_id_or_sku(db, req.product_id)
    assert prod.inventory is not None
    prod.inventory.quantity_available += req.quantity
    db.commit()
    return {
        "product_id": prod.product_id,
        "quantity_available": prod.inventory.quantity_available,
    }
