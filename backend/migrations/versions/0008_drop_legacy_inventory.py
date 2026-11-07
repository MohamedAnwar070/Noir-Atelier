"""Contract: drop the legacy product-level `inventory` table.

Revision ID: 0008_drop_legacy_inventory
Revises: 0007_agent_runtime
Create Date: 2026-11-07

0006 moved stock to `variant_inventory` (per size) plus the `inventory_movements`
ledger and left `inventory` in place, unused, so a rollback could not lose data.
No code has read or written it since. This revision completes the
expand -> backfill -> switch -> contract sequence.

Downgrade recreates the table in its original shape and fills it from the live
per-size levels (totals, reserved, damaged and a size breakdown), so 0006's own
downgrade still works afterwards.
"""
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_drop_legacy_inventory"
down_revision: Union[str, None] = "0007_agent_runtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "inventory" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index("ix_inventory_product_id", table_name="inventory")
        op.drop_table("inventory")


def downgrade() -> None:
    op.create_table(
        "inventory",
        sa.Column("inventory_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.String(16), sa.ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity_available", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quantity_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quantity_damaged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("size_breakdown", sa.JSON(), nullable=False),
        sa.Column("low_stock_threshold", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("last_sync", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("quantity_available >= 0", name="ck_inventory_avail_non_negative"),
        sa.CheckConstraint("quantity_reserved >= 0", name="ck_inventory_reserved_non_negative"),
    )
    op.create_index("ix_inventory_product_id", "inventory", ["product_id"], unique=True)

    bind = op.get_bind()
    totals: Dict[str, Dict] = defaultdict(lambda: {"a": 0, "r": 0, "d": 0, "sizes": {}})
    for pid, size, active, a, r, d in bind.execute(
        sa.text(
            "SELECT pv.product_id, pv.size, pv.is_active, vi.quantity_available, vi.quantity_reserved, "
            "vi.quantity_damaged FROM variant_inventory vi JOIN product_variants pv ON pv.variant_id = vi.variant_id"
        )
    ).all():
        t = totals[pid]
        t["a"] += a
        t["r"] += r
        t["d"] += d
        if active:
            t["sizes"][size] = a
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # column is timestamp without time zone
    rows = [
        {"p": pid, "a": t["a"], "r": t["r"], "d": t["d"], "s": json.dumps(t["sizes"]), "n": now}
        for pid, t in sorted(totals.items())
    ]
    if rows:
        bind.execute(
            sa.text(
                "INSERT INTO inventory (product_id, quantity_available, quantity_reserved, quantity_damaged, "
                "size_breakdown, low_stock_threshold, created_at, updated_at) VALUES (:p, :a, :r, :d, :s, 5, :n, :n)"
            ),
            rows,
        )
