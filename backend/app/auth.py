from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Callable, Dict, FrozenSet, List, Optional
import uuid

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import AgentPermission, AuthSession, Customer, Role, RolePermission, StaffUser
from .reference_data import ROLE_PERMISSION_MAP
from .security import ACCESS_COOKIE_NAME, create_access_token_bundle, decode_access_token
from .utils.exceptions import AppError

_ROLE_PERM_CACHE: Dict[tuple, FrozenSet[str]] = {}


def invalidate_rbac_cache() -> None:
    _ROLE_PERM_CACHE.clear()


def get_role_permissions(db: Session, role_code: str) -> FrozenSet[str]:
    clean_role = (role_code or "anon").strip().lower()
    if clean_role == "anon":
        return frozenset({"catalog:read", "config:read"})

    cache_key = (id(db.get_bind()), clean_role)
    if cache_key in _ROLE_PERM_CACHE:
        return _ROLE_PERM_CACHE[cache_key]

    rows = db.scalars(
        select(RolePermission.permission_code)
        .join(Role, Role.code == RolePermission.role_code)
        .where(RolePermission.role_code == clean_role, Role.is_active.is_(True))
    ).all()
    if rows:
        perms = frozenset(rows)
    else:
        perms = frozenset(ROLE_PERMISSION_MAP.get(clean_role, []))

    _ROLE_PERM_CACHE[cache_key] = perms
    return perms


@dataclass
class ActorContext:
    actor_type: str
    actor_id: str
    role: str = "customer"
    on_behalf_of: Optional[str] = None
    trace_id: str = ""
    permissions: FrozenSet[str] = field(default_factory=frozenset)
    email: Optional[str] = None
    name: Optional[str] = None
    session_id: Optional[str] = None

    def has_permission(self, permission_code: str) -> bool:
        if self.role == "super_admin":
            return True
        return permission_code in self.permissions


def _generate_trace_id() -> str:
    num = uuid.uuid4().int % 900000 + 100000
    return f"TRC-{num:06d}"


def create_access_token(
    actor_id: str,
    actor_type: str = "customer",
    role: str = "customer",
    on_behalf_of: Optional[str] = None,
    ttl_minutes: Optional[int] = None,
    email: Optional[str] = None,
    name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    token, _, _ = create_access_token_bundle(
        actor_id=actor_id,
        actor_type=actor_type,
        role=role,
        email=email,
        name=name,
        session_id=session_id,
        on_behalf_of=on_behalf_of,
        ttl_minutes=ttl_minutes,
    )
    return token


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

    token: Optional[str] = None
    if authorization:
        parts = authorization.strip().split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
            raise AppError("invalid_auth_header", "Authorization header must be 'Bearer <token>'.", 401)
        token = parts[1].strip()
    else:
        cookie_tok = request.cookies.get(ACCESS_COOKIE_NAME)
        if cookie_tok and cookie_tok.strip():
            token = cookie_tok.strip()

    if not token:
        return ActorContext(
            actor_type="anon",
            actor_id="anon",
            role="anon",
            permissions=get_role_permissions(db, "anon"),
            trace_id=trace_id,
        )

    settings = get_settings()

    if settings.demo_mode:
        if token in ("demo_cust_001", "demo_CUS-001", "CUS-001"):
            return ActorContext(
                "customer",
                "CUS-001",
                "customer",
                trace_id=trace_id,
                permissions=get_role_permissions(db, "customer"),
            )
        if token in ("demo_cust_002", "demo_CUS-002", "CUS-002"):
            return ActorContext(
                "customer",
                "CUS-002",
                "customer",
                trace_id=trace_id,
                permissions=get_role_permissions(db, "customer"),
            )
        if token.startswith("svc-"):
            _verify_agent_permission(db, token, request.url.path)
            return ActorContext(
                actor_type="agent",
                actor_id=token,
                role="service_account",
                on_behalf_of=x_on_behalf_of,
                trace_id=trace_id,
                permissions=get_role_permissions(db, "service_account"),
            )
        if token in ("admin_manager", "manager_001"):
            return ActorContext(
                "admin",
                "MGR-001",
                "manager",
                trace_id=trace_id,
                permissions=get_role_permissions(db, "manager"),
            )
        if token in ("admin_finance", "finance_001"):
            return ActorContext(
                "admin",
                "FIN-001",
                "finance_admin",
                trace_id=trace_id,
                permissions=get_role_permissions(db, "finance_admin"),
            )
        if token in ("admin_root", "admin"):
            return ActorContext(
                "admin",
                "ADM-001",
                "super_admin",
                trace_id=trace_id,
                permissions=get_role_permissions(db, "super_admin"),
            )

    payload = decode_access_token(token)

    actor_type = str(payload.get("actor_type", "customer"))
    actor_id = str(payload.get("sub", ""))
    role = str(payload.get("role", "customer")).strip().lower()
    behalf = x_on_behalf_of or payload.get("on_behalf_of")
    session_id = payload.get("sid")
    jti = payload.get("jti")
    email = payload.get("email")
    name = payload.get("name")

    if session_id:
        auth_sess = db.scalar(select(AuthSession).where(AuthSession.session_id == str(session_id)))
        if auth_sess is None or auth_sess.revoked_at is not None:
            raise AppError("session_revoked", "Your session has been signed out or revoked.", 401)
        exp_at = auth_sess.expires_at
        if exp_at.tzinfo is None:
            exp_at = exp_at.replace(tzinfo=timezone.utc)
        if exp_at <= datetime.now(timezone.utc):
            raise AppError("session_expired", "Your session has expired. Please sign in again.", 401)
        if jti and auth_sess.access_jti != str(jti):
            raise AppError("token_superseded", "Access token has been superseded by a newer token.", 401)

    if actor_type == "customer":
        cust = db.scalar(select(Customer).where(Customer.customer_id == actor_id))
        if cust is not None:
            if not cust.is_active or cust.status != "active":
                raise AppError("account_suspended", "This client account is currently inactive or suspended.", 403)
            email = cust.email
            name = cust.name
            role = "customer"
    elif actor_type == "admin":
        staff = db.scalar(select(StaffUser).where(StaffUser.staff_id == actor_id))
        if staff is not None:
            if not staff.is_active or staff.status != "active":
                raise AppError("account_suspended", "This staff account is currently inactive or suspended.", 403)
            role = staff.role_code
            email = staff.email
            name = staff.name
    elif actor_type == "agent":
        _verify_agent_permission(db, actor_id, request.url.path)

    return ActorContext(
        actor_type=actor_type,
        actor_id=actor_id,
        role=role,
        on_behalf_of=behalf,
        trace_id=trace_id,
        permissions=get_role_permissions(db, role),
        email=email,
        name=name,
        session_id=str(session_id) if session_id else None,
    )


def require_authenticated(actor: ActorContext = Depends(resolve_actor)) -> ActorContext:
    if actor.actor_type == "anon":
        raise AppError("unauthorized", "Authentication token required.", 401)
    return actor


def resolve_optional_actor(
    request: Request,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
    x_on_behalf_of: Optional[str] = Header(default=None),
    x_trace_id: Optional[str] = Header(default=None),
) -> ActorContext:
    """Resolve actor if valid credentials exist; gracefully degrade to anon if expired/revoked."""
    try:
        return resolve_actor(
            request=request,
            db=db,
            authorization=authorization,
            x_on_behalf_of=x_on_behalf_of,
            x_trace_id=x_trace_id,
        )
    except AppError as exc:
        if exc.code in ("token_expired", "session_revoked", "session_expired", "token_superseded", "invalid_token"):
            trace_id = getattr(request.state, "trace_id", None) or _generate_trace_id()
            return ActorContext(
                actor_type="anon",
                actor_id="anon",
                role="anon",
                permissions=get_role_permissions(db, "anon"),
                trace_id=trace_id,
            )
        raise


def require_customer(actor: ActorContext = Depends(require_authenticated)) -> ActorContext:
    if actor.actor_type != "customer":
        raise AppError("forbidden_customer_only", "A client account is required for this operation.", 403)
    return actor


def require_admin(actor: ActorContext = Depends(resolve_actor)) -> ActorContext:
    if actor.actor_type == "anon":
        raise AppError("unauthorized", "Authentication token required.", 401)
    if actor.actor_type != "admin":
        raise AppError("forbidden_admin_only", "Admin privileges required for this operation.", 403)
    return actor


def require_agent_or_admin(actor: ActorContext = Depends(resolve_actor)) -> ActorContext:
    if actor.actor_type == "anon":
        raise AppError("unauthorized", "Authentication token required.", 401)
    if actor.actor_type not in ("agent", "admin"):
        raise AppError("forbidden", "Service account or Admin privileges required.", 403)
    return actor


def require_roles(*allowed_roles: str) -> Callable[[ActorContext], ActorContext]:
    normalized = {r.strip().lower() for r in allowed_roles}

    def _dependency(actor: ActorContext = Depends(require_authenticated)) -> ActorContext:
        if actor.role == "super_admin" or actor.role in normalized:
            return actor
        raise AppError(
            code="forbidden_insufficient_role",
            message=f"Role '{actor.role}' is not authorized for this resource.",
            status_code=403,
            details={"required_roles": sorted(normalized), "actor_role": actor.role},
        )

    return _dependency


def require_permissions(
    *required_permissions: str,
    allow_agent: bool = False,
) -> Callable[[ActorContext], ActorContext]:
    needed = tuple(p.strip().lower() for p in required_permissions if p.strip())

    def _dependency(actor: ActorContext = Depends(resolve_actor)) -> ActorContext:
        if actor.actor_type == "anon":
            raise AppError("unauthorized", "Authentication token required.", 401)
        if allow_agent and actor.actor_type == "agent":
            return actor
        missing = [perm for perm in needed if not actor.has_permission(perm)]
        if missing:
            raise AppError(
                code="forbidden_missing_permission",
                message=f"Role '{actor.role}' lacks required permission(s): {', '.join(missing)}.",
                status_code=403,
                details={
                    "required_permissions": list(needed),
                    "missing_permissions": missing,
                    "actor_role": actor.role,
                },
            )
        return actor

    return _dependency
