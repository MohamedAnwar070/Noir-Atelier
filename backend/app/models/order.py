from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import SoftDeleteMixin, TimestampMixin, utc_now


class Cart(Base, TimestampMixin):
    __tablename__ = "cart"

    cart_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    customer_id: Mapped[Optional[str]] = mapped_column(
        String(16), ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=True, index=True
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sku: Mapped[str] = mapped_column(String(32), nullable=False)
    size: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (CheckConstraint("quantity > 0", name="ck_cart_quantity_positive"),)


class Coupon(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "coupons"

    coupon_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    discount_type: Mapped[str] = mapped_column(String(16), default="percent", nullable=False)
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    min_order_value_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    max_discount_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("1000.00"), nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    uses_remaining: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("customers.customer_id", ondelete="RESTRICT"), nullable=False
    )
    shipping_address_id: Mapped[Optional[str]] = mapped_column(
        String(16), ForeignKey("customer_addresses.address_id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), ForeignKey("order_statuses.code", ondelete="RESTRICT"), default="pending", nullable=False, index=True
    )
    subtotal_mrp_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    taxable_value_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cgst_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    sgst_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    igst_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    total_gst_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    shipping_fee_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    grand_total_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    coupon_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    signature_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hold_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_amount_paise: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    refund_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locker_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pickup_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)

    items: Mapped[List["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_orders_customer_order_date", "customer_id", "order_date"),)


class OrderItem(Base, TimestampMixin):
    __tablename__ = "order_items"

    item_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sku: Mapped[str] = mapped_column(String(32), nullable=False)
    product_name: Mapped[str] = mapped_column(String(160), nullable=False)
    size: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_mrp_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit_discount_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    unit_sale_value_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gst_rate_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    gst_amount_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    final_sale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")


class CouponUsage(Base, TimestampMixin):
    __tablename__ = "coupon_usage"

    usage_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    coupon_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("coupons.coupon_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    order_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False, unique=True
    )
    customer_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("customers.customer_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    discount_applied_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
