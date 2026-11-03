from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import ActorContext, resolve_actor
from ..database import get_db
from ..services.config_service import get_policies_and_config, list_payment_methods

router = APIRouter()


@router.get("/api/config/policies")
def api_get_policies(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(resolve_actor),
) -> Dict[str, Any]:
    return get_policies_and_config(db)


@router.get("/api/config/payment-methods")
def api_get_payment_methods(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(resolve_actor),
) -> List[Dict[str, Any]]:
    return list_payment_methods(db)
