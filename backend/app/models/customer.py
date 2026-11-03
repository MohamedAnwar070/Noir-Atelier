from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import SoftDeleteMixin, TimestampMixin


class Customer(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    loyalty_tier: Mapped[str] = mapped_column(String(32), default="STANDARD", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    addresses: Mapped[List["CustomerAddress"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
    preference: Mapped[Optional["CustomerPreference"]] = relationship(
        back_populates="customer", uselist=False, cascade="all, delete-orphan"
    )


class CustomerAddress(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "customer_addresses"

    address_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(32), default="Home", nullable=False)
    street: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(80), nullable=False)
    pin_code: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(64), default="India", nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    customer: Mapped["Customer"] = relationship(back_populates="addresses")


class CustomerPreference(Base, TimestampMixin):
    __tablename__ = "customer_preferences"

    pref_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("customers.customer_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    preferred_department: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    preferred_sizes: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sms_notifications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    newsletter: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dpdp_consent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    referral_code: Mapped[Optional[str]] = mapped_column(String(32), unique=True, nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="preference")


class CustomerVector(Base, TimestampMixin):
    __tablename__ = "customer_vectors"

    vector_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("customers.customer_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    qdrant_point_id: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(80), nullable=False)
    style_profile: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_customer_vectors_customer_id", "customer_id"),)
