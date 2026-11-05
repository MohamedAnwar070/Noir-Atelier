from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ActorContext, require_admin, require_permissions
from ..database import get_db
from ..models import SupportTicket
from ..schemas.auth_schema import (
    CustomerStatusUpdateRequest,
    StaffCreateRequest,
    StaffUpdateRequest,
)
from ..schemas.config_schema import ConfigUpdateRequest
from ..schemas.product_schema import (
    CategoryCreateRequest,
    ColorCreateRequest,
    DepartmentCreateRequest,
    MaterialCreateRequest,
    SynonymCreateRequest,
)
from ..services.auth_service import (
    create_staff_account_by_admin,
    get_rbac_matrix,
    list_all_users_for_governance,
    update_customer_account_status,
    update_staff_account,
)
from ..services.config_service import update_business_config
from ..services.customer_service import get_customers_analytics
from ..services.order_service import get_orders_analytics
from ..services.product_service import (
    create_catalog_category,
    create_catalog_color,
    create_catalog_department,
    create_catalog_material,
    create_search_synonym,
    delete_search_synonym,
    list_inventory,
    list_search_synonyms,
)
from ..services.returns_service import list_refunds

router = APIRouter()


@router.put("/api/admin/config/policies")
def api_update_config_policies(
    req: ConfigUpdateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("config:write", allow_agent=True)),
) -> Dict[str, Any]:
    return update_business_config(db, actor, req.config_key, req.config_value, req.reason)


@router.get("/api/admin/dashboard")
def api_admin_dashboard(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_admin),
) -> Dict[str, Any]:
    tickets = db.scalars(select(SupportTicket).order_by(SupportTicket.created_at.desc())).all()
    return {
        "actor_role": actor.role,
        "orders": get_orders_analytics(db) if actor.has_permission("orders:analytics") else {},
        "customers": get_customers_analytics(db) if actor.has_permission("customers:analytics") else {},
        "low_stock_alerts": list_inventory(db, low_stock_only=True) if actor.has_permission("inventory:read") else [],
        "recent_refunds": list_refunds(db)[:10] if actor.has_permission("returns:read_all") else [],
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
            for t in (tickets[:15] if actor.has_permission("support:read_all") else [])
        ],
    }


@router.post("/api/admin/inventory/sync")
def api_admin_inventory_sync(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_permissions("inventory:write")),
) -> Dict[str, Any]:
    items = list_inventory(db, low_stock_only=False)
    return {"status": "synced", "synced_skus": len(items)}


@router.get("/api/admin/catalog/synonyms")
def api_list_catalog_synonyms(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_admin),
) -> List[Dict[str, Any]]:
    return list_search_synonyms(db)


@router.post("/api/admin/catalog/synonyms", status_code=201)
def api_create_catalog_synonym(
    req: SynonymCreateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("catalog:manage_taxonomy")),
) -> Dict[str, Any]:
    return create_search_synonym(db, actor, req)


@router.delete("/api/admin/catalog/synonyms/{synonym_id}")
def api_delete_catalog_synonym(
    synonym_id: int,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("catalog:manage_taxonomy")),
) -> Dict[str, Any]:
    return delete_search_synonym(db, actor, synonym_id)


@router.post("/api/admin/catalog/colors", status_code=201)
def api_create_catalog_color(
    req: ColorCreateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("catalog:manage_taxonomy")),
) -> Dict[str, Any]:
    return create_catalog_color(db, actor, req)


@router.post("/api/admin/catalog/materials", status_code=201)
def api_create_catalog_material(
    req: MaterialCreateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("catalog:manage_taxonomy")),
) -> Dict[str, Any]:
    return create_catalog_material(db, actor, req)


@router.post("/api/admin/catalog/categories", status_code=201)
def api_create_catalog_category(
    req: CategoryCreateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("catalog:manage_taxonomy")),
) -> Dict[str, Any]:
    return create_catalog_category(db, actor, req)


@router.post("/api/admin/catalog/departments", status_code=201)
def api_create_catalog_department(
    req: DepartmentCreateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("catalog:manage_taxonomy")),
) -> Dict[str, Any]:
    return create_catalog_department(db, actor, req)


@router.get("/api/admin/rbac/matrix")
def api_get_rbac_matrix(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_admin),
) -> Dict[str, Any]:
    return get_rbac_matrix(db)


@router.get("/api/admin/users")
def api_list_governance_users(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_permissions("users:read")),
) -> Dict[str, Any]:
    return list_all_users_for_governance(db)


@router.post("/api/admin/users/staff", status_code=201)
def api_create_staff_user(
    req: StaffCreateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("users:manage_roles")),
) -> Dict[str, Any]:
    return create_staff_account_by_admin(db, actor, req)


@router.patch("/api/admin/users/staff/{staff_id}")
def api_update_staff_user(
    staff_id: str,
    req: StaffUpdateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("users:manage_roles")),
) -> Dict[str, Any]:
    return update_staff_account(db, actor, staff_id, req)


@router.patch("/api/admin/users/customers/{customer_id}/status")
def api_update_customer_status(
    customer_id: str,
    req: CustomerStatusUpdateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("users:manage_roles")),
) -> Dict[str, Any]:
    return update_customer_account_status(db, actor, customer_id, req)
