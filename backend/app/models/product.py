from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import SoftDeleteMixin, TimestampMixin, utc_now

if TYPE_CHECKING:  # resolved at runtime via the SQLAlchemy registry
    from .catalog import Color, ProductMaterial, ProductOccasion


class Category(Base, TimestampMixin, SoftDeleteMixin):
    """Product-type taxonomy (Tops › T-Shirts, Outerwear › Overshirts, …).

    Department is NOT a category: a product type spans departments, so the
    department lives on the product (FK to departments).
    """

    __tablename__ = "categories"

    category_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    # Stable, URL/search-safe key (e.g. "t-shirt"); synonyms point at slugs.
    slug: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(16), ForeignKey("categories.category_id", ondelete="SET NULL"), nullable=True, index=True
    )
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    icon_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    products: Mapped[List["Product"]] = relationship(back_populates="category")
    parent: Mapped[Optional["Category"]] = relationship(remote_side="Category.category_id")

    __table_args__ = (CheckConstraint("slug = LOWER(slug)", name="ck_categories_slug_lower"),)


class Product(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    # Style code shared by every size (e.g. "PRD-002-CHR"); each size has its own
    # sellable SKU on ProductVariant.
    sku: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("categories.category_id", ondelete="RESTRICT"), nullable=False
    )
    department: Mapped[str] = mapped_column(
        String(16), ForeignKey("departments.code", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Derived "from" price = lowest active variant price. Kept on the product for
    # catalog listing, sorting and price filters; maintained by variant_service,
    # never charged directly (checkout always prices the variant).
    mrp_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    original_mrp_inr: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    hsn_code: Mapped[str] = mapped_column(String(12), default="6205", nullable=False)
    color_id: Mapped[int] = mapped_column(
        ForeignKey("colors.color_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Derived from active variants (in display order); maintained by variant_service.
    sizes_available: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    fit_guide: Mapped[str] = mapped_column(Text, nullable=False)
    fabric_and_care: Mapped[str] = mapped_column(Text, nullable=False)
    country_of_origin: Mapped[str] = mapped_column(String(64), default="India", nullable=False)
    final_sale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    security_tag_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    category: Mapped["Category"] = relationship(back_populates="products")
    color: Mapped["Color"] = relationship(lazy="selectin")
    materials: Mapped[List["ProductMaterial"]] = relationship(
        cascade="all, delete-orphan",
        order_by="ProductMaterial.percentage.desc()",
    )
    occasions: Mapped[List["ProductOccasion"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    images: Mapped[List["ProductImage"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    variants: Mapped[List["ProductVariant"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductVariant.position",
    )

    __table_args__ = (
        Index("ix_products_category_active_price", "category_id", "is_active", "mrp_inr"),
        CheckConstraint("mrp_inr > 0", name="ck_products_mrp_positive"),
    )


class ProductVariant(Base, TimestampMixin):
    """A sellable size of a product: owns its SKU and its price.

    Price lives here (not on Product) because sizes can be priced differently —
    and because GST slabs are resolved per unit price, a size can even fall in a
    different tax slab than its siblings.
    """

    __tablename__ = "product_variants"

    variant_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True
    )
    size: Mapped[str] = mapped_column(String(16), nullable=False)
    sku: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    mrp_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="variants")
    # Stock for this size (one row). Loaded with the variant; locked separately by
    # inventory_service (never via a join, so FOR UPDATE stays outer-join free).
    stock: Mapped[Optional["VariantInventory"]] = relationship(
        back_populates="variant", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("product_id", "size", name="uq_product_variants_product_size"),
        CheckConstraint("mrp_inr > 0", name="ck_product_variants_mrp_positive"),
    )


class ProductImage(Base, TimestampMixin):
    __tablename__ = "product_images"

    image_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(255), nullable=False)
    alt_text: Mapped[str] = mapped_column(String(160), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="images")


# Every way stock can change. The ledger CHECK constraint is generated from this tuple.
MOVEMENT_TYPES = (
    "opening_balance",  # first stock of a size (seed, product creation, migration backfill)
    "sale",             # direct order: available -> sold
    "hold",             # checkout hold: available -> reserved
    "hold_release",     # hold expired / cancelled / payment flagged: reserved -> available
    "hold_capture",     # held order paid: reserved -> sold
    "late_capture",     # payment arrived after the hold expired: available -> sold
    "cancel_restock",   # paid order cancelled: sold -> available
    "return_restock",   # refunded return: sold -> available
    "restock",          # new units received
    "adjustment",       # admin / inventory agent sets an absolute level
    "damage",           # available -> damaged
)


class VariantInventory(Base, TimestampMixin):
    """Stock of ONE size (variant) — the only source of truth for stock.

    available = sellable now. Units held by a pending checkout move to reserved
    (they are no longer available) and leave on payment capture or go back on
    release. Only backend.app.services.inventory_service writes these rows, and
    every write appends an InventoryMovement in the same transaction.
    """

    __tablename__ = "variant_inventory"

    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.variant_id", ondelete="CASCADE"), primary_key=True
    )
    quantity_available: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    quantity_reserved: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    quantity_damaged: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=2, server_default="2", nullable=False)

    variant: Mapped["ProductVariant"] = relationship(back_populates="stock", lazy="raise_on_sql")

    __table_args__ = (
        CheckConstraint("quantity_available >= 0", name="ck_variant_inventory_available_non_negative"),
        CheckConstraint("quantity_reserved >= 0", name="ck_variant_inventory_reserved_non_negative"),
        CheckConstraint("quantity_damaged >= 0", name="ck_variant_inventory_damaged_non_negative"),
        CheckConstraint("low_stock_threshold >= 0", name="ck_variant_inventory_threshold_non_negative"),
    )


class InventoryMovement(Base):
    """Append-only stock ledger: one row per size per change. Never updated or deleted.

    Invariant: per variant, the sum of the deltas equals its current quantities
    (scripts/check_inventory_invariants.py).
    """

    __tablename__ = "inventory_movements"

    movement_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.variant_id", ondelete="CASCADE"), nullable=False
    )
    movement_type: Mapped[str] = mapped_column(String(24), nullable=False)
    delta_available: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    delta_reserved: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    delta_damaged: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    reference_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    reference_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "movement_type IN (" + ", ".join(f"'{t}'" for t in MOVEMENT_TYPES) + ")",
            name="ck_inventory_movements_type",
        ),
        CheckConstraint(
            "delta_available <> 0 OR delta_reserved <> 0 OR delta_damaged <> 0",
            name="ck_inventory_movements_non_zero",
        ),
        Index("ix_inventory_movements_variant_created", "variant_id", "created_at"),
        Index("ix_inventory_movements_reference", "reference_type", "reference_id"),
    )


class ProductVector(Base, TimestampMixin):
    __tablename__ = "product_vectors"

    vector_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("products.product_id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    qdrant_point_id: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(80), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, default=384, nullable=False)
    style_tags: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)


class ProductReview(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "product_reviews"

    review_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False, index=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    fit_feedback: Mapped[str] = mapped_column(String(32), default="true_to_size", nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verified_purchase: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (CheckConstraint("rating >= 1 AND rating <= 5", name="ck_product_reviews_rating"),)


class Recommendation(Base, TimestampMixin):
    __tablename__ = "recommendations"

    rec_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_product_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True
    )
    recommended_product_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(32), default="complete_the_look", nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.9000"), nullable=False)
