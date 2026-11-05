"""Style attributes for the conversational stylist: occasions and colour palettes.

Revision ID: 0005_stylist_style_attributes
Revises: 0004_rbac_and_auth_sessions
Create Date: 2026-11-05

Schema
------
occasions          vocabulary of what garments are worn for (everyday … black_tie)
product_occasions  product ↔ occasion (many-to-many)
palettes           colour moods shoppers describe ("calm", "earthy", "bold")
color_palettes     colour ↔ palette (many-to-many)
search_synonyms    CHECK widened to the new dimensions 'occasion' and 'palette'

Data
----
* Vocabulary rows (occasions, palettes, their synonyms) and the least-privilege
  `svc-stylist` agent permission come from backend.app.reference_data
  (insert-missing only, never overwrites).
* Product→occasion and colour→palette ASSIGNMENTS are deliberately NOT inserted
  here: they are curated data reviewed in backend/data/style_tags_draft.json and
  applied with backend/scripts/apply_style_tags.py once approved. Until then the
  search engine ignores these two dimensions rather than returning nothing.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision: str = "0005_stylist_style_attributes"
down_revision: Union[str, None] = "0004_rbac_and_auth_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_DIMENSIONS = "dimension IN ('department', 'product_type', 'color', 'material')"
_NEW_DIMENSIONS = "dimension IN ('department', 'product_type', 'color', 'material', 'occasion', 'palette')"


def _ts():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    # Fresh databases already have these tables from 0001's create_all.
    if "occasions" not in sa.inspect(bind).get_table_names():
        _create_tables()

    op.drop_constraint("ck_search_synonyms_dimension", "search_synonyms", type_="check")
    op.create_check_constraint("ck_search_synonyms_dimension", "search_synonyms", _NEW_DIMENSIONS)

    from backend.app.reference_data import ensure_reference_data  # single definition of the vocabulary

    session = Session(bind=bind)
    ensure_reference_data(session, tables=("occasions", "palettes", "search_synonyms", "agent_permissions"))
    session.flush()


def _create_tables() -> None:
    op.create_table(
        "occasions",
        sa.Column("code", sa.String(24), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts(),
        sa.CheckConstraint("code = LOWER(code)", name="ck_occasions_code_lower"),
    )
    op.create_table(
        "product_occasions",
        sa.Column("product_id", sa.String(16), sa.ForeignKey("products.product_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("occasion_code", sa.String(24), sa.ForeignKey("occasions.code", ondelete="RESTRICT"), primary_key=True),
        *_ts(),
    )
    op.create_index("ix_product_occasions_occasion_code", "product_occasions", ["occasion_code"])
    op.create_table(
        "palettes",
        sa.Column("code", sa.String(24), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        *_ts(),
        sa.CheckConstraint("code = LOWER(code)", name="ck_palettes_code_lower"),
    )
    op.create_table(
        "color_palettes",
        sa.Column("color_id", sa.Integer(), sa.ForeignKey("colors.color_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("palette_code", sa.String(24), sa.ForeignKey("palettes.code", ondelete="RESTRICT"), primary_key=True),
        *_ts(),
    )
    op.create_index("ix_color_palettes_palette_code", "color_palettes", ["palette_code"])


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM search_synonyms WHERE dimension IN ('occasion', 'palette')"))
    bind.execute(sa.text("DELETE FROM agent_permissions WHERE service_account = 'svc-stylist'"))
    op.drop_constraint("ck_search_synonyms_dimension", "search_synonyms", type_="check")
    op.create_check_constraint("ck_search_synonyms_dimension", "search_synonyms", _OLD_DIMENSIONS)
    op.drop_index("ix_color_palettes_palette_code", table_name="color_palettes")
    op.drop_table("color_palettes")
    op.drop_table("palettes")
    op.drop_index("ix_product_occasions_occasion_code", table_name="product_occasions")
    op.drop_table("product_occasions")
    op.drop_table("occasions")
