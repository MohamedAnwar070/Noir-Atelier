import threading
from typing import Any, Dict, Optional, Type

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ActorContext
from ..models import AuditLog, IdempotencyKey
from ..utils.id_generator import PREFIX_MAP, format_short_id

_ID_LOCK = threading.RLock()
_HIGH_WATER: Dict[tuple, int] = {}


def next_entity_id(
    db: Session,
    model_cls: Type[Any],
    id_attr: Any,
    entity_type: str,
    start_seq: int = 1001,
) -> str:
    with _ID_LOCK:
        prefix, _ = PREFIX_MAP[entity_type]
        existing_ids = db.scalars(select(id_attr)).all()
        max_num = start_seq - 1
        for raw in existing_ids:
            if not raw or not str(raw).startswith(f"{prefix}-"):
                continue
            tail = str(raw).split("-", 1)[1]
            if tail.isdigit():
                max_num = max(max_num, int(tail))
        bind_key = (id(db.get_bind()), entity_type)
        prev_high = _HIGH_WATER.get(bind_key, start_seq - 1)
        if not existing_ids:
            prev_high = start_seq - 1
        next_num = max(max_num, prev_high) + 1
        _HIGH_WATER[bind_key] = next_num
        return format_short_id(entity_type, next_num)


def record_audit(
    db: Session,
    actor: ActorContext,
    resource_type: str,
    resource_id: str,
    action: str,
    change_details: Optional[Dict[str, Any]] = None,
    reason: Optional[str] = None,
) -> AuditLog:
    entry = AuditLog(
        trace_id=actor.trace_id or "TRC-000000",
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        on_behalf_of=actor.on_behalf_of,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        change_details=change_details or {},
        reason=reason,
    )
    db.add(entry)
    return entry


def get_idempotent_result(db: Session, request_key: Optional[str]) -> Optional[IdempotencyKey]:
    if not request_key or not request_key.strip():
        return None
    return db.scalar(select(IdempotencyKey).where(IdempotencyKey.request_key == request_key.strip()))


def save_idempotent_result(
    db: Session,
    request_key: Optional[str],
    actor_id: str,
    resource_type: str,
    resource_id: str,
    action: str,
    response_snapshot: Dict[str, Any],
) -> None:
    if not request_key or not request_key.strip():
        return
    record = IdempotencyKey(
        request_key=request_key.strip(),
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        response_snapshot=response_snapshot,
    )
    db.add(record)
