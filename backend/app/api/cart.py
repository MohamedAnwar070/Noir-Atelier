from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import ActorContext, require_authenticated, resolve_actor
from ..database import get_db
from ..schemas.cart_schema import CartAddRequest, CouponValidateRequest
from ..services.cart_service import (
    add_item_to_cart,
    clear_cart,
    get_cart_summary,
    remove_cart_item,
    validate_coupon_endpoint,
)

router = APIRouter()


@router.post("/api/cart/add")
def api_cart_add(
    req: CartAddRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return add_item_to_cart(db, actor, req)


@router.get("/api/cart")
def api_cart_get(
    session_id: Optional[str] = Query(default=None),
    customer_id: Optional[str] = Query(default=None),
    coupon_code: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return get_cart_summary(db, actor, session_id=session_id, customer_id=customer_id, coupon_code=coupon_code)


@router.delete("/api/cart/remove/{item_id}")
def api_cart_remove(
    item_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return remove_cart_item(db, actor, item_id)


@router.post("/api/cart/clear")
def api_cart_clear(
    session_id: Optional[str] = Query(default=None),
    customer_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return clear_cart(db, actor, session_id=session_id, customer_id=customer_id)


@router.post("/api/coupons/validate")
def api_validate_coupon(
    req: CouponValidateRequest,
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(resolve_actor),
) -> Dict[str, Any]:
    return validate_coupon_endpoint(db, req.code, req.cart_total_inr)
