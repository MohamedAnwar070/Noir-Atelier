from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ActorContext, require_admin, require_agent_or_admin, require_authenticated, require_permissions
from ..database import get_db
from ..models import SupportTicket
from ..schemas.return_schema import (
    RefundApproveRequest,
    ReturnCreateRequest,
    SupportEscalateRequest,
)
from ..services.audit_service import record_audit
from ..services.returns_service import (
    approve_refund,
    create_support_escalation,
    get_return_status,
    initiate_return,
    list_refunds,
    process_refund_payout,
)
from ..utils.exceptions import AppError

router = APIRouter()


@router.post("/api/returns", status_code=201)
def api_initiate_return(
    req: ReturnCreateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return initiate_return(db, actor, req)


@router.get("/api/returns/{return_id}")
def api_get_return(
    return_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return get_return_status(db, actor, return_id)


@router.post("/api/refunds/{refund_id}/approve")
def api_approve_refund(
    refund_id: str,
    req: RefundApproveRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_agent_or_admin),
) -> Dict[str, Any]:
    return approve_refund(db, actor, refund_id, req)


@router.post("/api/refunds/{refund_id}/process")
def api_process_refund(
    refund_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_agent_or_admin),
) -> Dict[str, Any]:
    return process_refund_payout(db, actor, refund_id)


@router.get("/api/refunds")
def api_list_refunds(
    order_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_agent_or_admin),
) -> List[Dict[str, Any]]:
    return list_refunds(db, order_id=order_id)


@router.post("/api/support/escalate", status_code=201)
def api_support_escalate(
    req: SupportEscalateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return create_support_escalation(db, actor, req)


@router.get("/api/support/tickets")
def api_list_tickets(
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_permissions("support:read_all")),
) -> List[Dict[str, Any]]:
    stmt = select(SupportTicket).order_by(SupportTicket.created_at.desc())
    if status:
        stmt = stmt.where(SupportTicket.status == status)
    rows = db.scalars(stmt).all()
    return [
        {
            "ticket_id": t.ticket_id,
            "customer_id": t.customer_id,
            "order_id": t.order_id,
            "subject": t.subject,
            "description": t.description,
            "category": t.category,
            "priority": t.priority,
            "status": t.status,
            "created_by": t.created_by,
            "assigned_to": t.assigned_to,
        }
        for t in rows
    ]


@router.post("/api/support/tickets/{ticket_id}/resolve")
def api_resolve_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("support:resolve")),
) -> Dict[str, Any]:
    tkt = db.scalar(select(SupportTicket).where(SupportTicket.ticket_id == ticket_id.strip().upper()))
    if tkt is None:
        raise AppError("ticket_not_found", f"Support ticket '{ticket_id}' not found.", 404)
    tkt.status = "resolved"
    tkt.resolved_at = datetime.now(timezone.utc)
    record_audit(db, actor, "support_ticket", tkt.ticket_id, "resolve_ticket", {"status": "resolved"}, "admin_resolved")
    db.commit()
    return {"ticket_id": tkt.ticket_id, "status": tkt.status, "resolved_at": tkt.resolved_at.isoformat()}
