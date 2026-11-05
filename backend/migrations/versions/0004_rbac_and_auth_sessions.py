"""RBAC roles, permissions, staff accounts, and stateful JWT refresh sessions.

Revision ID: 0004_rbac_and_auth_sessions
Revises: 0003_catalog_reference_data
Create Date: 2026-11-04
"""

from typing import List, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision: str = "0004_rbac_and_auth_sessions"
down_revision: Union[str, None] = "0003_catalog_reference_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ts() -> List[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "roles" not in existing_tables:
        op.create_table(
            "roles",
            sa.Column("code", sa.String(32), primary_key=True),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("actor_type", sa.String(24), nullable=False),
            sa.Column("hierarchy_level", sa.Integer(), nullable=False, server_default="10"),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            *_ts(),
            sa.CheckConstraint("code = LOWER(code)", name="ck_roles_code_lower"),
            sa.CheckConstraint(
                "actor_type IN ('customer', 'admin', 'agent')",
                name="ck_roles_actor_type_valid",
            ),
        )
        op.create_index("ix_roles_actor_type", "roles", ["actor_type"])

    if "permissions" not in existing_tables:
        op.create_table(
            "permissions",
            sa.Column("code", sa.String(64), primary_key=True),
            sa.Column("resource", sa.String(32), nullable=False),
            sa.Column("action", sa.String(32), nullable=False),
            sa.Column("description", sa.String(200), nullable=False),
            *_ts(),
            sa.CheckConstraint("code = LOWER(code)", name="ck_permissions_code_lower"),
        )
        op.create_index("ix_permissions_resource", "permissions", ["resource"])

    if "role_permissions" not in existing_tables:
        op.create_table(
            "role_permissions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "role_code",
                sa.String(32),
                sa.ForeignKey("roles.code", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "permission_code",
                sa.String(64),
                sa.ForeignKey("permissions.code", ondelete="CASCADE"),
                nullable=False,
            ),
            *_ts(),
            sa.UniqueConstraint("role_code", "permission_code", name="uq_role_permissions_pair"),
        )
        op.create_index("ix_role_permissions_role_code", "role_permissions", ["role_code"])
        op.create_index("ix_role_permissions_permission_code", "role_permissions", ["permission_code"])

    if "staff_users" not in existing_tables:
        op.create_table(
            "staff_users",
            sa.Column("staff_id", sa.String(16), primary_key=True),
            sa.Column("email", sa.String(255), nullable=False, unique=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("phone", sa.String(32), nullable=True),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column(
                "role_code",
                sa.String(32),
                sa.ForeignKey("roles.code", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("department_scope", sa.String(16), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
            *_ts(),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("email = LOWER(email)", name="ck_staff_users_email_lower"),
            sa.CheckConstraint(
                "status IN ('active', 'suspended', 'locked')",
                name="ck_staff_users_status_valid",
            ),
        )
        op.create_index("ix_staff_users_email", "staff_users", ["email"], unique=True)
        op.create_index("ix_staff_users_role_code", "staff_users", ["role_code"])
        op.create_index("ix_staff_users_status", "staff_users", ["status"])

    if "auth_sessions" not in existing_tables:
        op.create_table(
            "auth_sessions",
            sa.Column("session_id", sa.String(40), primary_key=True),
            sa.Column("token_family", sa.String(36), nullable=False),
            sa.Column("actor_type", sa.String(24), nullable=False),
            sa.Column("actor_id", sa.String(32), nullable=False),
            sa.Column(
                "role_code",
                sa.String(32),
                sa.ForeignKey("roles.code", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("refresh_token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("access_jti", sa.String(36), nullable=False),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column("user_agent", sa.String(255), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoke_reason", sa.String(64), nullable=True),
            sa.Column("replaced_by_session_id", sa.String(40), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            *_ts(),
            sa.CheckConstraint(
                "actor_type IN ('customer', 'admin')",
                name="ck_auth_sessions_actor_type_valid",
            ),
        )
        op.create_index("ix_auth_sessions_token_family", "auth_sessions", ["token_family"])
        op.create_index("ix_auth_sessions_actor_id", "auth_sessions", ["actor_id"])
        op.create_index("ix_auth_sessions_role_code", "auth_sessions", ["role_code"])
        op.create_index("ix_auth_sessions_refresh_token_hash", "auth_sessions", ["refresh_token_hash"], unique=True)
        op.create_index("ix_auth_sessions_access_jti", "auth_sessions", ["access_jti"])
        op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
        op.create_index("ix_auth_sessions_actor_active", "auth_sessions", ["actor_type", "actor_id", "revoked_at"])

    customer_cols = {c["name"] for c in insp.get_columns("customers")}
    with op.batch_alter_table("customers") as batch_op:
        if "failed_login_attempts" not in customer_cols:
            batch_op.add_column(
                sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0")
            )
        if "locked_until" not in customer_cols:
            batch_op.add_column(
                sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True)
            )

    from backend.app.reference_data import ensure_reference_data

    session = Session(bind=bind)
    # Frozen to this revision's tables (see reference_data.ensure_reference_data).
    ensure_reference_data(session, tables=("roles", "permissions", "role_permissions"))
    session.flush()


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())
    customer_cols = {c["name"] for c in insp.get_columns("customers")} if "customers" in existing_tables else set()

    if "failed_login_attempts" in customer_cols or "locked_until" in customer_cols:
        with op.batch_alter_table("customers") as batch_op:
            if "locked_until" in customer_cols:
                batch_op.drop_column("locked_until")
            if "failed_login_attempts" in customer_cols:
                batch_op.drop_column("failed_login_attempts")

    if "auth_sessions" in existing_tables:
        op.drop_table("auth_sessions")
    if "staff_users" in existing_tables:
        op.drop_table("staff_users")
    if "role_permissions" in existing_tables:
        op.drop_table("role_permissions")
    if "permissions" in existing_tables:
        op.drop_table("permissions")
    if "roles" in existing_tables:
        op.drop_table("roles")
