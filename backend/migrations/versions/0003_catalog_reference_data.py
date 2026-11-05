"""Data-driven catalogue, search vocabulary and status reference tables.

Revision ID: 0003_catalog_reference_data
Revises: 0002_product_variants
Create Date: 2026-11-03

Schema
------
New tables: departments, colors, materials, product_materials, search_synonyms,
            order_statuses, refund_statuses, return_reasons.
categories  : becomes a product-type taxonomy (adds slug, display_order;
              drops the redundant `department` column).
products    : department → FK departments.code; free-text `color` replaced by
              color_id → colors.
orders.status, refunds.status, returns.reason_category → FKs to their vocabularies.
Indexes added on 7 previously unindexed foreign keys.

Data
----
Reference rows come from backend.app.reference_data (insert-missing only, never
overwrites). Existing products are mapped onto the new taxonomy/colours/
materials using the frozen tables below; any product not listed is placed in an
"Uncategorised" category and keeps its colour name with a derived family, so
the migration never fails on unknown data.

Order of operations follows add-nullable → backfill → constrain → drop.
"""
import json
from typing import Dict, List, Sequence, Tuple, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision: str = "0003_catalog_reference_data"
down_revision: Union[str, None] = "0002_product_variants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen mapping of the products that existed when this migration was written.
_PRODUCT_CATEGORY: Dict[str, str] = {
    "PRD-001": "CAT-11",  # Tailored Belgian Linen Shirt   → Shirts
    "PRD-002": "CAT-21",  # Structured Merino-Wool Overshirt → Overshirts
    "PRD-003": "CAT-40",  # Silk-Crepe Draped Midi Dress    → Dresses
    "PRD-004": "CAT-12",  # Minimalist Pima Cotton Tee      → T-Shirts
    "PRD-005": "CAT-30",  # Kids Organic Merino Crewneck    → Knitwear
}
_PRODUCT_MATERIALS: Dict[str, List[Tuple[str, int]]] = {
    "PRD-001": [("Belgian Linen", 100)],
    "PRD-002": [("Merino Wool", 80), ("Recycled Polyamide", 20)],
    "PRD-003": [("Mulberry Silk", 100)],
    "PRD-004": [("Pima Cotton", 100)],
    "PRD-005": [("Merino Wool", 100)],
}
_LEGACY_CATEGORIES = ("CAT-MEN", "CAT-WMN", "CAT-KID")

# Reference data this revision owns. Frozen: later revisions add their own tables
# and synonym dimensions, which do not exist yet when this migration runs.
_REFERENCE_TABLES = (
    "departments", "categories", "colors", "materials", "search_synonyms",
    "order_statuses", "refund_statuses", "return_reasons",
)
_SYNONYM_DIMENSIONS = ("department", "product_type", "color", "material")
_FALLBACK_CATEGORY = ("CAT-99", "uncategorised", "Uncategorised")

# FK indexes the original schema was missing (table, column).
_FK_INDEXES = [
    ("categories", "parent_id"),
    ("cart", "product_id"),
    ("orders", "shipping_address_id"),
    ("product_reviews", "customer_id"),
    ("recommendations", "recommended_product_id"),
    ("coupon_usage", "coupon_id"),
    ("order_items", "product_id"),
]


def _ts() -> List[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def _create_tables() -> None:
    op.create_table(
        "departments",
        sa.Column("code", sa.String(16), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts(),
        sa.CheckConstraint("code = UPPER(code)", name="ck_departments_code_upper"),
    )
    op.create_table(
        "colors",
        sa.Column("color_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(40), nullable=False, unique=True),
        sa.Column("family", sa.String(24), nullable=False),
        sa.Column("hex_code", sa.String(7), nullable=True),
        *_ts(),
        sa.CheckConstraint("family = LOWER(family)", name="ck_colors_family_lower"),
        sa.CheckConstraint("hex_code IS NULL OR hex_code LIKE '#%'", name="ck_colors_hex_format"),
    )
    op.create_index("ix_colors_family", "colors", ["family"])
    op.create_table(
        "materials",
        sa.Column("material_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(60), nullable=False, unique=True),
        sa.Column("family", sa.String(24), nullable=False),
        *_ts(),
        sa.CheckConstraint("family = LOWER(family)", name="ck_materials_family_lower"),
    )
    op.create_index("ix_materials_family", "materials", ["family"])
    op.create_table(
        "product_materials",
        sa.Column("product_id", sa.String(16), sa.ForeignKey("products.product_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("material_id", sa.Integer(), sa.ForeignKey("materials.material_id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("percentage", sa.Numeric(5, 2), nullable=False),
        *_ts(),
        sa.CheckConstraint("percentage > 0 AND percentage <= 100", name="ck_product_materials_pct_range"),
    )
    op.create_index("ix_product_materials_material_id", "product_materials", ["material_id"])
    op.create_table(
        "search_synonyms",
        sa.Column("synonym_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("term", sa.String(40), nullable=False, unique=True),
        sa.Column("dimension", sa.String(16), nullable=False),
        sa.Column("value", sa.String(40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts(),
        sa.CheckConstraint("term = LOWER(term)", name="ck_search_synonyms_term_lower"),
        sa.CheckConstraint(
            "dimension IN ('department', 'product_type', 'color', 'material')", name="ck_search_synonyms_dimension"
        ),
    )
    tone = "tone IN ('neutral', 'info', 'success', 'warning', 'error')"
    op.create_table(
        "order_statuses",
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("label", sa.String(60), nullable=False),
        sa.Column("tone", sa.String(16), nullable=False, server_default="neutral"),
        sa.Column("is_cancellable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_returnable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        *_ts(),
        sa.CheckConstraint(tone, name="ck_order_statuses_tone"),
    )
    op.create_table(
        "refund_statuses",
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("label", sa.String(60), nullable=False),
        sa.Column("tone", sa.String(16), nullable=False, server_default="neutral"),
        sa.Column("awaiting_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        *_ts(),
        sa.CheckConstraint(tone, name="ck_refund_statuses_tone"),
    )
    op.create_table(
        "return_reasons",
        sa.Column("code", sa.String(40), primary_key=True),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("is_defect_claim", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts(),
    )


def _sync_catalog_agent_permissions(bind: sa.Connection, *, include_catalog_api: bool) -> None:
    rows = bind.execute(
        sa.text("SELECT perm_id, allowed_endpoints FROM agent_permissions WHERE service_account = 'svc-catalog'")
    ).mappings().all()
    table = sa.table(
        "agent_permissions",
        sa.column("perm_id", sa.Integer()),
        sa.column("allowed_endpoints", sa.JSON()),
    )
    for row in rows:
        raw = row["allowed_endpoints"]
        endpoints: List[str] = json.loads(raw) if isinstance(raw, str) else list(raw or [])
        if include_catalog_api:
            for ep in ("/api/catalog/meta", "/api/catalog/search"):
                if ep not in endpoints:
                    endpoints.append(ep)
        else:
            endpoints = [ep for ep in endpoints if ep not in ("/api/catalog/meta", "/api/catalog/search")]
        bind.execute(
            table.update().where(table.c.perm_id == row["perm_id"]).values(allowed_endpoints=endpoints)
        )


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())

    # Fresh databases run Base.metadata.create_all in 0001, so the 0003 schema
    # is already in place; only seed missing reference rows and agent endpoints.
    if "departments" in existing_tables:
        from backend.app.reference_data import ensure_reference_data

        session = Session(bind=bind)
        ensure_reference_data(session, tables=_REFERENCE_TABLES, synonym_dimensions=_SYNONYM_DIMENSIONS)
        session.flush()
        _sync_catalog_agent_permissions(bind, include_catalog_api=True)
        return

    # 1. Relax/extend existing tables so new reference rows can be written.
    op.alter_column("categories", "department", existing_type=sa.String(16), nullable=True)
    op.add_column("categories", sa.Column("slug", sa.String(40), nullable=True))
    op.add_column("categories", sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("products", sa.Column("color_id", sa.Integer(), nullable=True))

    # 2. New tables + reference data.
    _create_tables()
    from backend.app.reference_data import ensure_reference_data  # single definition of the vocabulary

    session = Session(bind=bind)
    ensure_reference_data(session, tables=_REFERENCE_TABLES, synonym_dimensions=_SYNONYM_DIMENSIONS)
    session.flush()

    # 3. Backfill products.
    products = bind.execute(sa.text("SELECT product_id, color FROM products")).mappings().all()
    known_colors = {r[0] for r in bind.execute(sa.text("SELECT name FROM colors"))}
    for color in {p["color"] for p in products} - known_colors:
        bind.execute(
            sa.text("INSERT INTO colors (name, family) VALUES (:n, :f)"),
            {"n": color, "f": color.strip().split()[-1].lower()},
        )
    bind.execute(sa.text("UPDATE products p SET color_id = c.color_id FROM colors c WHERE c.name = p.color"))

    if any(p["product_id"] not in _PRODUCT_CATEGORY for p in products):
        cid, slug, name = _FALLBACK_CATEGORY
        bind.execute(
            sa.text("INSERT INTO categories (category_id, slug, name, display_order, is_active) "
                    "VALUES (:c, :s, :n, 99, true) ON CONFLICT (category_id) DO NOTHING"),
            {"c": cid, "s": slug, "n": name},
        )
    for p in products:
        bind.execute(
            sa.text("UPDATE products SET category_id = :c WHERE product_id = :p"),
            {"c": _PRODUCT_CATEGORY.get(p["product_id"], _FALLBACK_CATEGORY[0]), "p": p["product_id"]},
        )

    material_ids = {r[0]: r[1] for r in bind.execute(sa.text("SELECT name, material_id FROM materials"))}
    existing_pids = {p["product_id"] for p in products}
    for pid, parts in _PRODUCT_MATERIALS.items():
        if pid not in existing_pids:
            continue
        for material, pct in parts:
            bind.execute(
                sa.text("INSERT INTO product_materials (product_id, material_id, percentage) "
                        "VALUES (:p, :m, :pct) ON CONFLICT DO NOTHING"),
                {"p": pid, "m": material_ids[material], "pct": pct},
            )

    # Legacy department-as-category rows are now unreferenced.
    bind.execute(
        sa.text("DELETE FROM categories WHERE category_id IN :ids").bindparams(sa.bindparam("ids", expanding=True)),
        {"ids": list(_LEGACY_CATEGORIES)},
    )

    # 4. Constrain.
    op.alter_column("categories", "slug", existing_type=sa.String(40), nullable=False)
    op.create_unique_constraint("categories_slug_key", "categories", ["slug"])
    op.create_check_constraint("ck_categories_slug_lower", "categories", "slug = LOWER(slug)")

    op.alter_column("products", "color_id", existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key("products_color_id_fkey", "products", "colors", ["color_id"], ["color_id"], ondelete="RESTRICT")
    op.create_index("ix_products_color_id", "products", ["color_id"])
    op.create_foreign_key("products_department_fkey", "products", "departments", ["department"], ["code"], ondelete="RESTRICT")
    op.create_index("ix_products_department", "products", ["department"])

    # Normalize any unmapped statuses/reasons before adding foreign keys.
    bind.execute(
        sa.text("UPDATE orders SET status = 'pending' WHERE status NOT IN (SELECT code FROM order_statuses)")
    )
    bind.execute(
        sa.text("UPDATE refunds SET status = 'pending_approval' WHERE status NOT IN (SELECT code FROM refund_statuses)")
    )
    op.create_foreign_key("orders_status_fkey", "orders", "order_statuses", ["status"], ["code"], ondelete="RESTRICT")
    op.create_foreign_key("refunds_status_fkey", "refunds", "refund_statuses", ["status"], ["code"], ondelete="RESTRICT")
    # Map legacy free-text reasons onto the vocabulary before constraining.
    bind.execute(
        sa.text("UPDATE returns SET reason_category = 'size_mismatch' "
                "WHERE reason_category NOT IN (SELECT code FROM return_reasons)")
    )
    op.create_foreign_key(
        "returns_reason_category_fkey", "returns", "return_reasons", ["reason_category"], ["code"], ondelete="RESTRICT"
    )
    op.create_index("ix_returns_reason_category", "returns", ["reason_category"])

    for table, column in _FK_INDEXES:
        op.create_index(f"ix_{table}_{column}", table, [column])

    # 5. Drop what is now redundant (3NF): department lives on products, colour in colors.
    op.drop_index("ix_categories_department", table_name="categories")
    op.drop_column("categories", "department")
    op.drop_column("products", "color")

    _sync_catalog_agent_permissions(bind, include_catalog_api=True)


def downgrade() -> None:
    bind = op.get_bind()
    _sync_catalog_agent_permissions(bind, include_catalog_api=False)

    for table, column in _FK_INDEXES:
        op.drop_index(f"ix_{table}_{column}", table_name=table)
    op.drop_index("ix_returns_reason_category", table_name="returns")
    op.drop_constraint("returns_reason_category_fkey", "returns", type_="foreignkey")
    op.drop_constraint("refunds_status_fkey", "refunds", type_="foreignkey")
    op.drop_constraint("orders_status_fkey", "orders", type_="foreignkey")

    # Restore free-text colour.
    op.add_column("products", sa.Column("color", sa.String(40), nullable=True))
    bind.execute(sa.text("UPDATE products p SET color = c.name FROM colors c WHERE c.color_id = p.color_id"))
    op.alter_column("products", "color", existing_type=sa.String(40), nullable=False)
    op.drop_index("ix_products_department", table_name="products")
    op.drop_constraint("products_department_fkey", "products", type_="foreignkey")
    op.drop_index("ix_products_color_id", table_name="products")
    op.drop_constraint("products_color_id_fkey", "products", type_="foreignkey")
    op.drop_column("products", "color_id")

    # Restore department-as-category.
    op.add_column("categories", sa.Column("department", sa.String(16), nullable=True))
    for cid, dept, name in (("CAT-MEN", "MEN", "Men's Atelier Garments"),
                            ("CAT-WMN", "WOMEN", "Women's Atelier Garments"),
                            ("CAT-KID", "KIDS", "Kids' Atelier Garments")):
        bind.execute(
            sa.text("INSERT INTO categories (category_id, slug, name, department, is_active, display_order) "
                    "VALUES (:c, :s, :n, :d, true, 0) ON CONFLICT (category_id) DO NOTHING"),
            {"c": cid, "s": cid.lower(), "n": name, "d": dept},
        )
        bind.execute(sa.text("UPDATE products SET category_id = :c WHERE department = :d"), {"c": cid, "d": dept})
    bind.execute(
        sa.text("DELETE FROM categories WHERE category_id NOT IN :ids").bindparams(sa.bindparam("ids", expanding=True)),
        {"ids": list(_LEGACY_CATEGORIES)},
    )
    op.alter_column("categories", "department", existing_type=sa.String(16), nullable=False)
    op.create_index("ix_categories_department", "categories", ["department"])
    op.drop_constraint("ck_categories_slug_lower", "categories", type_="check")
    op.drop_constraint("categories_slug_key", "categories", type_="unique")
    op.drop_column("categories", "display_order")
    op.drop_column("categories", "slug")

    for table in ("return_reasons", "refund_statuses", "order_statuses", "search_synonyms",
                  "product_materials", "materials", "colors", "departments"):
        op.drop_table(table)
