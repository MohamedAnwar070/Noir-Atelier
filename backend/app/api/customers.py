from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import ActorContext, require_agent_or_admin, require_authenticated, resolve_actor
from ..database import get_db
from ..schemas.config_schema import (
    AddressCreateRequest,
    CustomerCreateRequest,
    CustomerUpdateRequest,
)
from ..services.customer_service import (
    add_customer_address,
    get_customer_preferences,
    get_customer_profile,
    get_customers_analytics,
    list_customer_addresses,
    register_customer,
    update_customer_profile,
)

router = APIRouter()


@router.post("/api/customers/register", status_code=201)
def api_register_customer(
    req: CustomerCreateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
) -> Dict[str, Any]:
    return register_customer(db, actor, req)


@router.get("/api/customers/analytics")
def api_customers_analytics(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_agent_or_admin),
) -> Dict[str, Any]:
    return get_customers_analytics(db)


@router.get("/api/customers/{customer_id}")
def api_get_customer(
    customer_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return get_customer_profile(db, actor, customer_id)


@router.put("/api/customers/{customer_id}")
def api_update_customer(
    customer_id: str,
    req: CustomerUpdateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return update_customer_profile(db, actor, customer_id, req)


@router.get("/api/customers/{customer_id}/addresses")
def api_list_addresses(
    customer_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> List[Dict[str, Any]]:
    return list_customer_addresses(db, actor, customer_id)


@router.post("/api/customers/{customer_id}/addresses", status_code=201)
def api_add_address(
    customer_id: str,
    req: AddressCreateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return add_customer_address(db, actor, customer_id, req)


@router.get("/api/customers/{customer_id}/preferences")
def api_get_preferences(
    customer_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return get_customer_preferences(db, actor, customer_id)
