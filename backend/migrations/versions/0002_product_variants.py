"""Per-size product variants: each size owns its SKU and price.

Revision ID: 0002_product_variants
Revises: 0001_initial
Create Date: 2026-11-03

What this does
--------------
1. Creates ``product_variants`` (one row per product + size) unless it already
   exists — 0001 runs ``create_all`` from the current models, so fresh databases
   get the table there.
2. Backfills a variant for every size of every product that has none yet. Prices
   are NOT invented: each size starts at the product's current price; set real
   per-size prices with ``PUT /api/products/{id}/variants/{size}``.
3. Normalises ``products.sku`` to a size-free style code (legacy rows stored one
   size's SKU, e.g. "PRD-002-CHR-L", on the product).
4. Corrects ``sku`` on existing cart and order lines, which recorded that single
   product SKU regardless of the size actually bought.

This migration is deliberately self-contained (no app-service imports) so its
behaviour never changes when application code evolves.
"""
import json
from typing import Dict, List, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_product_variants"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copy of the size display order at the time of this migration.
_SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "2Y", "4Y", "6Y", "8Y", "10Y", "12Y", "14Y"]


def _style_code(sku: str, sizes: List[str]) -> str:
    head, _, tail = sku.strip().upper().rpartition("-")
    return head if head and tail in set(sizes) | set(_SIZE_ORDER) else sku.strip().upper()


def _position(size: str) -> int:
    return _SIZE_ORDER.index(size) if size in _SIZE_ORDER else len(_SIZE_ORDER)


def upgrade() -> None:
    bind = op.get_bind()
    if "product_variants" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "product_variants",
            sa.Column("variant_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "product_id",
                sa.String(16),
                sa.ForeignKey("products.product_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("size", sa.String(16), nullable=False),
            sa.Column("sku", sa.String(32), nullable=False),
            sa.Column("mrp_inr", sa.Numeric(12, 2), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("product_id", "size", name="uq_product_variants_product_size"),
            sa.CheckConstraint("mrp_inr > 0", name="ck_product_variants_mrp_positive"),
        )
        op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"])
        op.create_index("ix_product_variants_sku", "product_variants", ["sku"], unique=True)

    products = bind.execute(
        sa.text("SELECT product_id, sku, mrp_inr, sizes_available FROM products")
    ).mappings().all()
    has_variants = {
        row[0] for row in bind.execute(sa.text("SELECT DISTINCT product_id FROM product_variants"))
    }

    for prod in products:
        raw_sizes = prod["sizes_available"]
        if isinstance(raw_sizes, str):  # JSON column read back as text on some drivers
            raw_sizes = json.loads(raw_sizes or "[]")
        sizes = [str(s).strip().upper() for s in (raw_sizes or []) if str(s).strip()]
        style = _style_code(prod["sku"], sizes)
        sku_by_size: Dict[str, str] = {size: f"{style}-{size}" for size in sizes}

        if prod["product_id"] not in has_variants:
            for size, sku in sku_by_size.items():
                bind.execute(
                    sa.text(
                        "INSERT INTO product_variants (product_id, size, sku, mrp_inr, position, is_active) "
                        "VALUES (:pid, :size, :sku, :price, :pos, :active)"
                    ),
                    {"pid": prod["product_id"], "size": size, "sku": sku, "price": prod["mrp_inr"],
                     "pos": _position(size), "active": True},
                )

        bind.execute(
            sa.text("UPDATE products SET sku = :style WHERE product_id = :pid"),
            {"style": style, "pid": prod["product_id"]},
        )
        for size, sku in sku_by_size.items():
            for table in ("cart", "order_items"):
                bind.execute(
                    sa.text(f"UPDATE {table} SET sku = :sku WHERE product_id = :pid AND UPPER(size) = :size"),
                    {"sku": sku, "pid": prod["product_id"], "size": size},
                )


def downgrade() -> None:
    # Product style codes and corrected line SKUs are kept: they are valid data
    # and the legacy single-SKU form cannot be reconstructed reliably.
    op.drop_table("product_variants")
