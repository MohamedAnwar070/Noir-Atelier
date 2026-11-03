from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CategoryDTO(BaseModel):
    category_id: str
    name: str
    department: str
    product_count: int = 0


class ProductDTO(BaseModel):
    product_id: str
    sku: str
    name: str
    description: str
    category_id: str
    department: str
    mrp_inr: Decimal
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
    mrp_inr: Decimal = Field(gt=0)
    hsn_code: str = "6205"
    color: str
    sizes_available: List[str] = Field(default_factory=lambda: ["S", "M", "L", "XL"])
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


class InventoryUpdateRequest(BaseModel):
    quantity_available: int = Field(ge=0)
    size_breakdown: Optional[Dict[str, int]] = None
    reason: str = "manual_inventory_sync"


class InventoryReserveRequest(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)
    order_id: Optional[str] = None
