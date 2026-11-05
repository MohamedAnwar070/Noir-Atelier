"""Shopping-assistant runtime: customer-scoped agents, internal turn traces, trace RBAC.

Revision ID: 0007_agent_runtime
Revises: 0006_variant_inventory
Create Date: 2026-11-05

Schema
------
agent_permissions.customer_scoped  agents that serve shoppers may only touch the records of
                                   the shopper they act for (enforced in auth.assert_customer_access)
agent_traces                       one internal, PII-scrubbed record per assistant turn
                                   (intent, plan note, tool calls, evaluation, errors, usage)

Data (frozen here, plain SQL)
-----------------------------
* svc-stylist becomes customer-scoped.
* svc-assistant: the read-only, customer-scoped grant for the shopping assistant.
* permission `agents:trace_read`, granted to `manager` and `super_admin`.

(The planned contract migration that drops the legacy `inventory` table moves to 0008.)
"""
import json
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_agent_runtime"
down_revision: Union[str, None] = "0006_variant_inventory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TRACE_STATUSES = ("answered", "fallback", "error", "blocked")
_ASSISTANT_ENDPOINTS = [
    "/api/catalog/attributes",
    "/api/catalog/search",
    "/api/products/{id}",
    "/api/products/{id}/recommendations",
    "/api/config/policies",
    "/api/orders",
    "/api/orders/{id}",
    "/api/shipments/{id}",
    "/api/returns/{id}",
    "/api/agents/sessions/{id}/profile",
]
_TRACE_PERMISSION = "agents:trace_read"
_TRACE_ROLES = ("manager", "super_admin")


def _columns(bind, table: str) -> set:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _create_traces_table() -> None:
    op.create_table(
        "agent_traces",
        sa.Column("trace_id", sa.String(32), primary_key=True),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column(
            "customer_id", sa.String(16),
            sa.ForeignKey("customers.customer_id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("runtime", sa.String(16), nullable=False),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("intent", sa.String(32), nullable=True),
        sa.Column("plan_note", sa.String(300), nullable=True),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("reply", sa.Text(), nullable=False),
        sa.Column("product_ids", sa.JSON(), nullable=False),
        sa.Column("tool_calls", sa.JSON(), nullable=False),
        sa.Column("evaluation", sa.JSON(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in _TRACE_STATUSES) + ")", name="ck_agent_traces_status"
        ),
    )
    op.create_index("ix_agent_traces_customer_id", "agent_traces", ["customer_id"])
    op.create_index("ix_agent_traces_session_created", "agent_traces", ["session_id", "created_at"])
    op.create_index("ix_agent_traces_created", "agent_traces", ["created_at"])
    op.create_index("ix_agent_traces_status_created", "agent_traces", ["status", "created_at"])


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    # Fresh databases get both from 0001's create_all.
    if "customer_scoped" not in _columns(bind, "agent_permissions"):
        op.add_column(
            "agent_permissions",
            sa.Column("customer_scoped", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "agent_traces" not in sa.inspect(bind).get_table_names():
        _create_traces_table()

    bind.execute(sa.text("UPDATE agent_permissions SET customer_scoped = :t WHERE service_account = 'svc-stylist'"), {"t": True})
    if bind.execute(sa.text("SELECT 1 FROM agent_permissions WHERE service_account = 'svc-assistant'")).first() is None:
        bind.execute(
            sa.text(
                "INSERT INTO agent_permissions (agent_type, service_account, resource_type, action, allowed_endpoints, "
                "customer_scoped, created_at, updated_at) VALUES ('shopping_assistant', 'svc-assistant', 'storefront', "
                "'read', :e, :t, :n, :n)"
            ),
            {"e": json.dumps(_ASSISTANT_ENDPOINTS), "t": True, "n": now},
        )

    if bind.execute(sa.text("SELECT 1 FROM permissions WHERE code = :c"), {"c": _TRACE_PERMISSION}).first() is None:
        bind.execute(
            sa.text(
                "INSERT INTO permissions (code, resource, action, description, created_at, updated_at) "
                "VALUES (:c, 'agents', 'trace_read', :d, :n, :n)"
            ),
            {
                "c": _TRACE_PERMISSION,
                "d": "Inspect internal shopping-assistant traces (tool calls, checks, errors) for audit and debugging.",
                "n": now,
            },
        )
    for role in _TRACE_ROLES:
        role_exists = bind.execute(sa.text("SELECT 1 FROM roles WHERE code = :r"), {"r": role}).first()
        granted = bind.execute(
            sa.text("SELECT 1 FROM role_permissions WHERE role_code = :r AND permission_code = :c"),
            {"r": role, "c": _TRACE_PERMISSION},
        ).first()
        if role_exists and not granted:
            bind.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_code, permission_code, created_at, updated_at) "
                    "VALUES (:r, :c, :n, :n)"
                ),
                {"r": role, "c": _TRACE_PERMISSION, "n": now},
            )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = :c"), {"c": _TRACE_PERMISSION})
    bind.execute(sa.text("DELETE FROM permissions WHERE code = :c"), {"c": _TRACE_PERMISSION})
    bind.execute(sa.text("DELETE FROM agent_permissions WHERE service_account = 'svc-assistant'"))
    op.drop_index("ix_agent_traces_status_created", table_name="agent_traces")
    op.drop_index("ix_agent_traces_created", table_name="agent_traces")
    op.drop_index("ix_agent_traces_session_created", table_name="agent_traces")
    op.drop_index("ix_agent_traces_customer_id", table_name="agent_traces")
    op.drop_table("agent_traces")
    op.drop_column("agent_permissions", "customer_scoped")
