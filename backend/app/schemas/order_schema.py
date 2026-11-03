from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class OrderLineInput(BaseModel):
    product_id: str
    size: str = "M"
    quantity: int = Field(default=1, gt=0)


class OrderCalculateRequest(BaseModel):
    items: List[OrderLineInput]
    coupon_code: Optional[str] = None
    destination_state: str = "Tamil Nadu"
    destination_pin: str = "600086"


class OrderCreateRequest(BaseModel):
    customer_id: Optional[str] = None
    session_id: Optional[str] = None
    items: Optional[List[OrderLineInput]] = None
    shipping_address_id: Optional[str] = None
    payment_method: str = "upi"
    coupon_code: Optional[str] = None
    request_key: Optional[str] = None
    hold_only: bool = False
    hold_seconds: Optional[int] = None


class OrderItemDTO(BaseModel):
    product_id: str
    sku: str
    product_name: str
    size: str
    quantity: int
    unit_mrp_inr: Decimal
    unit_discount_inr: Decimal
    unit_sale_value_inr: Decimal
    gst_rate_pct: Decimal
    gst_amount_inr: Decimal
    final_sale: bool


class OrderDTO(BaseModel):
    order_id: str
    customer_id: str
    status: str
    order_date: str
    items: List[OrderItemDTO]
    subtotal_mrp_inr: Decimal
    discount_inr: Decimal
    taxable_value_inr: Decimal
    cgst_inr: Decimal
    sgst_inr: Decimal
    igst_inr: Decimal
    total_gst_inr: Decimal
    shipping_fee_inr: Decimal
    grand_total_inr: Decimal
    currency: str
    payment_status: str
    invoice_id: Optional[str] = None
    tracking_number: Optional[str] = None
    signature_required: bool


class OrderCancelRequest(BaseModel):
    reason: str = "customer_requested_cancellation"
    request_key: Optional[str] = None


class PaymentInitiateRequest(BaseModel):
    order_id: str
    method: str = "upi"
    amount_inr: Optional[Decimal] = None


class ShipmentScheduleRequest(BaseModel):
    order_id: str
    carrier: str = "Noir Express"


class ShipmentDTO(BaseModel):
    shipment_id: str
    order_id: str
    carrier: str
    tracking_number: Optional[str] = None
    status: str
    scheduled_pickup: Optional[str] = None
    delivered_date: Optional[str] = None
    label_storage_key: Optional[str] = None
