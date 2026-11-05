from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CategoryDTO(BaseModel):
    category_id: str
    slug: str
    name: str
    parent_id: Optional[str] = None
    display_order: int = 0
    product_count: int = 0
    direct_product_count: int = 0


class ProductMaterialInput(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    family: Optional[str] = Field(default=None, max_length=24)
    percentage: Decimal = Field(gt=0, le=100)


class ProductVariantDTO(BaseModel):
    size: str
    sku: str
    mrp_inr: Decimal
    is_active: bool = True
    stock: int = 0  # sellable units of this size
    in_stock: bool = False


class PriceRangeDTO(BaseModel):
    min: Optional[Decimal]
    max: Optional[Decimal]


class ProductDTO(BaseModel):
    product_id: str
    sku: str  # style code; sellable SKUs are per variant
    name: str
    description: str
    category_id: str
    department: str
    mrp_inr: Decimal  # "from" price = lowest active variant price
    price_range: PriceRangeDTO
    variants: List[ProductVariantDTO]
    hsn_code: str
    color: str
    sizes_available: List[str]
    fit_guide: str
    fabric_and_care: str
    country_of_origin: str
    final_sale: bool
    security_tag_required: bool
    stock: int  # total sellable units across active sizes
    quantity_reserved: int
    stock_by_size: Dict[str, int]  # {size: sellable units}
    images: List[str]


class ProductCreateRequest(BaseModel):
    product_id: Optional[str] = None
    sku: str
    name: str
    description: str
    category_id: str
    department: str
    mrp_inr: Decimal = Field(gt=0)  # base price, used for any size not in variant_prices
    hsn_code: str = "6205"
    color: str
    color_family: Optional[str] = None
    color_hex: Optional[str] = None
    materials: Optional[List[ProductMaterialInput]] = None
    sizes_available: List[str] = Field(default_factory=lambda: ["S", "M", "L", "XL"])
    # Optional per-size prices, e.g. {"S": 2399, "M": 2499, "XL": 2699}. When given,
    # these sizes (and only these) are created; otherwise every sizes_available entry
    # is priced at mrp_inr.
    variant_prices: Optional[Dict[str, Decimal]] = None
    fit_guide: str = "Tailored regular fit."
    fabric_and_care: str = "Dry clean or cold gentle wash."
    final_sale: bool = False
    initial_stock: int = Field(default=20, ge=0)
    # Exact opening stock per size; when omitted, initial_stock is split evenly across sizes.
    initial_stock_by_size: Optional[Dict[str, int]] = None


class ProductUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None
    department: Optional[str] = None
    color: Optional[str] = None
    color_family: Optional[str] = None
    color_hex: Optional[str] = None
    materials: Optional[List[ProductMaterialInput]] = None
    mrp_inr: Optional[Decimal] = Field(default=None, gt=0)
    fit_guide: Optional[str] = None
    fabric_and_care: Optional[str] = None
    final_sale: Optional[bool] = None


class SynonymCreateRequest(BaseModel):
    term: str = Field(min_length=1, max_length=40)
    dimension: str = Field(min_length=3, max_length=16)
    value: str = Field(min_length=1, max_length=40)


class ColorCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    family: str = Field(min_length=1, max_length=24)
    hex_code: Optional[str] = Field(default=None, max_length=7)


class MaterialCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    family: str = Field(min_length=1, max_length=24)


class CategoryCreateRequest(BaseModel):
    category_id: Optional[str] = Field(default=None, max_length=16)
    slug: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    parent_id: Optional[str] = Field(default=None, max_length=16)
    display_order: int = 0


class DepartmentCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=16)
    name: str = Field(min_length=1, max_length=60)
    display_order: int = 0


class VariantUpdateRequest(BaseModel):
    """Reprice and/or retire one size. Giving mrp_inr for a new size adds it."""

    mrp_inr: Optional[Decimal] = Field(default=None, gt=0)
    is_active: Optional[bool] = None


class InventoryUpdateRequest(BaseModel):
    """Absolute available stock per size, e.g. {"sizes": {"M": 12, "L": 4}}."""

    sizes: Dict[str, int] = Field(min_length=1)
    reason: str = Field(default="manual_stock_count", min_length=3, max_length=160)


class InventoryRestockRequest(BaseModel):
    """Newly received units for one size."""

    product_id: str
    size: str = Field(min_length=1, max_length=16)
    quantity: int = Field(gt=0, le=10000)
    reason: str = Field(default="units_received", min_length=3, max_length=160)


class ProductReviewCreateRequest(BaseModel):
    rating: int = Field(default=5, ge=1, le=5)
    fit_feedback: str = "true_to_size"
    comment: str = Field(min_length=3, max_length=500)
