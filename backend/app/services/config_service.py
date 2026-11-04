from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ActorContext
from ..models import BusinessConfig, Coupon, Customer, Department, PaymentMethod, Policy, ShippingZone
from ..reference_data import FIT_FEEDBACK_OPTIONS
from .audit_service import record_audit

STAFF_ROLES = ["manager", "finance_admin", "super_admin", "admin"]

_config_cache: Dict[str, Any] = {}


def invalidate_config_cache() -> None:
    _config_cache.clear()


def get_business_config_map(db: Session) -> Dict[str, Dict[str, Any]]:
    if "business_config" in _config_cache:
        return _config_cache["business_config"]

    rows = db.scalars(select(BusinessConfig)).all()
    cfg_map: Dict[str, Dict[str, Any]] = {r.config_key: dict(r.config_value) for r in rows}
    dept_codes = [
        d.code
        for d in db.scalars(
            select(Department).where(Department.is_active.is_(True)).order_by(Department.display_order, Department.code)
        ).all()
    ] or ["MEN", "WOMEN", "KIDS"]

    cfg_map.setdefault(
        "store",
        {
            "name": "Noir Atelier",
            "domain": "premium_garments_only",
            "departments": dept_codes,
            "currency": "INR",
            "timezone": "Asia/Kolkata",
        },
    )
    cfg_map["store"]["departments"] = dept_codes
    cfg_map.setdefault(
        "storefront_ui",
        {
            "hero_eyebrow": "Noir Atelier · HSN 61 & 62 Luxury Garments",
            "hero_title": "The New Edit",
            "hero_subtitle": "Explore timeless tailored Belgian linen shirts, 22-momme mulberry silk dresses, and superfine merino knitwear across Men, Women, and Kids.",
            "hero_image_url": "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=1200&q=85",
            "hero_image_alt": "Noir Atelier Editorial Collection",
            "ai_quick_prompts": [
                {"label": "Men's linen under ₹3,000", "prompt": "Show me Men's garments under INR 3000"},
                {"label": "Women's mulberry silk & cotton", "prompt": "Show me Women's garments"},
                {"label": "7-Day Return & GST Policy", "prompt": "What are the return policy rules and GST slabs?"},
                {"label": "GMV & Analytics Report", "prompt": "Show GMV and order analytics report"},
            ],
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

    cfg_map.setdefault(
        "catalog",
        {
            "luxury_tier_min_inr": 7000,
            "high_value_tier_min_inr": 50000,
            "couture_tier_min_inr": 100000,
            "curated_collection_target": 100,
            "fit_feedback_options": [dict(opt) for opt in FIT_FEEDBACK_OPTIONS],
        },
    )
    cfg_map["catalog"].setdefault("luxury_tier_min_inr", 7000)
    cfg_map["catalog"].setdefault("high_value_tier_min_inr", 50000)
    cfg_map["catalog"].setdefault("couture_tier_min_inr", 100000)
    cfg_map["catalog"].setdefault("curated_collection_target", 100)
    cfg_map["catalog"].setdefault("fit_feedback_options", [dict(opt) for opt in FIT_FEEDBACK_OPTIONS])

    _config_cache["business_config"] = cfg_map
    return cfg_map


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


def list_active_coupons(db: Session) -> List[Dict[str, Any]]:
    coupons = db.scalars(select(Coupon).where(Coupon.is_active.is_(True))).all()
    return [
        {
            "code": c.code,
            "discount_type": c.discount_type,
            "discount_value": float(c.discount_value),
            "min_order_value_inr": float(c.min_order_value_inr),
            "max_discount_inr": float(c.max_discount_inr),
        }
        for c in coupons
    ]


def list_shipping_zones(db: Session) -> List[Dict[str, Any]]:
    zones = db.scalars(select(ShippingZone).where(ShippingZone.is_active.is_(True))).all()
    return [
        {
            "zone_id": z.zone_id,
            "name": z.name,
            "pin_prefixes": list(z.pin_prefixes or []),
            "base_fee_inr": float(z.base_fee_inr),
            "estimated_days": z.estimated_days,
        }
        for z in zones
    ]


def list_platform_actors(db: Session) -> List[Dict[str, Any]]:
    customers = db.scalars(
        select(Customer).where(Customer.is_active.is_(True)).order_by(Customer.customer_id)
    ).all()
    actors: List[Dict[str, Any]] = []
    for c in customers:
        tier_label = "VIP Gold" if c.loyalty_tier == "VIP_GOLD" else "Standard"
        actors.append(
            {
                "token": f"demo_{c.customer_id}",
                "id": c.customer_id,
                "actor_type": "customer",
                "role": "customer",
                "is_staff": False,
                "loyalty_tier": c.loyalty_tier,
                "label": f"{c.name.split()[0]} · {tier_label} ({c.customer_id})",
            }
        )
    actors.extend(
        [
            {
                "token": "admin_manager",
                "id": "MGR-001",
                "actor_type": "admin",
                "role": "manager",
                "is_staff": True,
                "loyalty_tier": "STAFF",
                "label": "Store Manager (MGR-001)",
            },
            {
                "token": "admin_finance",
                "id": "FIN-001",
                "actor_type": "admin",
                "role": "finance_admin",
                "is_staff": True,
                "loyalty_tier": "STAFF",
                "label": "Finance Admin (FIN-001)",
            },
        ]
    )
    return actors


def get_policies_and_config(db: Session) -> Dict[str, Any]:
    cfg = get_business_config_map(db)
    policies = db.scalars(select(Policy).where(Policy.is_active.is_(True))).all()
    return {
        "business_config": cfg,
        "staff_roles": list(STAFF_ROLES),
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
        "payment_methods": list_payment_methods(db),
        "coupons": list_active_coupons(db),
        "shipping_zones": list_shipping_zones(db),
        "actors": list_platform_actors(db),
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
