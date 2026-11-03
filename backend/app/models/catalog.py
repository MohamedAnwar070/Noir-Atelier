"""Catalogue attributes and search vocabulary.

Everything a shopper (or the AI concierge) can search or filter by is data in
these tables, not code: adding a department, colour, material or synonym is an
INSERT (or an admin API call), never a code change.

    departments ─┐
    categories ──┼── products ── product_materials ── materials
    colors ──────┘
    search_synonyms  (term → one dimension/value, e.g. "tee" → product_type:t-shirt)
"""

from decimal import Decimal
from typing import List, Optional

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import TimestampMixin

# Dimensions a synonym can resolve to. Kept in sync with the CHECK constraint below.
SYNONYM_DIMENSIONS = ("department", "product_type", "color", "material")


class Department(Base, TimestampMixin):
    """Shopping department (MEN / WOMEN / KIDS …)."""

    __tablename__ = "departments"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (CheckConstraint("code = UPPER(code)", name="ck_departments_code_upper"),)


class Color(Base, TimestampMixin):
    """A named colourway. `family` is what shoppers search for ("black" finds Obsidian)."""

    __tablename__ = "colors"

    color_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    family: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    hex_code: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)

    __table_args__ = (
        CheckConstraint("family = LOWER(family)", name="ck_colors_family_lower"),
        CheckConstraint("hex_code IS NULL OR hex_code LIKE '#%'", name="ck_colors_hex_format"),
    )


class Material(Base, TimestampMixin):
    """A fibre. `family` groups variants of a fibre (Merino Wool → wool)."""

    __tablename__ = "materials"

    material_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    family: Mapped[str] = mapped_column(String(24), nullable=False, index=True)

    __table_args__ = (CheckConstraint("family = LOWER(family)", name="ck_materials_family_lower"),)


class ProductMaterial(Base, TimestampMixin):
    """Fabric composition: one row per fibre in a product (e.g. 80% merino, 20% polyamide)."""

    __tablename__ = "product_materials"

    product_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("products.product_id", ondelete="CASCADE"), primary_key=True
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.material_id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    material: Mapped["Material"] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("percentage > 0 AND percentage <= 100", name="ck_product_materials_pct_range"),
    )


class SearchSynonym(Base, TimestampMixin):
    """Maps a shopper's word to exactly one searchable value.

    `value` is interpreted per dimension: a department code, a category slug,
    a colour family or a material family. Admin-managed; validated on write so
    a synonym can never point at something that does not exist.
    """

    __tablename__ = "search_synonyms"

    synonym_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    term: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    dimension: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("term = LOWER(term)", name="ck_search_synonyms_term_lower"),
        CheckConstraint(
            "dimension IN ('department', 'product_type', 'color', 'material')",
            name="ck_search_synonyms_dimension",
        ),
    )


__all__ = [
    "SYNONYM_DIMENSIONS",
    "Department",
    "Color",
    "Material",
    "ProductMaterial",
    "SearchSynonym",
]
