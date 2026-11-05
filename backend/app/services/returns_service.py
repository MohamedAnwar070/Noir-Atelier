from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ActorContext
from ..models import (
    ComplianceFlag,
    Customer,
    Order,
    Refund,
    RefundStatus,
    ReturnReason,
    ReturnRequest,
    Shipment,
    SupportTicket,
)
from ..schemas.return_schema import (
    RefundApproveRequest,
    ReturnCreateRequest,
    SupportEscalateRequest,
)
from ..storage.object_store import LocalObjectStore
from ..utils.exceptions import AppError
from .audit_service import get_idempotent_result, next_entity_id, record_audit, save_idempotent_result
from .config_service import get_business_config_map
from .order_service import _assert_order_access
from .product_service import get_product_by_id_or_sku


def _determine_approval_tier(
    amount_inr: Decimal,
    has_final_sale: bool,
    is_vip_gold: bool,
    outside_window: bool,
    is_defective_claim: bool,
    tiers_cfg: Dict[str, Any],
) -> int:
    tier1_max = Decimal(str(tiers_cfg.get("tier_1_auto_refund_max_inr", 5000)))
    tier2_max = Decimal(str(tiers_cfg.get("tier_2_manager_approval_max_inr", 25000)))

    if amount_inr > tier2_max or (outside_window and is_defective_claim):
        return 3
    if amount_inr > tier1_max or (has_final_sale and is_vip_gold):
        return 2
    return 1


def initiate_return(db: Session, actor: ActorContext, req: ReturnCreateRequest) -> Dict[str, Any]:
    cached = get_idempotent_result(db, req.request_key)
    if cached is not None:
        return dict(cached.response_snapshot)

    order = db.scalar(select(Order).where(Order.order_id == req.order_id.strip().upper()))
    if order is None:
        raise AppError("order_not_found", f"Order '{req.order_id}' was not found.", 404)
    _assert_order_access(actor, order)

    reason_code = req.reason_category.strip().lower()
    reason_row = db.scalar(
        select(ReturnReason).where(ReturnReason.code == reason_code, ReturnReason.is_active.is_(True))
    )
    if reason_row is None:
        available = [
            r.code
            for r in db.scalars(
                select(ReturnReason).where(ReturnReason.is_active.is_(True)).order_by(ReturnReason.display_order)
            ).all()
        ]
        raise AppError(
            "invalid_return_reason",
            f"Unsupported return reason '{req.reason_category}'.",
            422,
            details={"available_reasons": available},
        )
    is_defective_claim = bool(reason_row.is_defect_claim or req.is_defective_claim)

    cfg = get_business_config_map(db)["returns_and_refunds"]
    window_days = int(cfg.get("return_window_days", 7))
    tiers_cfg = cfg.get("tiers", {})

    customer = db.scalar(select(Customer).where(Customer.customer_id == order.customer_id))
    is_vip_gold = bool(customer and customer.loyalty_tier == "VIP_GOLD")
    has_final_sale = any(i.final_sale for i in order.items)

    if has_final_sale and not is_vip_gold and not is_defective_claim:
        raise AppError(
            "final_sale_non_returnable",
            "Items marked Final Sale are strictly non-returnable under policy POL-RET-02.",
            422,
        )

    shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.order_id))
    ref_date = (shipment.delivered_date if shipment and shipment.delivered_date else order.order_date)
    if ref_date.tzinfo is None:
        ref_date = ref_date.replace(tzinfo=timezone.utc)
    days_elapsed = max(0, (datetime.now(timezone.utc) - ref_date).days)
    effective_window = 14 if is_vip_gold else window_days
    outside_window = days_elapsed > effective_window

    if outside_window and not is_defective_claim:
        raise AppError(
            "return_window_expired",
            f"Return window of {effective_window} days from delivery has expired ({days_elapsed} days elapsed).",
            422,
        )

    if not req.tag_intact or not req.qc_passed:
        raise AppError(
            "qc_or_security_tag_failed",
            "Noir Atelier garments require the atelier security ribbon intact and passing warehouse QC (POL-RET-01).",
            422,
        )

    tier = _determine_approval_tier(
        amount_inr=order.grand_total_inr,
        has_final_sale=has_final_sale,
        is_vip_gold=is_vip_gold,
        outside_window=outside_window,
        is_defective_claim=is_defective_claim,
        tiers_cfg=tiers_cfg,
    )

    ret_id = next_entity_id(db, ReturnRequest, ReturnRequest.return_id, "return", start_seq=1001)
    object_store = LocalObjectStore()
    label_url = f"/media/returns/{ret_id}/return-label.json"
    qc_key = object_store.put_json(
        "returns",
        ret_id,
        "qc-report.json",
        {
            "return_id": ret_id,
            "order_id": order.order_id,
            "tag_intact": req.tag_intact,
            "qc_passed": req.qc_passed,
            "approval_tier": tier,
        },
    )

    ret_row = ReturnRequest(
        return_id=ret_id,
        order_id=order.order_id,
        reason_category=reason_row.code,
        customer_notes=req.customer_notes,
        status="qc_passed" if tier == 1 else "pending_approval",
        tag_intact=req.tag_intact,
        qc_passed=req.qc_passed,
        return_shipping_label_url=label_url,
        evidence_storage_key=qc_key,
    )
    db.add(ret_row)

    rfd_id = next_entity_id(db, Refund, Refund.refund_id, "refund", start_seq=1001)
    rfd_status = "pending_approval" if tier >= 2 else "approved"
    rfd_row = Refund(
        refund_id=rfd_id,
        return_id=ret_id,
        order_id=order.order_id,
        amount_inr=order.grand_total_inr,
        approval_tier=tier,
        status=rfd_status,
        reason=reason_row.code,
        approved_by="svc-returns" if tier == 1 else None,
        approved_date=datetime.now(timezone.utc) if tier == 1 else None,
    )
    db.add(rfd_row)

    ticket_id: Optional[str] = None
    if tier >= 2:
        tkt_id = next_entity_id(db, SupportTicket, SupportTicket.ticket_id, "ticket", start_seq=1001)
        ticket_id = tkt_id
        db.add(
            SupportTicket(
                ticket_id=tkt_id,
                customer_id=order.customer_id,
                order_id=order.order_id,
                subject=f"Tier {tier} Return Approval Required ({order.order_id})",
                description=f"Return {ret_id} for INR {order.grand_total_inr} requires Tier {tier} approval.",
                category="return_approval",
                priority="high" if tier == 3 else "medium",
                status="pending_approval",
                created_by=actor.actor_id,
                assigned_to="finance_admin" if tier == 3 else "manager",
            )
        )
        db.add(
            ComplianceFlag(
                order_id=order.order_id,
                flag_type=f"tier_{tier}_refund_review",
                severity="high" if tier == 3 else "medium",
                details={"return_id": ret_id, "refund_id": rfd_id, "amount_inr": float(order.grand_total_inr)},
            )
        )
        order.status = "pending_return"
    else:
        rfd_row.status = "processed"
        rfd_row.processed_date = datetime.now(timezone.utc)
        rfd_row.payment_refund_id = f"RFD-TXN-{uuid.uuid4().hex[:8].upper()}"
        ret_row.status = "completed"
        order.status = "refunded"
        for item in order.items:
            prod = get_product_by_id_or_sku(db, item.product_id)
            if prod.inventory:
                prod.inventory.quantity_available += item.quantity

    record_audit(
        db,
        actor,
        "return",
        ret_id,
        f"initiate_return_tier_{tier}",
        {"order_id": order.order_id, "refund_id": rfd_id, "tier": tier, "status": rfd_row.status},
        req.reason_category,
    )
    db.flush()

    response_payload = {
        "return_id": ret_id,
        "order_id": order.order_id,
        "reason_category": ret_row.reason_category,
        "reason_label": reason_row.label,
        "status": ret_row.status,
        "tag_intact": ret_row.tag_intact,
        "qc_passed": ret_row.qc_passed,
        "return_shipping_label_url": ret_row.return_shipping_label_url,
        "refund_id": rfd_id,
        "refund_status": rfd_row.status,
        "approval_tier": tier,
        "escalation_ticket_id": ticket_id,
    }
    save_idempotent_result(db, req.request_key, actor.actor_id, "return", ret_id, "initiate_return", response_payload)
    db.commit()
    return response_payload


def get_return_status(db: Session, actor: ActorContext, return_id: str) -> Dict[str, Any]:
    ret = db.scalar(select(ReturnRequest).where(ReturnRequest.return_id == return_id.strip().upper()))
    if ret is None:
        raise AppError("return_not_found", f"Return '{return_id}' was not found.", 404)
    order = db.scalar(select(Order).where(Order.order_id == ret.order_id))
    if order:
        _assert_order_access(actor, order)
    rfd = db.scalar(select(Refund).where(Refund.return_id == ret.return_id))
    return {
        "return_id": ret.return_id,
        "order_id": ret.order_id,
        "reason_category": ret.reason_category,
        "status": ret.status,
        "tag_intact": ret.tag_intact,
        "qc_passed": ret.qc_passed,
        "return_shipping_label_url": ret.return_shipping_label_url,
        "refund_id": rfd.refund_id if rfd else None,
        "refund_status": rfd.status if rfd else None,
        "approval_tier": rfd.approval_tier if rfd else 1,
    }


def approve_refund(
    db: Session,
    actor: ActorContext,
    refund_id: str,
    req: RefundApproveRequest,
) -> Dict[str, Any]:
    rfd = db.scalar(select(Refund).where(Refund.refund_id == refund_id.strip().upper()))
    if rfd is None:
        raise AppError("refund_not_found", f"Refund '{refund_id}' was not found.", 404)

    if rfd.approval_tier == 1:
        rfd.approved_by = actor.actor_id
        rfd.approved_date = datetime.now(timezone.utc)
        rfd.status = "approved"
    elif rfd.approval_tier == 2:
        if actor.actor_type != "admin" or not actor.has_permission("refunds:approve_tier2"):
            raise AppError(
                "manager_approval_required",
                f"Refund '{rfd.refund_id}' (INR {rfd.amount_inr}) is Tier 2 and requires Store Manager approval.",
                403,
            )
        rfd.approved_by = actor.actor_id
        rfd.approved_date = datetime.now(timezone.utc)
        rfd.status = "approved"
    else:
        if actor.actor_type != "admin" or not actor.has_permission("refunds:approve_tier3"):
            raise AppError(
                "dual_approval_required",
                f"Refund '{rfd.refund_id}' (INR {rfd.amount_inr}) is Tier 3 (> INR 25,000) and requires Manager + Finance dual approval.",
                403,
            )
        if not rfd.approved_by:
            rfd.approved_by = actor.actor_id
            rfd.status = "awaiting_secondary_approval"
        elif rfd.approved_by == actor.actor_id:
            raise AppError(
                "segregation_of_duties_violation",
                "Tier 3 dual approval requires two distinct admin approvers (Manager + Finance).",
                403,
            )
        else:
            rfd.secondary_approved_by = actor.actor_id
            rfd.approved_date = datetime.now(timezone.utc)
            rfd.status = "approved"

    record_audit(
        db,
        actor,
        "refund",
        rfd.refund_id,
        "approve_refund",
        {"tier": rfd.approval_tier, "status": rfd.status, "approved_by": rfd.approved_by, "secondary": rfd.secondary_approved_by},
        req.reason,
    )
    db.commit()
    return _serialize_refund(rfd, db)


def process_refund_payout(db: Session, actor: ActorContext, refund_id: str) -> Dict[str, Any]:
    rfd = db.scalar(select(Refund).where(Refund.refund_id == refund_id.strip().upper()))
    if rfd is None:
        raise AppError("refund_not_found", f"Refund '{refund_id}' was not found.", 404)
    if rfd.status == "processed":
        return _serialize_refund(rfd, db)
    if rfd.status != "approved":
        raise AppError(
            "refund_not_approved",
            f"Refund '{rfd.refund_id}' is in status '{rfd.status}' and must be approved before payout.",
            422,
        )

    rfd.status = "processed"
    rfd.processed_date = datetime.now(timezone.utc)
    rfd.payment_refund_id = f"RFD-TXN-{uuid.uuid4().hex[:8].upper()}"

    order = db.scalar(select(Order).where(Order.order_id == rfd.order_id))
    if order:
        order.status = "refunded"
        for item in order.items:
            prod = get_product_by_id_or_sku(db, item.product_id)
            if prod.inventory:
                prod.inventory.quantity_available += item.quantity

    if rfd.return_id:
        ret = db.scalar(select(ReturnRequest).where(ReturnRequest.return_id == rfd.return_id))
        if ret:
            ret.status = "completed"

    record_audit(
        db,
        actor,
        "refund",
        rfd.refund_id,
        "process_refund_payout",
        {"amount_inr": float(rfd.amount_inr), "payment_refund_id": rfd.payment_refund_id},
        "refund_disbursed_and_restocked",
    )
    db.commit()
    return _serialize_refund(rfd, db)


def list_refunds(db: Session, order_id: Optional[str] = None) -> List[Dict[str, Any]]:
    stmt = select(Refund).order_by(Refund.created_at.desc())
    if order_id:
        stmt = stmt.where(Refund.order_id == order_id.strip().upper())
    rows = db.scalars(stmt).all()
    status_map = {s.code: s for s in db.scalars(select(RefundStatus)).all()}
    return [_serialize_refund(r, db, status_map=status_map) for r in rows]


def _serialize_refund(
    rfd: Refund,
    db: Optional[Session] = None,
    *,
    status_map: Optional[Dict[str, RefundStatus]] = None,
) -> Dict[str, Any]:
    srow = status_map.get(rfd.status) if status_map is not None else (db.get(RefundStatus, rfd.status) if db else None)
    return {
        "refund_id": rfd.refund_id,
        "return_id": rfd.return_id,
        "order_id": rfd.order_id,
        "amount_inr": float(rfd.amount_inr),
        "approval_tier": rfd.approval_tier,
        "status": rfd.status,
        "status_label": srow.label if srow else rfd.status,
        "status_tone": srow.tone if srow else "neutral",
        "awaiting_approval": bool(srow.awaiting_approval) if srow else False,
        "reason": rfd.reason,
        "approved_by": rfd.approved_by,
        "secondary_approved_by": rfd.secondary_approved_by,
        "payment_refund_id": rfd.payment_refund_id,
    }


def create_support_escalation(db: Session, actor: ActorContext, req: SupportEscalateRequest) -> Dict[str, Any]:
    tkt_id = next_entity_id(db, SupportTicket, SupportTicket.ticket_id, "ticket", start_seq=1001)
    tkt = SupportTicket(
        ticket_id=tkt_id,
        customer_id=req.customer_id or actor.on_behalf_of,
        order_id=req.order_id,
        subject=req.subject,
        description=req.description,
        category=req.category,
        priority=req.priority,
        status="open",
        created_by=actor.actor_id,
        assigned_to="support_specialist",
    )
    db.add(tkt)
    record_audit(db, actor, "support_ticket", tkt_id, "escalate_ticket", {"category": req.category, "priority": req.priority}, req.subject)
    db.commit()
    return {
        "ticket_id": tkt.ticket_id,
        "customer_id": tkt.customer_id,
        "order_id": tkt.order_id,
        "subject": tkt.subject,
        "description": tkt.description,
        "category": tkt.category,
        "priority": tkt.priority,
        "status": tkt.status,
        "created_by": tkt.created_by,
        "assigned_to": tkt.assigned_to,
    }
