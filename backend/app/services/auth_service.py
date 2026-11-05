from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import ActorContext, get_role_permissions, invalidate_rbac_cache
from ..config import get_settings
from ..models import (
    AuthSession,
    Customer,
    CustomerPreference,
    Permission,
    Role,
    RolePermission,
    StaffUser,
)
from ..schemas.auth_schema import (
    AdminRegisterRequest,
    CustomerRegisterRequest,
    CustomerStatusUpdateRequest,
    LoginRequest,
    PasswordChangeRequest,
    StaffCreateRequest,
    StaffUpdateRequest,
)
from ..security import (
    constant_time_equals,
    create_access_token_bundle,
    create_refresh_token_bundle,
    decode_refresh_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
    verify_password_constant_time,
)
from ..utils.exceptions import AppError
from .audit_service import next_entity_id, record_audit
from .config_service import invalidate_config_cache


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_tz(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _get_role_meta(db: Session, role_code: str) -> Optional[Role]:
    return db.scalar(select(Role).where(Role.code == role_code.strip().lower()))


def _serialize_customer_user(db: Session, cust: Customer) -> Dict[str, Any]:
    role_row = _get_role_meta(db, "customer")
    return {
        "id": cust.customer_id,
        "customer_id": cust.customer_id,
        "actor_type": "customer",
        "role": "customer",
        "role_name": role_row.name if role_row else "Maison Client",
        "hierarchy_level": role_row.hierarchy_level if role_row else 10,
        "is_staff": False,
        "name": cust.name,
        "email": cust.email,
        "phone": cust.phone,
        "loyalty_tier": cust.loyalty_tier,
        "status": cust.status,
        "last_login": cust.last_login.isoformat() if cust.last_login else None,
        "created_at": cust.created_at.isoformat() if cust.created_at else None,
    }


def _serialize_staff_user(db: Session, staff: StaffUser) -> Dict[str, Any]:
    role_row = _get_role_meta(db, staff.role_code)
    return {
        "id": staff.staff_id,
        "staff_id": staff.staff_id,
        "actor_type": "admin",
        "role": staff.role_code,
        "role_name": role_row.name if role_row else staff.role_code.replace("_", " ").title(),
        "hierarchy_level": role_row.hierarchy_level if role_row else 50,
        "is_staff": True,
        "name": staff.name,
        "email": staff.email,
        "phone": staff.phone,
        "department_scope": staff.department_scope,
        "loyalty_tier": "STAFF",
        "status": staff.status,
        "last_login": staff.last_login.isoformat() if staff.last_login else None,
        "created_at": staff.created_at.isoformat() if staff.created_at else None,
    }


def _issue_session_bundle(
    db: Session,
    actor_type: str,
    actor_id: str,
    role_code: str,
    email: str,
    name: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    token_family: Optional[str] = None,
) -> Tuple[AuthSession, Dict[str, Any]]:
    settings = get_settings()
    session_id = f"SES-{uuid.uuid4().hex[:16].upper()}"
    family = token_family or str(uuid.uuid4())

    access_token, access_jti, access_ttl_sec = create_access_token_bundle(
        actor_id=actor_id,
        actor_type=actor_type,
        role=role_code,
        email=email,
        name=name,
        session_id=session_id,
    )
    refresh_token, refresh_exp_dt = create_refresh_token_bundle(
        actor_id=actor_id,
        actor_type=actor_type,
        role=role_code,
        session_id=session_id,
        token_family=family,
    )
    refresh_ttl_sec = int(settings.refresh_token_ttl_days * 86400)

    session_row = AuthSession(
        session_id=session_id,
        token_family=family,
        actor_type=actor_type,
        actor_id=actor_id,
        role_code=role_code,
        refresh_token_hash=hash_token(refresh_token),
        access_jti=access_jti,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=refresh_exp_dt,
        last_used_at=_utc_now(),
    )
    db.add(session_row)

    tokens_payload = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": access_ttl_sec,
        "refresh_expires_in": refresh_ttl_sec,
    }
    return session_row, tokens_payload


def _assert_email_available(db: Session, email: str) -> None:
    normalized = email.strip().lower()
    existing_cust = db.scalar(select(Customer).where(func.lower(Customer.email) == normalized))
    existing_staff = db.scalar(select(StaffUser).where(func.lower(StaffUser.email) == normalized))
    if existing_cust or existing_staff:
        raise AppError(
            code="email_already_registered",
            message=f"An account with email '{normalized}' is already registered.",
            status_code=409,
        )


def _revoke_all_actor_sessions(
    db: Session,
    actor_type: str,
    actor_id: str,
    reason: str,
    exclude_session_id: Optional[str] = None,
) -> int:
    now = _utc_now()
    stmt = select(AuthSession).where(
        AuthSession.actor_type == actor_type,
        AuthSession.actor_id == actor_id,
        AuthSession.revoked_at.is_(None),
    )
    rows = db.scalars(stmt).all()
    count = 0
    for row in rows:
        if exclude_session_id and row.session_id == exclude_session_id:
            continue
        row.revoked_at = now
        row.revoke_reason = reason
        count += 1
    return count


def register_customer_account(
    db: Session,
    actor: ActorContext,
    req: CustomerRegisterRequest,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    _assert_email_available(db, req.email)

    cid = next_entity_id(db, Customer, Customer.customer_id, "customer", start_seq=1)
    now = _utc_now()
    cust = Customer(
        customer_id=cid,
        name=req.name,
        email=req.email,
        phone=req.phone,
        password_hash=hash_password(req.password),
        loyalty_tier="STANDARD",
        status="active",
        last_login=now,
    )
    db.add(cust)

    pref_dept = req.preferred_department.strip().upper() if req.preferred_department else None
    db.add(
        CustomerPreference(
            customer_id=cid,
            preferred_department=pref_dept,
            dpdp_consent=True,
            referral_code=f"NOIR-{cid}",
        )
    )
    db.flush()

    session_row, tokens = _issue_session_bundle(
        db=db,
        actor_type="customer",
        actor_id=cid,
        role_code="customer",
        email=cust.email,
        name=cust.name,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    audit_actor = ActorContext(
        actor_type="customer",
        actor_id=cid,
        role="customer",
        trace_id=actor.trace_id,
    )
    record_audit(
        db,
        audit_actor,
        "customer",
        cid,
        "auth_register_customer",
        {"email": cust.email, "ip": ip_address},
        "client_self_registration",
    )
    db.commit()
    invalidate_config_cache()

    perms = sorted(get_role_permissions(db, "customer"))
    return {
        "user": _serialize_customer_user(db, cust),
        "tokens": tokens,
        "permissions": perms,
        "session": {
            "session_id": session_row.session_id,
            "expires_at": session_row.expires_at.isoformat(),
        },
    }


def register_admin_account(
    db: Session,
    actor: ActorContext,
    req: AdminRegisterRequest,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    issue_session: bool = True,
) -> Dict[str, Any]:
    settings = get_settings()
    caller_authorized = actor.actor_type == "admin" and actor.has_permission("users:manage_roles")
    invite_valid = constant_time_equals(req.invite_code, settings.admin_invite_code)

    if not caller_authorized and not invite_valid:
        raise AppError(
            code="invalid_admin_invite_code",
            message="Valid Maison Admin Provisioning Code or Super Admin authorization is required.",
            status_code=403,
        )

    role_row = db.scalar(
        select(Role).where(
            Role.code == req.role_code,
            Role.actor_type == "admin",
            Role.is_active.is_(True),
        )
    )
    if role_row is None:
        valid_admin_roles = sorted(
            db.scalars(select(Role.code).where(Role.actor_type == "admin", Role.is_active.is_(True))).all()
        )
        raise AppError(
            code="invalid_staff_role",
            message=f"Role '{req.role_code}' is not a valid staff role.",
            status_code=422,
            details={"allowed_roles": valid_admin_roles},
        )

    _assert_email_available(db, req.email)

    entity_kind = "admin" if req.role_code == "super_admin" else "staff"
    staff_id = next_entity_id(db, StaffUser, StaffUser.staff_id, entity_kind, start_seq=1)
    now = _utc_now()
    staff = StaffUser(
        staff_id=staff_id,
        name=req.name,
        email=req.email,
        phone=req.phone,
        password_hash=hash_password(req.password),
        role_code=role_row.code,
        department_scope=req.department_scope.strip().upper() if req.department_scope else None,
        status="active",
        last_login=now if issue_session else None,
    )
    db.add(staff)
    db.flush()

    tokens: Optional[Dict[str, Any]] = None
    session_payload: Optional[Dict[str, Any]] = None
    if issue_session:
        session_row, tokens = _issue_session_bundle(
            db=db,
            actor_type="admin",
            actor_id=staff_id,
            role_code=staff.role_code,
            email=staff.email,
            name=staff.name,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        session_payload = {
            "session_id": session_row.session_id,
            "expires_at": session_row.expires_at.isoformat(),
        }

    audit_actor = (
        actor
        if caller_authorized
        else ActorContext(actor_type="admin", actor_id=staff_id, role=staff.role_code, trace_id=actor.trace_id)
    )
    record_audit(
        db,
        audit_actor,
        "staff_user",
        staff_id,
        "auth_register_admin",
        {"email": staff.email, "role_code": staff.role_code, "provisioned_by": actor.actor_id},
        "staff_account_provisioning",
    )
    db.commit()
    invalidate_config_cache()

    perms = sorted(get_role_permissions(db, staff.role_code))
    result: Dict[str, Any] = {
        "user": _serialize_staff_user(db, staff),
        "permissions": perms,
    }
    if tokens is not None:
        result["tokens"] = tokens
    if session_payload is not None:
        result["session"] = session_payload
    return result


def authenticate_user(
    db: Session,
    actor: ActorContext,
    req: LoginRequest,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    settings = get_settings()
    now = _utc_now()
    email = req.email.strip().lower()

    staff: Optional[StaffUser] = None
    cust: Optional[Customer] = None

    if req.portal in ("auto", "admin"):
        staff = db.scalar(select(StaffUser).where(func.lower(StaffUser.email) == email))
    if staff is None and req.portal in ("auto", "customer"):
        cust = db.scalar(select(Customer).where(func.lower(Customer.email) == email))

    target: Any = staff or cust
    target_type = "admin" if staff is not None else "customer"

    if target is None:
        verify_password_constant_time(req.password, None)
        raise AppError(
            code="invalid_credentials",
            message="Invalid email address or password.",
            status_code=401,
        )

    if not target.is_active or target.status == "suspended":
        raise AppError(
            code="account_suspended",
            message="This account has been suspended. Please contact Noir Atelier Client Governance.",
            status_code=403,
        )

    locked_until = _ensure_tz(target.locked_until)
    if locked_until is not None:
        if locked_until > now:
            remaining_min = max(1, int((locked_until - now).total_seconds() // 60) + 1)
            raise AppError(
                code="account_locked",
                message=f"Account temporarily locked due to repeated failed attempts. Try again in {remaining_min} minute(s).",
                status_code=423,
                details={"locked_until": locked_until.isoformat()},
            )
        target.locked_until = None
        target.failed_login_attempts = 0
        if target.status == "locked":
            target.status = "active"

    if not verify_password_constant_time(req.password, target.password_hash):
        target.failed_login_attempts = int(target.failed_login_attempts or 0) + 1
        target_id = target.staff_id if target_type == "admin" else target.customer_id
        if target.failed_login_attempts >= settings.max_failed_logins:
            target.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            record_audit(
                db,
                ActorContext(actor_type=target_type, actor_id=target_id, role="anon", trace_id=actor.trace_id),
                "staff_user" if target_type == "admin" else "customer",
                target_id,
                "auth_account_locked",
                {"failed_attempts": target.failed_login_attempts, "ip": ip_address},
                "brute_force_lockout",
            )
        db.commit()
        raise AppError(
            code="invalid_credentials",
            message="Invalid email address or password.",
            status_code=401,
        )

    target.failed_login_attempts = 0
    target.locked_until = None
    target.last_login = now
    if password_needs_rehash(target.password_hash):
        target.password_hash = hash_password(req.password)

    if target_type == "admin":
        assert staff is not None
        actor_id = staff.staff_id
        role_code = staff.role_code
        user_payload = _serialize_staff_user(db, staff)
        resource_type = "staff_user"
    else:
        assert cust is not None
        actor_id = cust.customer_id
        role_code = "customer"
        user_payload = _serialize_customer_user(db, cust)
        resource_type = "customer"

    session_row, tokens = _issue_session_bundle(
        db=db,
        actor_type=target_type,
        actor_id=actor_id,
        role_code=role_code,
        email=target.email,
        name=target.name,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    record_audit(
        db,
        ActorContext(actor_type=target_type, actor_id=actor_id, role=role_code, trace_id=actor.trace_id),
        resource_type,
        actor_id,
        "auth_login_success",
        {"session_id": session_row.session_id, "ip": ip_address},
        "user_authenticated",
    )
    db.commit()

    perms = sorted(get_role_permissions(db, role_code))
    return {
        "user": user_payload,
        "tokens": tokens,
        "permissions": perms,
        "session": {
            "session_id": session_row.session_id,
            "expires_at": session_row.expires_at.isoformat(),
        },
    }


def refresh_user_session(
    db: Session,
    trace_id: str,
    raw_refresh_token: Optional[str],
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    if not raw_refresh_token or not raw_refresh_token.strip():
        raise AppError("missing_refresh_token", "Refresh token is required.", 401)

    payload = decode_refresh_token(raw_refresh_token.strip())
    session_id = str(payload["sid"])
    token_family = str(payload["fam"])
    now = _utc_now()

    session_row = db.scalar(select(AuthSession).where(AuthSession.session_id == session_id))
    if session_row is None:
        raise AppError("invalid_refresh_token", "Session was not found.", 401)

    if session_row.revoked_at is not None:
        if session_row.revoke_reason == "rotated":
            # Token theft / replay detection: invalidate entire token family immediately.
            family_rows = db.scalars(
                select(AuthSession).where(
                    AuthSession.token_family == token_family,
                    AuthSession.revoked_at.is_(None),
                )
            ).all()
            for fam_row in family_rows:
                fam_row.revoked_at = now
                fam_row.revoke_reason = "token_reuse_detected"
            record_audit(
                db,
                ActorContext(
                    actor_type=session_row.actor_type,
                    actor_id=session_row.actor_id,
                    role=session_row.role_code,
                    trace_id=trace_id,
                ),
                "auth_session",
                session_id,
                "auth_refresh_reuse_detected",
                {"token_family": token_family, "ip": ip_address},
                "security_token_family_revoked",
            )
            db.commit()
            raise AppError(
                code="token_reuse_detected",
                message="Suspicious refresh token replay detected. All sessions in this token family were revoked.",
                status_code=401,
            )
        raise AppError("session_revoked", "This session has already been signed out.", 401)

    if not constant_time_equals(session_row.refresh_token_hash, hash_token(raw_refresh_token.strip())):
        raise AppError("invalid_refresh_token", "Refresh token hash mismatch.", 401)

    exp_at = _ensure_tz(session_row.expires_at)
    if exp_at is None or exp_at <= now:
        session_row.revoked_at = now
        session_row.revoke_reason = "expired"
        db.commit()
        raise AppError("refresh_token_expired", "Refresh token has expired. Please sign in again.", 401)

    if session_row.actor_type == "admin":
        staff = db.scalar(select(StaffUser).where(StaffUser.staff_id == session_row.actor_id))
        if staff is None or not staff.is_active or staff.status != "active":
            session_row.revoked_at = now
            session_row.revoke_reason = "account_suspended"
            db.commit()
            raise AppError("account_suspended", "Staff account is inactive or suspended.", 403)
        role_code = staff.role_code
        email = staff.email
        name = staff.name
        user_payload = _serialize_staff_user(db, staff)
    else:
        cust = db.scalar(select(Customer).where(Customer.customer_id == session_row.actor_id))
        if cust is None or not cust.is_active or cust.status != "active":
            session_row.revoked_at = now
            session_row.revoke_reason = "account_suspended"
            db.commit()
            raise AppError("account_suspended", "Client account is inactive or suspended.", 403)
        role_code = "customer"
        email = cust.email
        name = cust.name
        user_payload = _serialize_customer_user(db, cust)

    new_session, tokens = _issue_session_bundle(
        db=db,
        actor_type=session_row.actor_type,
        actor_id=session_row.actor_id,
        role_code=role_code,
        email=email,
        name=name,
        ip_address=ip_address,
        user_agent=user_agent,
        token_family=token_family,
    )
    session_row.revoked_at = now
    session_row.revoke_reason = "rotated"
    session_row.replaced_by_session_id = new_session.session_id
    db.commit()

    perms = sorted(get_role_permissions(db, role_code))
    return {
        "user": user_payload,
        "tokens": tokens,
        "permissions": perms,
        "session": {
            "session_id": new_session.session_id,
            "expires_at": new_session.expires_at.isoformat(),
        },
    }


def logout_session(
    db: Session,
    actor: ActorContext,
    raw_refresh_token: Optional[str] = None,
) -> Dict[str, Any]:
    now = _utc_now()
    revoked = False

    if actor.session_id:
        sess = db.scalar(select(AuthSession).where(AuthSession.session_id == actor.session_id))
        if sess is not None and sess.revoked_at is None:
            sess.revoked_at = now
            sess.revoke_reason = "logout"
            revoked = True

    if raw_refresh_token and raw_refresh_token.strip():
        tok_hash = hash_token(raw_refresh_token.strip())
        sess_by_hash = db.scalar(select(AuthSession).where(AuthSession.refresh_token_hash == tok_hash))
        if sess_by_hash is not None and sess_by_hash.revoked_at is None:
            sess_by_hash.revoked_at = now
            sess_by_hash.revoke_reason = "logout"
            revoked = True

    if actor.actor_type != "anon":
        record_audit(
            db,
            actor,
            "auth_session",
            actor.session_id or actor.actor_id,
            "auth_logout",
            {"revoked": revoked},
            "user_logout",
        )
    db.commit()
    return {"status": "logged_out", "session_revoked": revoked}


def logout_all_sessions(db: Session, actor: ActorContext) -> Dict[str, Any]:
    revoked_count = _revoke_all_actor_sessions(db, actor.actor_type, actor.actor_id, "logout_all")
    record_audit(
        db,
        actor,
        "auth_session",
        actor.actor_id,
        "auth_logout_all",
        {"revoked_sessions": revoked_count},
        "user_logout_all_devices",
    )
    db.commit()
    return {"status": "logged_out_all", "revoked_sessions": revoked_count}


def get_authenticated_profile(db: Session, actor: ActorContext) -> Dict[str, Any]:
    if actor.actor_type == "customer":
        cust = db.scalar(select(Customer).where(Customer.customer_id == actor.actor_id))
        if cust is None:
            raise AppError("customer_not_found", f"Customer '{actor.actor_id}' not found.", 404)
        user_payload = _serialize_customer_user(db, cust)
    elif actor.actor_type == "admin":
        staff = db.scalar(select(StaffUser).where(StaffUser.staff_id == actor.actor_id))
        if staff is not None:
            user_payload = _serialize_staff_user(db, staff)
        else:
            role_row = _get_role_meta(db, actor.role)
            user_payload = {
                "id": actor.actor_id,
                "staff_id": actor.actor_id,
                "actor_type": "admin",
                "role": actor.role,
                "role_name": role_row.name if role_row else actor.role.replace("_", " ").title(),
                "hierarchy_level": role_row.hierarchy_level if role_row else 70,
                "is_staff": True,
                "name": actor.name or f"Maison {actor.role.replace('_', ' ').title()}",
                "email": actor.email or f"{actor.actor_id.lower()}@noir.test",
                "loyalty_tier": "STAFF",
                "status": "active",
            }
    else:
        user_payload = {
            "id": actor.actor_id,
            "actor_type": actor.actor_type,
            "role": actor.role,
            "role_name": "AI Service Account",
            "is_staff": False,
            "name": actor.actor_id,
            "status": "active",
        }

    return {
        "user": user_payload,
        "permissions": sorted(actor.permissions),
        "session_id": actor.session_id,
    }


def list_user_sessions(db: Session, actor: ActorContext) -> List[Dict[str, Any]]:
    now = _utc_now()
    rows = db.scalars(
        select(AuthSession)
        .where(
            AuthSession.actor_type == actor.actor_type,
            AuthSession.actor_id == actor.actor_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
        .order_by(AuthSession.last_used_at.desc())
    ).all()
    return [
        {
            "session_id": r.session_id,
            "ip_address": r.ip_address or "Local / Private",
            "user_agent": r.user_agent or "Web Client",
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "is_current": r.session_id == actor.session_id,
        }
        for r in rows
    ]


def revoke_user_session(db: Session, actor: ActorContext, target_session_id: str) -> Dict[str, Any]:
    sess = db.scalar(
        select(AuthSession).where(
            AuthSession.session_id == target_session_id.strip(),
            AuthSession.actor_type == actor.actor_type,
            AuthSession.actor_id == actor.actor_id,
        )
    )
    if sess is None:
        raise AppError("session_not_found", f"Session '{target_session_id}' was not found.", 404)
    if sess.revoked_at is None:
        sess.revoked_at = _utc_now()
        sess.revoke_reason = "user_revoked"
        db.commit()
    return {"session_id": sess.session_id, "status": "revoked"}


def change_user_password(db: Session, actor: ActorContext, req: PasswordChangeRequest) -> Dict[str, Any]:
    if actor.actor_type == "customer":
        account: Any = db.scalar(select(Customer).where(Customer.customer_id == actor.actor_id))
        resource_type = "customer"
    elif actor.actor_type == "admin":
        account = db.scalar(select(StaffUser).where(StaffUser.staff_id == actor.actor_id))
        resource_type = "staff_user"
    else:
        raise AppError("unsupported_actor", "Service accounts do not use interactive passwords.", 400)

    if account is None:
        raise AppError("account_not_found", "Account record not found.", 404)

    if account.password_hash and not verify_password(req.current_password, account.password_hash):
        raise AppError("invalid_current_password", "Your current password is incorrect.", 401)

    if constant_time_equals(req.current_password, req.new_password):
        raise AppError("password_unchanged", "New password must differ from your current password.", 422)

    account.password_hash = hash_password(req.new_password)
    revoked_others = _revoke_all_actor_sessions(
        db,
        actor.actor_type,
        actor.actor_id,
        reason="password_changed",
        exclude_session_id=actor.session_id,
    )
    record_audit(
        db,
        actor,
        resource_type,
        actor.actor_id,
        "auth_password_changed",
        {"revoked_other_sessions": revoked_others},
        "user_password_update",
    )
    db.commit()
    return {"status": "password_updated", "revoked_other_sessions": revoked_others}


def get_rbac_matrix(db: Session) -> Dict[str, Any]:
    roles = db.scalars(select(Role).where(Role.is_active.is_(True)).order_by(Role.hierarchy_level.desc())).all()
    permissions = db.scalars(select(Permission).order_by(Permission.resource, Permission.code)).all()
    rp_rows = db.execute(select(RolePermission.role_code, RolePermission.permission_code)).all()

    by_role: Dict[str, List[str]] = {}
    for r_code, p_code in rp_rows:
        by_role.setdefault(r_code, []).append(p_code)

    return {
        "roles": [
            {
                "code": r.code,
                "role_code": r.code,
                "name": r.name,
                "description": r.description,
                "actor_type": r.actor_type,
                "hierarchy_level": r.hierarchy_level,
                "is_system": r.is_system,
                "permissions": sorted(by_role.get(r.code, [])),
            }
            for r in roles
        ],
        "permissions": [
            {
                "code": p.code,
                "resource": p.resource,
                "action": p.action,
                "description": p.description,
            }
            for p in permissions
        ],
    }


def list_all_users_for_governance(db: Session) -> Dict[str, Any]:
    staff_rows = db.scalars(select(StaffUser).order_by(StaffUser.staff_id)).all()
    cust_rows = db.scalars(select(Customer).order_by(Customer.customer_id)).all()
    return {
        "staff": [_serialize_staff_user(db, s) for s in staff_rows],
        "customers": [_serialize_customer_user(db, c) for c in cust_rows],
    }


def create_staff_account_by_admin(
    db: Session,
    actor: ActorContext,
    req: StaffCreateRequest,
) -> Dict[str, Any]:
    admin_req = AdminRegisterRequest(
        name=req.name,
        email=req.email,
        password=req.password,
        role_code=req.role_code,
        phone=req.phone,
        department_scope=req.department_scope,
    )
    return register_admin_account(db=db, actor=actor, req=admin_req, issue_session=False)


def update_staff_account(
    db: Session,
    actor: ActorContext,
    staff_id: str,
    req: StaffUpdateRequest,
) -> Dict[str, Any]:
    clean_id = staff_id.strip().upper()
    staff = db.scalar(select(StaffUser).where(StaffUser.staff_id == clean_id))
    if staff is None:
        raise AppError("staff_not_found", f"Staff account '{staff_id}' was not found.", 404)

    changes: Dict[str, Any] = {}
    revoke_sessions_reason: Optional[str] = None

    if req.role_code is not None and req.role_code != staff.role_code:
        if staff.staff_id == actor.actor_id and staff.role_code == "super_admin":
            raise AppError("self_demotion_forbidden", "You cannot demote your own Super Admin role.", 409)
        role_row = db.scalar(
            select(Role).where(Role.code == req.role_code, Role.actor_type == "admin", Role.is_active.is_(True))
        )
        if role_row is None:
            raise AppError("invalid_staff_role", f"Role '{req.role_code}' is not an active staff role.", 422)
        if staff.role_code == "super_admin" and req.role_code != "super_admin":
            active_supers = db.scalar(
                select(func.count(StaffUser.staff_id)).where(
                    StaffUser.role_code == "super_admin",
                    StaffUser.status == "active",
                    StaffUser.is_active.is_(True),
                )
            ) or 0
            if active_supers <= 1:
                raise AppError(
                    "last_super_admin",
                    "At least one active Super Admin account must remain in Noir Atelier.",
                    409,
                )
        changes["old_role"] = staff.role_code
        changes["new_role"] = role_row.code
        staff.role_code = role_row.code
        revoke_sessions_reason = "role_changed"

    if req.status is not None and req.status != staff.status:
        if staff.staff_id == actor.actor_id and req.status != "active":
            raise AppError("self_suspension_forbidden", "You cannot suspend your own active account.", 409)
        changes["old_status"] = staff.status
        changes["new_status"] = req.status
        staff.status = req.status
        staff.is_active = req.status == "active"
        if req.status != "active":
            revoke_sessions_reason = "account_suspended"

    if req.name is not None:
        staff.name = req.name
        changes["name"] = req.name

    if req.department_scope is not None:
        staff.department_scope = req.department_scope.strip().upper() or None
        changes["department_scope"] = staff.department_scope

    if revoke_sessions_reason:
        changes["revoked_sessions"] = _revoke_all_actor_sessions(db, "admin", staff.staff_id, revoke_sessions_reason)

    record_audit(db, actor, "staff_user", staff.staff_id, "admin_update_staff", changes, "rbac_governance_update")
    db.commit()
    invalidate_rbac_cache()
    invalidate_config_cache()
    return _serialize_staff_user(db, staff)


def update_customer_account_status(
    db: Session,
    actor: ActorContext,
    customer_id: str,
    req: CustomerStatusUpdateRequest,
) -> Dict[str, Any]:
    cid = customer_id.strip().upper()
    cust = db.scalar(select(Customer).where(Customer.customer_id == cid))
    if cust is None:
        raise AppError("customer_not_found", f"Customer '{customer_id}' was not found.", 404)

    changes: Dict[str, Any] = {}
    if req.status is not None and req.status != cust.status:
        changes["old_status"] = cust.status
        changes["new_status"] = req.status
        cust.status = req.status
        cust.is_active = req.status == "active"
        if req.status != "active":
            changes["revoked_sessions"] = _revoke_all_actor_sessions(db, "customer", cust.customer_id, "account_suspended")

    if req.loyalty_tier is not None and req.loyalty_tier != cust.loyalty_tier:
        changes["old_loyalty_tier"] = cust.loyalty_tier
        changes["new_loyalty_tier"] = req.loyalty_tier
        cust.loyalty_tier = req.loyalty_tier

    record_audit(db, actor, "customer", cust.customer_id, "admin_update_customer", changes, "client_governance_update")
    db.commit()
    invalidate_config_cache()
    return _serialize_customer_user(db, cust)
