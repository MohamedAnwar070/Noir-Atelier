from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ActorContext, require_authenticated, resolve_optional_actor
from ..database import get_db
from ..models import Role
from ..schemas.auth_schema import (
    AdminRegisterRequest,
    CustomerRegisterRequest,
    LoginRequest,
    LogoutRequest,
    PasswordChangeRequest,
    RefreshTokenRequest,
)
from ..security import (
    REFRESH_COOKIE_NAME,
    auth_rate_limiter,
    clear_auth_cookies,
    extract_client_meta,
    set_auth_cookies,
)
from ..services.auth_service import (
    authenticate_user,
    change_user_password,
    get_authenticated_profile,
    list_user_sessions,
    logout_all_sessions,
    logout_session,
    refresh_user_session,
    register_admin_account,
    register_customer_account,
    revoke_user_session,
)

router = APIRouter()


@router.get("/api/auth/roles")
def api_list_public_roles(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(resolve_optional_actor),
) -> List[Dict[str, Any]]:
    rows = db.scalars(
        select(Role)
        .where(Role.is_active.is_(True), Role.actor_type.in_(("customer", "admin")))
        .order_by(Role.hierarchy_level.asc())
    ).all()
    return [
        {
            "code": r.code,
            "name": r.name,
            "description": r.description,
            "actor_type": r.actor_type,
            "hierarchy_level": r.hierarchy_level,
        }
        for r in rows
    ]


@router.post("/api/auth/register", status_code=201)
def api_auth_register_customer(
    req: CustomerRegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_optional_actor),
) -> Dict[str, Any]:
    ip_addr, user_agent = extract_client_meta(request)
    auth_rate_limiter.check(f"register:{ip_addr or 'local'}")
    result = register_customer_account(db, actor, req, ip_address=ip_addr, user_agent=user_agent)
    tokens = result["tokens"]
    set_auth_cookies(
        response,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        access_max_age_sec=tokens["expires_in"],
        refresh_max_age_sec=tokens["refresh_expires_in"],
    )
    return result


@router.post("/api/auth/register/admin", status_code=201)
def api_auth_register_admin(
    req: AdminRegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_optional_actor),
) -> Dict[str, Any]:
    ip_addr, user_agent = extract_client_meta(request)
    auth_rate_limiter.check(f"register_admin:{ip_addr or 'local'}")
    caller_is_super = actor.actor_type == "admin" and actor.has_permission("users:manage_roles")
    result = register_admin_account(
        db,
        actor,
        req,
        ip_address=ip_addr,
        user_agent=user_agent,
        issue_session=not caller_is_super,
    )
    tokens = result.get("tokens")
    if tokens:
        set_auth_cookies(
            response,
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            access_max_age_sec=tokens["expires_in"],
            refresh_max_age_sec=tokens["refresh_expires_in"],
        )
    return result


@router.post("/api/auth/login")
def api_auth_login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_optional_actor),
) -> Dict[str, Any]:
    ip_addr, user_agent = extract_client_meta(request)
    auth_rate_limiter.check(f"login:{ip_addr or 'local'}:{req.email}")
    result = authenticate_user(db, actor, req, ip_address=ip_addr, user_agent=user_agent)
    tokens = result["tokens"]
    set_auth_cookies(
        response,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        access_max_age_sec=tokens["expires_in"],
        refresh_max_age_sec=tokens["refresh_expires_in"],
    )
    return result


@router.post("/api/auth/refresh")
def api_auth_refresh(
    request: Request,
    response: Response,
    req: Optional[RefreshTokenRequest] = None,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_optional_actor),
) -> Dict[str, Any]:
    ip_addr, user_agent = extract_client_meta(request)
    raw_refresh = (req.refresh_token if req and req.refresh_token else None) or request.cookies.get(REFRESH_COOKIE_NAME)
    result = refresh_user_session(
        db=db,
        trace_id=actor.trace_id,
        raw_refresh_token=raw_refresh,
        ip_address=ip_addr,
        user_agent=user_agent,
    )
    tokens = result["tokens"]
    set_auth_cookies(
        response,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        access_max_age_sec=tokens["expires_in"],
        refresh_max_age_sec=tokens["refresh_expires_in"],
    )
    return result


@router.post("/api/auth/logout")
def api_auth_logout(
    request: Request,
    response: Response,
    req: Optional[LogoutRequest] = None,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_optional_actor),
) -> Dict[str, Any]:
    raw_refresh = (req.refresh_token if req and req.refresh_token else None) or request.cookies.get(REFRESH_COOKIE_NAME)
    result = logout_session(db, actor, raw_refresh_token=raw_refresh)
    clear_auth_cookies(response)
    return result


@router.post("/api/auth/logout-all")
def api_auth_logout_all(
    response: Response,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    result = logout_all_sessions(db, actor)
    clear_auth_cookies(response)
    return result


@router.get("/api/auth/me")
def api_auth_me(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return get_authenticated_profile(db, actor)


@router.get("/api/auth/sessions")
def api_auth_list_sessions(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> List[Dict[str, Any]]:
    return list_user_sessions(db, actor)


@router.delete("/api/auth/sessions/{session_id}")
def api_auth_revoke_session(
    session_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return revoke_user_session(db, actor, session_id)


@router.post("/api/auth/change-password")
def api_auth_change_password(
    req: PasswordChangeRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return change_user_password(db, actor, req)
