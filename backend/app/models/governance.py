from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import SoftDeleteMixin, TimestampMixin, utc_now


class SupportTicket(Base, TimestampMixin):
    __tablename__ = "support_tickets"

    ticket_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    customer_id: Mapped[Optional[str]] = mapped_column(
        String(16), ForeignKey("customers.customer_id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        String(16), ForeignKey("orders.order_id", ondelete="SET NULL"), nullable=True, index=True
    )
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), default="general", nullable=False)
    priority: Mapped[str] = mapped_column(String(24), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    on_behalf_of: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    change_details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_audit_log_actor_timestamp", "actor_type", "actor_id", "timestamp"),)


class ComplianceFlag(Base, TimestampMixin):
    __tablename__ = "compliance_flags"

    flag_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[Optional[str]] = mapped_column(
        String(16), ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=True, index=True
    )
    flag_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), default="medium", nullable=False)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class FraudFlag(Base, TimestampMixin):
    __tablename__ = "fraud_flags"

    fraud_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False, index=True
    )
    flag_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), default="medium", nullable=False)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class BusinessConfig(Base, TimestampMixin):
    __tablename__ = "business_config"

    config_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    config_value: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    data_type: Mapped[str] = mapped_column(String(24), default="json", nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), default="system", nullable=False)


class Policy(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "policies"

    policy_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    topic: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    rule_text: Mapped[str] = mapped_column(Text, nullable=False)
    applies_to: Mapped[str] = mapped_column(String(40), default="all_garments", nullable=False)
    return_window_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    version: Mapped[str] = mapped_column(String(16), default="1.0", nullable=False)


class AgentPermission(Base, TimestampMixin):
    __tablename__ = "agent_permissions"

    perm_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    service_account: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    allowed_endpoints: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    max_value_inr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Customer-facing agents (shopping assistant, stylist) may touch a shopper's own
    # records only, and only while acting for that shopper (X-On-Behalf-Of). Enforced
    # server-side by auth.assert_customer_access, never trusted to the agent.
    customer_scoped: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)


class AgentSession(Base, TimestampMixin):
    __tablename__ = "agent_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[Optional[str]] = mapped_column(
        String(16), ForeignKey("customers.customer_id", ondelete="SET NULL"), nullable=True, index=True
    )
    verified_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    failed_verifications: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    state_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


# Outcome of one assistant turn (CHECK constraint generated from this tuple).
AGENT_TRACE_STATUSES = ("answered", "fallback", "error", "blocked")


class AgentTrace(Base):
    """Internal, structured record of ONE assistant turn — never shown to shoppers.

    Holds what the runtime understood, planned, called, checked and replied, so a
    conversation can be audited and debugged. Free text is PII-scrubbed before it is
    stored. Readable only with the `agents:trace_read` permission.
    """

    __tablename__ = "agent_traces"

    trace_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_id: Mapped[Optional[str]] = mapped_column(
        String(16), ForeignKey("customers.customer_id", ondelete="SET NULL"), nullable=True, index=True
    )
    runtime: Mapped[str] = mapped_column(String(16), nullable=False)  # llm | offline
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    intent: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # reported by the model
    plan_note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    reply: Mapped[str] = mapped_column(Text, nullable=False)
    product_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    tool_calls: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    evaluation: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    errors: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    usage: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in AGENT_TRACE_STATUSES) + ")",
            name="ck_agent_traces_status",
        ),
        Index("ix_agent_traces_session_created", "session_id", "created_at"),
        Index("ix_agent_traces_created", "created_at"),
        Index("ix_agent_traces_status_created", "status", "created_at"),
    )


class IdempotencyKey(Base, TimestampMixin):
    __tablename__ = "idempotency_keys"

    request_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    response_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
