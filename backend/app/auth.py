from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import List, Optional
import uuid

from fastapi import Depends, Header, Request
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import AgentPermission
from .utils.exceptions import AppError


@dataclass
class ActorContext:
    actor_type: str
    actor_id: str
    role: str = "customer"
    on_behalf_of: Optional[str] = None
    trace_id: str = ""


def _generate_trace_id() -> str:
    num = uuid.uuid4().int % 900000 + 100000
    return f"TRC-{num:06d}"


def create_access_token(
    actor_id: str,
    actor_type: str = "customer",
    role: str = "customer",
    on_behalf_of: Optional[str] = None,
    ttl_minutes: Optional[int] = None,
) -> str:
    settings = get_settings()
    exp_min = ttl_minutes or settings.access_token_ttl_min
    now = datetime.now(timezone.utc)
    payload = {
        "sub": actor_id,
        "actor_type": actor_type,
        "role": role,
        "on_behalf_of": on_behalf_of,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=exp_min)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _match_endpoint_pattern(pattern: str, actual_path: str) -> bool:
    regex_str = "^" + re.sub(r"\{[^/]+\}", r"[^/]+", pattern.rstrip("/")) + "/?$"
    return bool(re.match(regex_str, actual_path.rstrip("/") or "/"))


def _verify_agent_permission(db: Session, service_account: str, request_path: str) -> None:
    perms = db.scalars(
        select(AgentPermission).where(AgentPermission.service_account == service_account)
    ).all()
    if not perms:
        raise AppError(
            code="unknown_service_account",
            message=f"Service account '{service_account}' is not registered in agent_permissions.",
            status_code=403,
        )
    allowed: List[str] = []
    for p in perms:
        allowed.extend(p.allowed_endpoints or [])

    if not any(_match_endpoint_pattern(pat, request_path) for pat in allowed):
        raise AppError(
            code="agent_permission_denied",
            message=f"Service account '{service_account}' is not whitelisted for '{request_path}'.",
            status_code=403,
        )


def resolve_actor(
    request: Request,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
    x_on_behalf_of: Optional[str] = Header(default=None),
    x_trace_id: Optional[str] = Header(default=None),
) -> ActorContext:
    trace_id = x_trace_id or getattr(request.state, "trace_id", None) or _generate_trace_id()
    request.state.trace_id = trace_id

    if not authorization:
        return ActorContext(actor_type="anon", actor_id="anon", role="anon", trace_id=trace_id)

    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AppError("invalid_auth_header", "Authorization header must be 'Bearer <token>'.", 401)

    token = parts[1].strip()
    settings = get_settings()

    if settings.demo_mode:
        if token in ("demo_cust_001", "demo_CUS-001", "CUS-001"):
            return ActorContext("customer", "CUS-001", "customer", trace_id=trace_id)
        if token in ("demo_cust_002", "demo_CUS-002", "CUS-002"):
            return ActorContext("customer", "CUS-002", "customer", trace_id=trace_id)
        if token.startswith("svc-"):
            _verify_agent_permission(db, token, request.url.path)
            return ActorContext(
                actor_type="agent",
                actor_id=token,
                role="service_account",
                on_behalf_of=x_on_behalf_of,
                trace_id=trace_id,
            )
        if token in ("admin_manager", "manager_001"):
            return ActorContext("admin", "MGR-001", "manager", trace_id=trace_id)
        if token in ("admin_finance", "finance_001"):
            return ActorContext("admin", "FIN-001", "finance_admin", trace_id=trace_id)
        if token in ("admin_root", "admin"):
            return ActorContext("admin", "ADM-001", "super_admin", trace_id=trace_id)

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise AppError("invalid_token", f"Invalid or expired token: {exc}", 401) from exc

    actor_type = str(payload.get("actor_type", "customer"))
    actor_id = str(payload.get("sub", ""))
    role = str(payload.get("role", "customer"))
    behalf = x_on_behalf_of or payload.get("on_behalf_of")

    if actor_type == "agent":
        _verify_agent_permission(db, actor_id, request.url.path)

    return ActorContext(
        actor_type=actor_type,
        actor_id=actor_id,
        role=role,
        on_behalf_of=behalf,
        trace_id=trace_id,
    )


def require_authenticated(actor: ActorContext = Depends(resolve_actor)) -> ActorContext:
    if actor.actor_type == "anon":
        raise AppError("unauthorized", "Authentication token required.", 401)
    return actor


def require_admin(actor: ActorContext = Depends(resolve_actor)) -> ActorContext:
    if actor.actor_type != "admin":
        raise AppError("forbidden_admin_only", "Admin privileges required for this operation.", 403)
    return actor


def require_agent_or_admin(actor: ActorContext = Depends(resolve_actor)) -> ActorContext:
    if actor.actor_type not in ("agent", "admin"):
        raise AppError("forbidden", "Service account or Admin privileges required.", 403)
    return actor
