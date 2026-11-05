"""Per-size stock (variant_inventory) and an append-only stock ledger (inventory_movements).

Revision ID: 0006_variant_inventory
Revises: 0005_stylist_style_attributes
Create Date: 2026-11-05

Why
---
Stock was one number per product, so a sold-out size could still be sold, and the
per-size JSON (inventory.size_breakdown) was never updated by orders, cancels or
returns. Stock now lives on the size (variant), and every change is a ledger row.

Expand / contract
-----------------
This revision EXPANDS: it creates the new tables and backfills them. The old
`inventory` table is left in place (no code uses it any more) and is dropped by
0007 once production has run cleanly. The downgrade writes the per-size levels
back into `inventory`, so rolling back loses no stock changes made meanwhile.

Backfill rules (logic frozen here, independent of app code)
------------------------------------------------------------
1. Start from inventory.size_breakdown[size] for each active size.
2. The product total (inventory.quantity_available) is the truth — orders always
   decremented it. If the sizes do not sum to it, rescale them proportionally
   (largest remainder) so they do; with no usable breakdown, split evenly.
3. reserved per size = units of PENDING orders for that product and size (exact).
4. damaged goes to the first active size.
5. One `opening_balance` ledger row per size with non-zero stock.
6. Every rescaled product is printed (id, before, after).
"""
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_variant_inventory"
down_revision: Union[str, None] = "0005_stylist_style_attributes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MOVEMENT_TYPES = (
    "opening_balance", "sale", "hold", "hold_release", "hold_capture", "late_capture",
    "cancel_restock", "return_restock", "restock", "adjustment", "damage",
)
_PER_SIZE_LOW_STOCK_MAX = 2
_REMOVED_ENDPOINT = "/api/inventory/reserve"


def _ts():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def _create_tables() -> None:
    op.create_table(
        "variant_inventory",
        sa.Column(
            "variant_id", sa.Integer(),
            sa.ForeignKey("product_variants.variant_id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("quantity_available", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quantity_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quantity_damaged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("low_stock_threshold", sa.Integer(), nullable=False, server_default="2"),
        *_ts(),
        sa.CheckConstraint("quantity_available >= 0", name="ck_variant_inventory_available_non_negative"),
        sa.CheckConstraint("quantity_reserved >= 0", name="ck_variant_inventory_reserved_non_negative"),
        sa.CheckConstraint("quantity_damaged >= 0", name="ck_variant_inventory_damaged_non_negative"),
        sa.CheckConstraint("low_stock_threshold >= 0", name="ck_variant_inventory_threshold_non_negative"),
    )
    op.create_table(
        "inventory_movements",
        sa.Column("movement_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "variant_id", sa.Integer(),
            sa.ForeignKey("product_variants.variant_id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("movement_type", sa.String(24), nullable=False),
        sa.Column("delta_available", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delta_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delta_damaged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reference_type", sa.String(16), nullable=True),
        sa.Column("reference_id", sa.String(32), nullable=True),
        sa.Column("actor_id", sa.String(64), nullable=True),
        sa.Column("reason", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "movement_type IN (" + ", ".join(f"'{t}'" for t in _MOVEMENT_TYPES) + ")",
            name="ck_inventory_movements_type",
        ),
        sa.CheckConstraint(
            "delta_available <> 0 OR delta_reserved <> 0 OR delta_damaged <> 0",
            name="ck_inventory_movements_non_zero",
        ),
    )
    op.create_index("ix_inventory_movements_variant_created", "inventory_movements", ["variant_id", "created_at"])
    op.create_index("ix_inventory_movements_reference", "inventory_movements", ["reference_type", "reference_id"])


def _rescale(base: Dict[str, int], sizes: List[str], total: int) -> Dict[str, int]:
    """Distribute ``total`` across ``sizes`` in proportion to ``base`` (largest remainder)."""
    weight = sum(base.values())
    if weight <= 0:
        q, r = divmod(total, len(sizes))
        return {s: q + (1 if i < r else 0) for i, s in enumerate(sizes)}
    exact = {s: total * base[s] / weight for s in sizes}
    out = {s: int(exact[s]) for s in sizes}
    leftover = total - sum(out.values())
    for s in sorted(sizes, key=lambda s: (-(exact[s] - out[s]), sizes.index(s)))[:leftover]:
        out[s] += 1
    return out


def _backfill(bind) -> None:
    variants = bind.execute(
        sa.text(
            "SELECT variant_id, product_id, size, is_active FROM product_variants "
            "ORDER BY product_id, position, size"
        )
    ).all()
    already = {r[0] for r in bind.execute(sa.text("SELECT variant_id FROM variant_inventory")).all()}
    legacy = {
        r.product_id: r
        for r in bind.execute(
            sa.text(
                "SELECT product_id, quantity_available, quantity_reserved, quantity_damaged, "
                "size_breakdown, low_stock_threshold FROM inventory"
            )
        ).all()
    }
    pending = defaultdict(int)
    for pid, size, qty in bind.execute(
        sa.text(
            "SELECT oi.product_id, oi.size, SUM(oi.quantity) FROM order_items oi "
            "JOIN orders o ON o.order_id = oi.order_id WHERE o.status = 'pending' "
            "GROUP BY oi.product_id, oi.size"
        )
    ).all():
        pending[(pid, str(size).upper())] += int(qty)

    by_product: Dict[str, list] = defaultdict(list)
    for v in variants:
        if v.variant_id not in already:
            by_product[v.product_id].append(v)

    now = datetime.now(timezone.utc)  # explicit: the tables may come from create_all (no server defaults)
    vi_rows, mv_rows, rescaled = [], [], []
    for pid, vs in by_product.items():
        inv = legacy.get(pid)
        active = [v.size for v in vs if v.is_active] or [v.size for v in vs]
        total = int(inv.quantity_available) if inv else 0
        raw = inv.size_breakdown if inv and isinstance(inv.size_breakdown, dict) else {}
        base = {s: max(0, int(raw.get(s, 0) or 0)) for s in active}
        levels = base if sum(base.values()) == total else _rescale(base, active, total)
        if levels != base:
            rescaled.append((pid, base, levels))
        threshold = min(int(inv.low_stock_threshold), _PER_SIZE_LOW_STOCK_MAX) if inv else _PER_SIZE_LOW_STOCK_MAX
        damaged_left = int(inv.quantity_damaged) if inv else 0
        for v in vs:
            avail = levels.get(v.size, 0) if v.size in active else 0
            reserved = pending.get((pid, v.size), 0)
            damaged = damaged_left if v.size == active[0] else 0
            vi_rows.append({
                "variant_id": v.variant_id, "quantity_available": avail, "quantity_reserved": reserved,
                "quantity_damaged": damaged, "low_stock_threshold": threshold,
                "created_at": now, "updated_at": now,
            })
            if avail or reserved or damaged:
                mv_rows.append({
                    "variant_id": v.variant_id, "movement_type": "opening_balance",
                    "delta_available": avail, "delta_reserved": reserved, "delta_damaged": damaged,
                    "reference_type": "migration", "reference_id": "0006", "actor_id": "system",
                    "reason": "backfill from product-level inventory", "created_at": now,
                })

    vi = sa.table(
        "variant_inventory", sa.column("variant_id"), sa.column("quantity_available"),
        sa.column("quantity_reserved"), sa.column("quantity_damaged"), sa.column("low_stock_threshold"),
        sa.column("created_at"), sa.column("updated_at"),
    )
    mv = sa.table(
        "inventory_movements", sa.column("variant_id"), sa.column("movement_type"),
        sa.column("delta_available"), sa.column("delta_reserved"), sa.column("delta_damaged"),
        sa.column("reference_type"), sa.column("reference_id"), sa.column("actor_id"), sa.column("reason"),
        sa.column("created_at"),
    )
    if vi_rows:
        bind.execute(vi.insert(), vi_rows)
    if mv_rows:
        bind.execute(mv.insert(), mv_rows)
    print(f"[0006] per-size stock rows: {len(vi_rows)}, opening movements: {len(mv_rows)}, rescaled products: {len(rescaled)}")
    for pid, before, after in rescaled:
        print(f"[0006]   {pid}: {before} -> {after}")


def _update_endpoint_lists(bind, transform) -> None:
    """agent_permissions.allowed_endpoints is JSON: rewrite it in Python (portable)."""
    import json

    for perm_id, endpoints in bind.execute(sa.text("SELECT perm_id, allowed_endpoints FROM agent_permissions")).all():
        current = json.loads(endpoints) if isinstance(endpoints, str) else list(endpoints or [])
        updated = transform(current)
        if updated != current:
            bind.execute(
                sa.text("UPDATE agent_permissions SET allowed_endpoints = :e WHERE perm_id = :i"),
                {"e": json.dumps(updated), "i": perm_id},
            )


def upgrade() -> None:
    bind = op.get_bind()
    # Fresh databases already have the tables from 0001's create_all.
    if "variant_inventory" not in sa.inspect(bind).get_table_names():
        _create_tables()
    _backfill(bind)
    # Holds go only through /api/orders/hold now; the raw reserve endpoint is gone.
    _update_endpoint_lists(bind, lambda eps: [e for e in eps if e != _REMOVED_ENDPOINT])


def downgrade() -> None:
    bind = op.get_bind()
    # Write per-size levels back to the product-level table so nothing is lost.
    rows = bind.execute(
        sa.text(
            "SELECT pv.product_id, pv.size, vi.quantity_available, vi.quantity_reserved, vi.quantity_damaged "
            "FROM variant_inventory vi JOIN product_variants pv ON pv.variant_id = vi.variant_id"
        )
    ).all()
    totals: Dict[str, Dict] = defaultdict(lambda: {"a": 0, "r": 0, "d": 0, "sizes": {}})
    for pid, size, a, r, d in rows:
        t = totals[pid]
        t["a"] += a
        t["r"] += r
        t["d"] += d
        t["sizes"][size] = a
    import json

    for pid, t in totals.items():
        bind.execute(
            sa.text(
                "UPDATE inventory SET quantity_available = :a, quantity_reserved = :r, quantity_damaged = :d, "
                "size_breakdown = :s WHERE product_id = :p"
            ),
            {"a": t["a"], "r": t["r"], "d": t["d"], "s": json.dumps(t["sizes"]), "p": pid},
        )
    _update_endpoint_lists(
        bind,
        lambda eps: eps + [_REMOVED_ENDPOINT] if "/api/shipments/schedule" in eps and _REMOVED_ENDPOINT not in eps else eps,
    )
    op.drop_index("ix_inventory_movements_reference", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_variant_created", table_name="inventory_movements")
    op.drop_table("inventory_movements")
    op.drop_table("variant_inventory")
