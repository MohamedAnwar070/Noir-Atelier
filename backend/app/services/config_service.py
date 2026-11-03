from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ActorContext
from ..models import BusinessConfig, PaymentMethod, Policy
from .audit_service import record_audit

_config_cache: Dict[str, Any] = {}


def invalidate_config_cache() -> None:
    _config_cache.clear()


def get_business_config_map(db: Session) -> Dict[str, Dict[str, Any]]:
    if "business_config" in _config_cache:
        return _config_cache["business_config"]

    rows = db.scalars(select(BusinessConfig)).all()
    cfg_map: Dict[str, Dict[str, Any]] = {r.config_key: dict(r.config_value) for r in rows}

    cfg_map.setdefault(
        "store",
        {
            "name": "Noir Atelier",
            "domain": "premium_garments_only",
            "departments": ["MEN", "WOMEN", "KIDS"],
            "currency": "INR",
            "timezone": "Asia/Kolkata",
        },
    )
    cfg_map.setdefault(
        "tax",
        {
            "mrp_inclusive": True,
            "mock_gstin": "33MOCKA1234Z1Z5",
            "origin_state": "Tamil Nadu",
            "origin_state_code": "33",
            "hsn_chapters": ["61", "62"],
            "garment_slab_threshold_inr": 2500,
            "rate_upto_threshold": 0.05,
            "rate_above_threshold": 0.18,
        },
    )
    cfg_map.setdefault(
        "shipping",
        {
            "free_shipping_threshold_inr": 1999,
            "default_shipping_fee_inr": 99,
            "cod_allowed": False,
            "signature_required_above_inr": 5000,
        },
    )
    cfg_map.setdefault(
        "returns_and_refunds",
        {
            "return_window_days": 7,
            "window_starts_from": "delivered_date",
            "require_security_tag_intact": True,
            "require_warehouse_qc_pass": True,
            "tiers": {
                "tier_0_pre_ship_cancel_max_inr": 50000,
                "tier_1_auto_refund_max_inr": 5000,
                "tier_2_manager_approval_max_inr": 25000,
                "tier_3_dual_approval_max_inr": 50000,
            },
        },
    )

    _config_cache["business_config"] = cfg_map
    return cfg_map


def get_policies_and_config(db: Session) -> Dict[str, Any]:
    cfg = get_business_config_map(db)
    policies = db.scalars(select(Policy).where(Policy.is_active.is_(True))).all()
    return {
        "business_config": cfg,
        "policies": [
            {
                "policy_id": p.policy_id,
                "topic": p.topic,
                "title": p.title,
                "rule_text": p.rule_text,
                "applies_to": p.applies_to,
                "return_window_days": p.return_window_days,
                "version": p.version,
            }
            for p in policies
        ],
    }


def update_business_config(
    db: Session,
    actor: ActorContext,
    config_key: str,
    config_value: Dict[str, Any],
    reason: str,
) -> Dict[str, Any]:
    row = db.scalar(select(BusinessConfig).where(BusinessConfig.config_key == config_key))
    old_val = dict(row.config_value) if row else None
    if row is None:
        row = BusinessConfig(config_key=config_key, config_value=config_value, updated_by=actor.actor_id)
        db.add(row)
    else:
        row.config_value = config_value
        row.updated_by = actor.actor_id

    record_audit(
        db=db,
        actor=actor,
        resource_type="business_config",
        resource_id=config_key,
        action="update_config",
        change_details={"old": old_val, "new": config_value},
        reason=reason,
    )
    db.commit()
    invalidate_config_cache()
    return {"config_key": config_key, "config_value": row.config_value, "updated_by": row.updated_by}


def list_payment_methods(db: Session) -> List[Dict[str, Any]]:
    methods = db.scalars(select(PaymentMethod).where(PaymentMethod.is_active.is_(True))).all()
    return [
        {
            "method_id": m.method_id,
            "name": m.name,
            "min_order_inr": float(m.min_order_inr),
            "max_order_inr": float(m.max_order_inr),
        }
        for m in methods
    ]
