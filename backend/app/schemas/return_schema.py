from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ReturnCreateRequest(BaseModel):
    order_id: str
    reason_category: str = "size_mismatch"
    customer_notes: Optional[str] = None
    tag_intact: bool = True
    qc_passed: bool = True
    is_defective_claim: bool = False
    request_key: Optional[str] = None


class ReturnInspectRequest(BaseModel):
    tag_intact: bool
    qc_passed: bool
    qc_notes: Optional[str] = None


class ReturnDTO(BaseModel):
    return_id: str
    order_id: str
    reason_category: str
    status: str
    tag_intact: Optional[bool]
    qc_passed: Optional[bool]
    return_shipping_label_url: Optional[str]
    refund_id: Optional[str] = None
    approval_tier: int = 1


class RefundApproveRequest(BaseModel):
    reason: str = "policy_verified_qc_passed"
    amount_inr: Optional[Decimal] = Field(default=None, gt=0)


class RefundDTO(BaseModel):
    refund_id: str
    return_id: Optional[str]
    order_id: str
    amount_inr: Decimal
    approval_tier: int
    status: str
    reason: str
    approved_by: Optional[str]
    secondary_approved_by: Optional[str]
    payment_refund_id: Optional[str]


class SupportEscalateRequest(BaseModel):
    customer_id: Optional[str] = None
    order_id: Optional[str] = None
    subject: str
    description: str
    category: str = "general"
    priority: str = "medium"


class SupportTicketDTO(BaseModel):
    ticket_id: str
    customer_id: Optional[str]
    order_id: Optional[str]
    subject: str
    description: str
    category: str
    priority: str
    status: str
    created_by: str
    assigned_to: Optional[str]
