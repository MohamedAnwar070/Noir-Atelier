"""Typed data passed between the stylist's pipeline steps.

    message ─► Route ─► ProfileUpdate ─► StyleProfile ─► Plan ─► WorkerResults ─► Draft ─► Verdict

Product facts (names, prices, stock) exist ONLY in WorkerResults, which are built
exclusively from tool responses. The writer and critic read facts from here and
nowhere else — that is what keeps every reply grounded.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.stylist_schema import AvoidList, StyleProfile


class Route(str, Enum):
    """Where a message goes. Only DISCOVERY is handled by the stylist itself."""

    DISCOVERY = "discovery"
    CART = "cart"
    ORDER_STATUS = "order_status"
    RETURNS = "returns"
    SUPPORT = "support"  # complaints and anything needing a person


class PlanAction(str, Enum):
    ASK = "ask"  # not enough to search on: ask ONE question
    SEARCH = "search"  # first look for this need
    REFINE = "refine"  # the shopper reacted to products already shown


@dataclass(frozen=True)
class Plan:
    action: PlanAction
    reason: str
    question: Optional[str] = None
    # True when the shopper asked for alternatives ("something else") — hide last turn's picks.
    exclude_previous: bool = False


class ProfileUpdate(BaseModel):
    """What this turn changes. ``None`` = unchanged; lists replace; avoid_* lists add."""

    model_config = ConfigDict(extra="forbid")

    reset: bool = False
    occasion: Optional[str] = None
    department: Optional[str] = None
    product_types: Optional[List[str]] = None
    colors: Optional[List[str]] = None
    palettes: Optional[List[str]] = None
    materials: Optional[List[str]] = None
    sizes: Optional[List[str]] = None
    budget_min_inr: Optional[float] = Field(default=None, ge=0)
    budget_max_inr: Optional[float] = Field(default=None, gt=0)
    recipient: Optional[str] = None
    location: Optional[str] = None
    timing: Optional[str] = None
    avoid: AvoidList = Field(default_factory=AvoidList)
    confidence: Dict[str, float] = Field(default_factory=dict)

    def is_noop(self) -> bool:
        return self == ProfileUpdate()


@dataclass(frozen=True)
class ProductFact:
    """Everything the stylist may say about one product — copied from a tool result."""

    product_id: str
    name: str
    department: str
    category: str
    color: str
    materials: List[str]
    price_min: float
    price_max: float
    stock: int
    sizes: List[str]
    gst_rate_pct: int

    @property
    def in_stock(self) -> bool:
        return self.stock > 0


@dataclass
class WorkerResults:
    products: List[ProductFact] = field(default_factory=list)
    pairings: List[ProductFact] = field(default_factory=list)
    total_matches: int = 0
    relaxed: bool = False  # search had to drop constraints to find anything
    errors: List[str] = field(default_factory=list)
    # Full API payloads keyed by product_id — for rendering product cards ONLY.
    # The writer and critic read ProductFact, never these.
    display_items: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def by_id(self) -> Dict[str, ProductFact]:
        return {p.product_id: p for p in [*self.products, *self.pairings]}


@dataclass(frozen=True)
class Draft:
    reply: str
    product_ids: List[str]
    source: str  # "llm" | "template"


@dataclass(frozen=True)
class Verdict:
    passed: bool
    problems: List[str] = field(default_factory=list)


__all__ = [
    "Route",
    "PlanAction",
    "Plan",
    "ProfileUpdate",
    "ProductFact",
    "WorkerResults",
    "Draft",
    "Verdict",
    "StyleProfile",
    "AvoidList",
]
