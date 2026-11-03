from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import SoftDeleteMixin, TimestampMixin, utc_now


class ShippingZone(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "shipping_zones"

    zone_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    pin_prefixes: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    base_fee_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    per_kg_fee_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    estimated_days: Mapped[int] = mapped_column(Integer, default=3, nullable=False)


class Shipment(Base, TimestampMixin):
    __tablename__ = "shipments"

    shipment_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("orders.order_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    carrier: Mapped[str] = mapped_column(String(64), default="Noir Express", nullable=False)
    tracking_number: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="picking", nullable=False)
    scheduled_pickup: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    shipped_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    signature_proof: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    label_storage_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class ReturnRequest(Base, TimestampMixin):
    __tablename__ = "returns"

    return_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("orders.order_id", ondelete="RESTRICT"), nullable=False
    )
    reason_category: Mapped[str] = mapped_column(
        String(40), ForeignKey("return_reasons.code", ondelete="RESTRICT"), nullable=False, index=True
    )
    customer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    initiated_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="requested", nullable=False, index=True)
    tag_intact: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    qc_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    qc_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    return_shipping_label_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    evidence_storage_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (Index("ix_returns_order_initiated", "order_id", "initiated_date"),)


class Refund(Base, TimestampMixin):
    __tablename__ = "refunds"

    refund_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    return_id: Mapped[Optional[str]] = mapped_column(
        String(16), ForeignKey("returns.return_id", ondelete="RESTRICT"), nullable=True, index=True
    )
    order_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("orders.order_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    approval_tier: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), ForeignKey("refund_statuses.code", ondelete="RESTRICT"), default="pending_approval", nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    secondary_approved_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approved_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_refund_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
