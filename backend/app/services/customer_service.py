from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import ActorContext
from ..models import Customer, CustomerAddress, CustomerPreference, Order
from ..schemas.config_schema import AddressCreateRequest, CustomerCreateRequest, CustomerUpdateRequest
from ..utils.exceptions import AppError
from .audit_service import next_entity_id, record_audit


def _assert_customer_access(actor: ActorContext, customer_id: str) -> None:
    if actor.actor_type in ("admin", "agent"):
        return
    if actor.actor_type == "customer" and actor.actor_id != customer_id:
        raise AppError("forbidden_customer_access", "Cannot access another customer's profile.", 403)


def register_customer(db: Session, actor: ActorContext, req: CustomerCreateRequest) -> Dict[str, Any]:
    existing = db.scalar(select(Customer).where(func.lower(Customer.email) == req.email.strip().lower()))
    if existing:
        raise AppError("email_already_registered", f"Email '{req.email}' is already registered.", 409)

    cid = next_entity_id(db, Customer, Customer.customer_id, "customer", start_seq=1)
    cust = Customer(
        customer_id=cid,
        name=req.name.strip(),
        email=req.email.strip().lower(),
        phone=req.phone,
        loyalty_tier=req.loyalty_tier.strip().upper(),
    )
    db.add(cust)
    db.add(CustomerPreference(customer_id=cid, dpdp_consent=True, referral_code=f"NOIR-{cid}"))
    record_audit(db, actor, "customer", cid, "register_customer", {"email": cust.email}, "customer_registration")
    db.commit()
    return _serialize_customer(cust)


def get_customer_profile(db: Session, actor: ActorContext, customer_id: str) -> Dict[str, Any]:
    cid = customer_id.strip().upper()
    _assert_customer_access(actor, cid)
    cust = db.scalar(select(Customer).where(Customer.customer_id == cid))
    if cust is None:
        raise AppError("customer_not_found", f"Customer '{customer_id}' not found.", 404)
    return _serialize_customer(cust)


def update_customer_profile(
    db: Session,
    actor: ActorContext,
    customer_id: str,
    req: CustomerUpdateRequest,
) -> Dict[str, Any]:
    cid = customer_id.strip().upper()
    _assert_customer_access(actor, cid)
    cust = db.scalar(select(Customer).where(Customer.customer_id == cid))
    if cust is None:
        raise AppError("customer_not_found", f"Customer '{customer_id}' not found.", 404)

    changes: Dict[str, Any] = {}
    if req.name is not None:
        cust.name = req.name.strip()
        changes["name"] = cust.name
    if req.email is not None:
        cust.email = req.email.strip().lower()
        changes["email"] = cust.email
    if req.phone is not None:
        cust.phone = req.phone.strip()
        changes["phone"] = cust.phone

    record_audit(db, actor, "customer", cid, "update_customer", changes, "profile_update")
    db.commit()
    return _serialize_customer(cust)


def list_customer_addresses(db: Session, actor: ActorContext, customer_id: str) -> List[Dict[str, Any]]:
    cid = customer_id.strip().upper()
    _assert_customer_access(actor, cid)
    rows = db.scalars(select(CustomerAddress).where(CustomerAddress.customer_id == cid, CustomerAddress.is_active.is_(True))).all()
    return [_serialize_address(a) for a in rows]


def add_customer_address(
    db: Session,
    actor: ActorContext,
    customer_id: str,
    req: AddressCreateRequest,
) -> Dict[str, Any]:
    cid = customer_id.strip().upper()
    _assert_customer_access(actor, cid)
    aid = next_entity_id(db, CustomerAddress, CustomerAddress.address_id, "address", start_seq=1)
    addr = CustomerAddress(
        address_id=aid,
        customer_id=cid,
        label=req.label,
        street=req.street,
        city=req.city,
        state=req.state,
        pin_code=req.pin_code,
        is_primary=req.is_primary,
    )
    db.add(addr)
    record_audit(db, actor, "customer_address", aid, "add_address", {"customer_id": cid, "pin_code": req.pin_code}, "address_added")
    db.commit()
    return _serialize_address(addr)


def get_customer_preferences(db: Session, actor: ActorContext, customer_id: str) -> Dict[str, Any]:
    cid = customer_id.strip().upper()
    _assert_customer_access(actor, cid)
    pref = db.scalar(select(CustomerPreference).where(CustomerPreference.customer_id == cid))
    if pref is None:
        raise AppError("preferences_not_found", f"Preferences not found for '{customer_id}'.", 404)
    return {
        "customer_id": pref.customer_id,
        "preferred_department": pref.preferred_department,
        "preferred_sizes": dict(pref.preferred_sizes or {}),
        "email_notifications": pref.email_notifications,
        "sms_notifications": pref.sms_notifications,
        "newsletter": pref.newsletter,
        "dpdp_consent": pref.dpdp_consent,
        "referral_code": pref.referral_code,
    }


def get_customers_analytics(db: Session) -> Dict[str, Any]:
    total_customers = db.scalar(select(func.count(Customer.customer_id))) or 0
    order_counts = db.execute(
        select(Order.customer_id, func.count(Order.order_id).label("cnt"))
        .where(Order.status != "cancelled")
        .group_by(Order.customer_id)
    ).all()
    repeat_buyers = sum(1 for r in order_counts if (r.cnt or 0) > 1)
    retention_pct = round((repeat_buyers / total_customers) * 100, 2) if total_customers else 0.0
    return {
        "total_customers": int(total_customers),
        "repeat_buyers": repeat_buyers,
        "retention_rate_pct": retention_pct,
    }


def _serialize_customer(c: Customer) -> Dict[str, Any]:
    return {
        "customer_id": c.customer_id,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "loyalty_tier": c.loyalty_tier,
        "status": c.status,
    }


def _serialize_address(a: CustomerAddress) -> Dict[str, Any]:
    return {
        "address_id": a.address_id,
        "customer_id": a.customer_id,
        "label": a.label,
        "street": a.street,
        "city": a.city,
        "state": a.state,
        "pin_code": a.pin_code,
        "country": a.country,
        "is_primary": a.is_primary,
    }
