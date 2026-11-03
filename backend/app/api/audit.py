from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ActorContext, require_agent_or_admin
from ..database import get_db
from ..models import AuditLog
from ..services.audit_service import record_audit

router = APIRouter()


class AuditCreateRequest(BaseModel):
    resource_type: str
    resource_id: str
    action: str
    change_details: Dict[str, Any] = {}
    reason: Optional[str] = None


@router.get("/api/audit/log")
def api_get_audit_log(
    actor_type: Optional[str] = Query(default=None),
    actor_id: Optional[str] = Query(default=None),
    resource_type: Optional[str] = Query(default=None),
    resource_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_agent_or_admin),
) -> List[Dict[str, Any]]:
    stmt = select(AuditLog).order_by(AuditLog.log_id.desc())
    if actor_type:
        stmt = stmt.where(AuditLog.actor_type == actor_type)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if resource_id:
        stmt = stmt.where(AuditLog.resource_id == resource_id)

    rows = db.scalars(stmt.limit(limit)).all()
    return [
        {
            "log_id": r.log_id,
            "trace_id": r.trace_id,
            "timestamp": r.timestamp.isoformat(),
            "actor_type": r.actor_type,
            "actor_id": r.actor_id,
            "on_behalf_of": r.on_behalf_of,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "action": r.action,
            "change_details": r.change_details,
            "reason": r.reason,
        }
        for r in rows
    ]


@router.post("/api/audit/log", status_code=201)
def api_create_audit_log(
    req: AuditCreateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_agent_or_admin),
) -> Dict[str, Any]:
    row = record_audit(
        db=db,
        actor=actor,
        resource_type=req.resource_type,
        resource_id=req.resource_id,
        action=req.action,
        change_details=req.change_details,
        reason=req.reason,
    )
    db.commit()
    db.refresh(row)
    return {"log_id": row.log_id, "trace_id": row.trace_id, "action": row.action}
