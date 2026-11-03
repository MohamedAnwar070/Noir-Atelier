from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ActorContext, require_agent_or_admin, require_authenticated, resolve_actor
from ..database import get_db
from ..models import Invoice, Shipment
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
    create_order,
    get_order_details,
    get_orders_analytics,
    initiate_payment,
    list_customer_orders,
    schedule_shipment,
)
from ..utils.exceptions import AppError

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
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return create_order(db, actor, req)


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
    req: OrderCancelRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return cancel_order(db, actor, order_id, req)


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
    actor: ActorContext = Depends(require_agent_or_admin),
) -> Dict[str, Any]:
    return schedule_shipment(db, actor, req)


@router.get("/api/shipments/{identifier}")
def api_get_shipment(
    identifier: str,
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    clean = identifier.strip().upper()
    shp = db.scalar(
        select(Shipment).where((Shipment.shipment_id == clean) | (Shipment.order_id == clean))
    )
    if shp is None:
        raise AppError("shipment_not_found", f"Shipment for '{identifier}' not found.", 404)
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
    _actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    clean = identifier.strip().upper()
    inv = db.scalar(
        select(Invoice).where((Invoice.invoice_id == clean) | (Invoice.order_id == clean))
    )
    if inv is None:
        raise AppError("invoice_not_found", f"Invoice for '{identifier}' not found.", 404)
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
