"""Status and reason vocabularies.

Transitions between statuses are business logic and stay in the services;
the *vocabulary* lives here so that:
  * every stored status is valid (orders.status / refunds.status are FKs),
  * customer-facing labels, tones and policy flags have one source of truth,
  * the storefront renders whatever the backend defines (GET /api/catalog/meta).
"""

from sqlalchemy import Boolean, CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin

UI_TONES = ("neutral", "info", "success", "warning", "error")
_TONE_CHECK = "tone IN ('neutral', 'info', 'success', 'warning', 'error')"


class OrderStatus(Base, TimestampMixin):
    __tablename__ = "order_statuses"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    tone: Mapped[str] = mapped_column(String(16), default="neutral", nullable=False)
    # Policy flags read by order_service / returns_service (and shown by the UI).
    is_cancellable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_returnable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (CheckConstraint(_TONE_CHECK, name="ck_order_statuses_tone"),)


class RefundStatus(Base, TimestampMixin):
    __tablename__ = "refund_statuses"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    tone: Mapped[str] = mapped_column(String(16), default="neutral", nullable=False)
    # True while an approver still has to act (drives the admin approval queue).
    awaiting_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (CheckConstraint(_TONE_CHECK, name="ck_refund_statuses_tone"),)


class ReturnReason(Base, TimestampMixin):
    """Why a customer returns a garment.

    `is_defect_claim` is decided here, server-side — never by the client —
    because defect claims bypass Final Sale and late-window rules.
    """

    __tablename__ = "return_reasons"

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    is_defect_claim: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


__all__ = ["UI_TONES", "OrderStatus", "RefundStatus", "ReturnReason"]
