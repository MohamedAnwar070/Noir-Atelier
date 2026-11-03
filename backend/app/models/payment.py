from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, ForeignKey, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import SoftDeleteMixin, TimestampMixin


class PaymentMethod(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "payment_methods"

    method_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    min_order_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    max_order_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("200000.00"), nullable=False)
    icon_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    payment_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("orders.order_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    amount_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(80), unique=True, nullable=True)
    gateway_response: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    invoice_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("orders.order_id", ondelete="RESTRICT"), unique=True, nullable=False, index=True
    )
    seller_gstin: Mapped[str] = mapped_column(String(20), nullable=False)
    place_of_supply_state: Mapped[str] = mapped_column(String(64), nullable=False)
    is_intra_state: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    taxable_value_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cgst_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    sgst_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    igst_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    total_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
