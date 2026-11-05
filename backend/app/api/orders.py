import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ActorContext, assert_customer_access, require_agent_or_admin, require_authenticated, require_permissions, resolve_actor
from ..config import get_settings
from ..database import get_db
from ..models import Invoice, Order, Shipment
from ..schemas.order_schema import (
    OrderCalculateRequest,
    OrderCancelRequest,
    OrderCreateRequest,
    PaymentInitiateRequest,
    ShipmentScheduleRequest,
)
from ..services.order_service import (
    calculate_order_preview,
    cancel_order,
    claim_order_pickup,
    create_order,
    get_order_details,
    get_orders_analytics,
    handle_demo_payment,
    handle_payment_webhook,
    initiate_payment,
    list_customer_orders,
    schedule_shipment,
    sweep_expired_orders,
)
from ..utils.exceptions import AppError
from ..utils.hmac_auth import verify_signature

router = APIRouter()


@router.post("/api/orders/calculate")
def api_calculate_order(
    req: OrderCalculateRequest,
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(resolve_actor),
) -> Dict[str, Any]:
    return calculate_order_preview(db, req)


@router.post("/api/orders", status_code=201)
def api_create_order(
    req: OrderCreateRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    if idempotency_key and not req.request_key:
        req.request_key = idempotency_key
    return create_order(db, actor, req)


@router.post("/api/orders/hold", status_code=201)
def api_create_order_hold(
    req: OrderCreateRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    if idempotency_key and not req.request_key:
        req.request_key = idempotency_key
    req.hold_only = True
    return create_order(db, actor, req)


@router.post("/api/orders/sweep-expired")
def api_sweep_expired_orders(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(resolve_actor),
) -> Dict[str, Any]:
    return sweep_expired_orders(db)


@router.get("/api/orders")
def api_list_orders(
    customer_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> List[Dict[str, Any]]:
    return list_customer_orders(db, actor, customer_id=customer_id)


@router.get("/api/orders/analytics")
def api_orders_analytics(
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_agent_or_admin),
) -> Dict[str, Any]:
    return get_orders_analytics(db)


@router.get("/api/orders/{order_id}")
def api_get_order(
    order_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return get_order_details(db, actor, order_id)


@router.post("/api/orders/{order_id}/cancel")
def api_cancel_order(
    order_id: str,
    req: Optional[OrderCancelRequest] = None,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    cancel_req = req or OrderCancelRequest()
    if idempotency_key and not cancel_req.request_key:
        cancel_req.request_key = idempotency_key
    return cancel_order(db, actor, order_id, cancel_req)


@router.post("/api/orders/{order_id}/pickup-claim")
def api_claim_order_pickup(
    order_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return claim_order_pickup(db, actor, order_id)


@router.post("/api/payments/webhook")
async def api_payment_webhook(
    request: Request,
    x_signature: Optional[str] = Header(default=None, alias="X-Signature"),
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
) -> Dict[str, Any]:
    raw_bytes = await request.body()
    raw_str = raw_bytes.decode("utf-8", errors="replace")
    secret = get_settings().webhook_secret
    if not verify_signature(raw_bytes, x_signature, secret):
        raise AppError("invalid_signature", "Webhook signature verification failed.", 401)
    try:
        payload = json.loads(raw_str) if raw_str else {}
    except json.JSONDecodeError as exc:
        raise AppError("validation_error", f"Malformed JSON body: {exc}", 400) from exc
    return handle_payment_webhook(db, actor, payload, raw_str)


@router.post("/api/payments/demo/{order_id}")
def api_demo_payment(
    order_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
) -> Dict[str, Any]:
    return handle_demo_payment(db, actor, order_id)


@router.post("/api/payments/initiate")
def api_initiate_payment(
    req: PaymentInitiateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return initiate_payment(db, actor, req)


@router.post("/api/shipments/schedule")
def api_schedule_shipment(
    req: ShipmentScheduleRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_permissions("orders:manage_fulfillment", allow_agent=True)),
) -> Dict[str, Any]:
    return schedule_shipment(db, actor, req)


def _assert_order_record_access(db: Session, actor: ActorContext, order_id: str) -> None:
    if actor.actor_type == "admin":
        if actor.has_permission("orders:read_all"):
            return
        raise AppError("forbidden_order_access", "You are not authorized to access this order's records.", 403)
    ord_row = db.scalar(select(Order).where(Order.order_id == order_id))
    if ord_row is None:
        raise AppError("forbidden_order_access", "You are not authorized to access this order's records.", 403)
    assert_customer_access(actor, ord_row.customer_id, "order's records")


@router.get("/api/shipments/{identifier}")
def api_get_shipment(
    identifier: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    clean = identifier.strip().upper()
    shp = db.scalar(
        select(Shipment).where((Shipment.shipment_id == clean) | (Shipment.order_id == clean))
    )
    if shp is None:
        raise AppError("shipment_not_found", f"Shipment for '{identifier}' not found.", 404)
    _assert_order_record_access(db, actor, shp.order_id)
    return {
        "shipment_id": shp.shipment_id,
        "order_id": shp.order_id,
        "carrier": shp.carrier,
        "tracking_number": shp.tracking_number,
        "status": shp.status,
        "scheduled_pickup": shp.scheduled_pickup.isoformat() if shp.scheduled_pickup else None,
        "delivered_date": shp.delivered_date.isoformat() if shp.delivered_date else None,
        "label_storage_key": shp.label_storage_key,
    }


@router.get("/api/invoices/{identifier}")
def api_get_invoice(
    identifier: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    clean = identifier.strip().upper()
    inv = db.scalar(
        select(Invoice).where((Invoice.invoice_id == clean) | (Invoice.order_id == clean))
    )
    if inv is None:
        raise AppError("invoice_not_found", f"Invoice for '{identifier}' not found.", 404)
    _assert_order_record_access(db, actor, inv.order_id)
    return {
        "invoice_id": inv.invoice_id,
        "order_id": inv.order_id,
        "seller_gstin": inv.seller_gstin,
        "place_of_supply_state": inv.place_of_supply_state,
        "is_intra_state": inv.is_intra_state,
        "taxable_value_inr": float(inv.taxable_value_inr),
        "cgst_inr": float(inv.cgst_inr),
        "sgst_inr": float(inv.sgst_inr),
        "igst_inr": float(inv.igst_inr),
        "total_inr": float(inv.total_inr),
        "storage_key": inv.storage_key,
    }
