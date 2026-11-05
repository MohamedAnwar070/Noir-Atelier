"""Internal assistant traces: one structured record per turn (agent_traces).

Written by the chat endpoint after every turn; readable only by staff holding
`agents:trace_read` (see api/agents.py). Never returned to shoppers.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AgentTrace
from ..utils.exceptions import AppError

_FIELDS = (
    "trace_id", "session_id", "customer_id", "runtime", "model", "status", "intent", "plan_note",
    "user_message", "reply", "product_ids", "tool_calls", "evaluation", "errors", "usage", "latency_ms",
)


def save_trace(db: Session, record: Dict[str, Any]) -> AgentTrace:
    row = AgentTrace(**{key: record.get(key) for key in _FIELDS})
    row.product_ids = row.product_ids or []
    row.tool_calls = row.tool_calls or []
    row.evaluation = row.evaluation or {}
    row.errors = row.errors or []
    row.usage = row.usage or {}
    db.add(row)
    return row


def _summary(row: AgentTrace) -> Dict[str, Any]:
    return {
        "trace_id": row.trace_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "session_id": row.session_id,
        "customer_id": row.customer_id,
        "runtime": row.runtime,
        "model": row.model,
        "status": row.status,
        "intent": row.intent,
        "tool_count": len(row.tool_calls or []),
        "evaluation_passed": bool((row.evaluation or {}).get("passed")),
        "latency_ms": row.latency_ms,
        "user_message": (row.user_message or "")[:160],
    }


def list_traces(
    db: Session,
    *,
    session_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    before: Optional[datetime] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    stmt = select(AgentTrace).order_by(AgentTrace.created_at.desc(), AgentTrace.trace_id.desc())
    if session_id:
        stmt = stmt.where(AgentTrace.session_id == session_id)
    if customer_id:
        stmt = stmt.where(AgentTrace.customer_id == customer_id)
    if status:
        stmt = stmt.where(AgentTrace.status == status)
    if before:
        stmt = stmt.where(AgentTrace.created_at < before)
    return [_summary(r) for r in db.scalars(stmt.limit(max(1, min(limit, 200)))).all()]


def get_trace(db: Session, trace_id: str) -> Dict[str, Any]:
    row = db.get(AgentTrace, trace_id)
    if row is None:
        raise AppError("trace_not_found", f"Trace '{trace_id}' not found.", 404)
    return {**_summary(row), **{key: getattr(row, key) for key in _FIELDS}, "created_at": _summary(row)["created_at"]}
