from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class CartAddRequest(BaseModel):
    product_id: str
    size: str = "M"
    quantity: int = Field(default=1, gt=0)
    session_id: Optional[str] = None
    customer_id: Optional[str] = None


class CartItemDTO(BaseModel):
    cart_id: str
    product_id: str
    sku: str
    product_name: str
    size: str
    quantity: int
    unit_mrp_inr: Decimal
    line_mrp_inr: Decimal
    gst_rate_pct: Decimal
    included_gst_inr: Decimal


class CartSummaryDTO(BaseModel):
    session_id: str
    customer_id: Optional[str] = None
    items: List[CartItemDTO]
    subtotal_mrp_inr: Decimal
    discount_inr: Decimal
    taxable_value_inr: Decimal
    cgst_inr: Decimal
    sgst_inr: Decimal
    igst_inr: Decimal
    total_gst_inr: Decimal
    shipping_fee_inr: Decimal
    grand_total_inr: Decimal
    free_shipping_applied: bool


class CouponValidateRequest(BaseModel):
    code: str
    cart_total_inr: Decimal = Field(gt=0)


class CouponValidateResponse(BaseModel):
    valid: bool
    code: str
    discount_inr: Decimal
    new_total_inr: Decimal
    message: str
