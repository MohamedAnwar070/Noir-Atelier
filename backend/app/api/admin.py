from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ActorContext, require_admin, require_agent_or_admin
from ..database import get_db
from ..models import SupportTicket
from ..schemas.config_schema import ConfigUpdateRequest
from ..services.config_service import update_business_config
from ..services.customer_service import get_customers_analytics
from ..services.order_service import get_orders_analytics
from ..services.product_service import list_inventory
from ..services.returns_service import list_refunds

router = APIRouter()


@router.put("/api/admin/config/policies")
def api_update_config_policies(
    req: ConfigUpdateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_agent_or_admin),
) -> Dict[str, Any]:
    return update_business_config(db, actor, req.config_key, req.config_value, req.reason)


@router.get("/api/admin/dashboard")
def api_admin_dashboard(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_admin),
) -> Dict[str, Any]:
    tickets = db.scalars(select(SupportTicket).order_by(SupportTicket.created_at.desc())).all()
    return {
        "orders": get_orders_analytics(db),
        "customers": get_customers_analytics(db),
        "low_stock_alerts": list_inventory(db, low_stock_only=True),
        "recent_refunds": list_refunds(db)[:10],
        "support_tickets": [
            {
                "ticket_id": t.ticket_id,
                "customer_id": t.customer_id,
                "order_id": t.order_id,
                "subject": t.subject,
                "description": t.description,
                "category": t.category,
                "priority": t.priority,
                "status": t.status,
            }
            for t in tickets[:15]
        ],
    }


@router.post("/api/admin/inventory/sync")
def api_admin_inventory_sync(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_admin),
) -> Dict[str, Any]:
    items = list_inventory(db, low_stock_only=False)
    return {"status": "synced", "synced_skus": len(items)}
