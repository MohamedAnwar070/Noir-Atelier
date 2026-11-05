from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import SoftDeleteMixin, TimestampMixin, utc_now


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    hierarchy_level: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    role_permissions: Mapped[List["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )
    staff_users: Mapped[List["StaffUser"]] = relationship(back_populates="role")

    __table_args__ = (
        CheckConstraint("code = LOWER(code)", name="ck_roles_code_lower"),
        CheckConstraint(
            "actor_type IN ('customer', 'admin', 'agent')",
            name="ck_roles_actor_type_valid",
        ),
    )


class Permission(Base, TimestampMixin):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)

    role_permissions: Mapped[List["RolePermission"]] = relationship(
        back_populates="permission", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("code = LOWER(code)", name="ck_permissions_code_lower"),
    )


class RolePermission(Base, TimestampMixin):
    __tablename__ = "role_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_code: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("roles.code", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("permissions.code", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped["Role"] = relationship(back_populates="role_permissions")
    permission: Mapped["Permission"] = relationship(back_populates="role_permissions")

    __table_args__ = (
        UniqueConstraint("role_code", "permission_code", name="uq_role_permissions_pair"),
    )


class StaffUser(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "staff_users"

    staff_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_code: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("roles.code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    department_scope: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False, index=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    role: Mapped["Role"] = relationship(back_populates="staff_users")

    __table_args__ = (
        CheckConstraint("email = LOWER(email)", name="ck_staff_users_email_lower"),
        CheckConstraint(
            "status IN ('active', 'suspended', 'locked')",
            name="ck_staff_users_status_valid",
        ),
    )


class AuthSession(Base, TimestampMixin):
    __tablename__ = "auth_sessions"

    session_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    token_family: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role_code: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("roles.code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    access_jti: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    replaced_by_session_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('customer', 'admin')",
            name="ck_auth_sessions_actor_type_valid",
        ),
        Index("ix_auth_sessions_actor_active", "actor_type", "actor_id", "revoked_at"),
    )
