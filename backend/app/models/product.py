from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import SoftDeleteMixin, TimestampMixin


class Category(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "categories"

    category_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    department: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(16), ForeignKey("categories.category_id", ondelete="SET NULL"), nullable=True
    )
    icon_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    products: Mapped[List["Product"]] = relationship(back_populates="category")


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
    department: Mapped[str] = mapped_column(String(16), nullable=False)
    # Derived "from" price = lowest active variant price. Kept on the product for
    # catalog listing, sorting and price filters; maintained by variant_service,
    # never charged directly (checkout always prices the variant).
    mrp_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    original_mrp_inr: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    hsn_code: Mapped[str] = mapped_column(String(12), default="6205", nullable=False)
    color: Mapped[str] = mapped_column(String(40), nullable=False)
    # Derived from active variants (in display order); maintained by variant_service.
    sizes_available: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    fit_guide: Mapped[str] = mapped_column(Text, nullable=False)
    fabric_and_care: Mapped[str] = mapped_column(Text, nullable=False)
    country_of_origin: Mapped[str] = mapped_column(String(64), default="India", nullable=False)
    final_sale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    security_tag_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    category: Mapped["Category"] = relationship(back_populates="products")
    images: Mapped[List["ProductImage"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    inventory: Mapped[Optional["Inventory"]] = relationship(
        back_populates="product", uselist=False, cascade="all, delete-orphan"
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


class Inventory(Base, TimestampMixin):
    __tablename__ = "inventory"

    inventory_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("products.product_id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    quantity_available: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quantity_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quantity_damaged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    size_breakdown: Mapped[Dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="inventory")

    __table_args__ = (
        CheckConstraint("quantity_available >= 0", name="ck_inventory_avail_non_negative"),
        CheckConstraint("quantity_reserved >= 0", name="ck_inventory_reserved_non_negative"),
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
        String(16), ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False
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
        String(16), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(32), default="complete_the_look", nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.9000"), nullable=False)
