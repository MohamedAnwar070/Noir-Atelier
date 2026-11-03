from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CategoryDTO(BaseModel):
    category_id: str
    name: str
    department: str
    product_count: int = 0


class ProductVariantDTO(BaseModel):
    size: str
    sku: str
    mrp_inr: Decimal
    is_active: bool = True


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
    stock: int
    size_breakdown: Dict[str, int]
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
    sizes_available: List[str] = Field(default_factory=lambda: ["S", "M", "L", "XL"])
    # Optional per-size prices, e.g. {"S": 2399, "M": 2499, "XL": 2699}. When given,
    # these sizes (and only these) are created; otherwise every sizes_available entry
    # is priced at mrp_inr.
    variant_prices: Optional[Dict[str, Decimal]] = None
    fit_guide: str = "Tailored regular fit."
    fabric_and_care: str = "Dry clean or cold gentle wash."
    final_sale: bool = False
    initial_stock: int = Field(default=20, ge=0)


class ProductUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    mrp_inr: Optional[Decimal] = Field(default=None, gt=0)
    fit_guide: Optional[str] = None
    fabric_and_care: Optional[str] = None
    final_sale: Optional[bool] = None


class VariantUpdateRequest(BaseModel):
    """Reprice and/or retire one size. Giving mrp_inr for a new size adds it."""

    mrp_inr: Optional[Decimal] = Field(default=None, gt=0)
    is_active: Optional[bool] = None


class InventoryUpdateRequest(BaseModel):
    quantity_available: int = Field(ge=0)
    size_breakdown: Optional[Dict[str, int]] = None
    reason: str = "manual_inventory_sync"


class InventoryReserveRequest(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)
    order_id: Optional[str] = None


class ProductReviewCreateRequest(BaseModel):
    rating: int = Field(default=5, ge=1, le=5)
    fit_feedback: str = "true_to_size"
    comment: str = Field(min_length=3, max_length=500)
