"""What the assistant is allowed to claim this turn: everything the backend returned.

Every tool result is added here. The grounding check then accepts a reply only if
each product, rupee amount, stock count and record id it states appears in this
evidence (or in the shopper's own words). Product cards are built from the stored
payloads, so the model never types a price.
"""

import re
import threading
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Set

# Record identifiers the platform issues (orders, shipments, returns, refunds, products).
RECORD_ID = re.compile(r"\b(?:ORD|SHP|RET|RFD|PRD|INV)-\d{3,6}\b", re.IGNORECASE)
_NUMERIC_TEXT = re.compile(r"^-?\d+(?:\.\d+)?$")
# Field names that hold money. Only these may back a rupee amount in a reply —
# a quantity of 1 must never "verify" a price of ₹1.
_MONEY_KEY = re.compile(r"(?:_inr|mrp|price|fee|total|amount|threshold|ceiling)", re.IGNORECASE)


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and _NUMERIC_TEXT.match(value.strip()):
        try:
            return float(Decimal(value.strip()))
        except InvalidOperation:
            return None
    return None


@dataclass
class Evidence:
    products: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # product_id -> full payload
    numbers: Set[float] = field(default_factory=set)  # every numeric value returned
    amounts: Set[float] = field(default_factory=set)  # numeric values of money fields only
    stock_counts: Set[int] = field(default_factory=set)
    identifiers: Set[str] = field(default_factory=set)
    requested_sizes: Set[str] = field(default_factory=set)  # sizes the turn searched for
    # Tools run in parallel threads and all write here.
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    # ------------------------------------------------------------------ intake

    def add_payload(self, payload: Any) -> None:
        """Walk any JSON payload: collect numbers and record ids."""
        with self._lock:
            self._walk(payload)

    def _walk(self, payload: Any) -> None:
        stack: List[tuple] = [("", payload)]
        while stack:
            key, item = stack.pop()
            if isinstance(item, dict):
                # Values of a money-named mapping (e.g. price_by_size) are money too.
                stack.extend((k if not _MONEY_KEY.search(key or "") else key, v) for k, v in item.items())
            elif isinstance(item, list):
                stack.extend((key, v) for v in item)
            else:
                number = _as_number(item)
                if number is not None:
                    self.numbers.add(round(number, 2))
                    if _MONEY_KEY.search(key or ""):
                        self.amounts.add(round(number, 2))
                elif isinstance(item, str):
                    self.identifiers.update(m.upper() for m in RECORD_ID.findall(item))

    def add_product(self, product: Dict[str, Any]) -> None:
        pid = str(product.get("product_id") or "").upper()
        if not pid:
            return
        with self._lock:
            self.products[pid] = product
            self.identifiers.add(pid)
            self._walk(product)
            self.stock_counts.add(int(product.get("stock") or 0))
            self.stock_counts.update(int(q) for q in (product.get("stock_by_size") or {}).values())

    def add_user_text(self, text: str) -> None:
        """The shopper's own numbers and ids may be repeated back ("under ₹5,000", "ORD-1001")."""
        for token in re.findall(r"\d[\d,]*(?:\.\d+)?", text or ""):
            number = _as_number(token.replace(",", ""))
            if number is not None:
                self.numbers.add(round(number, 2))
                self.amounts.add(round(number, 2))  # e.g. the shopper's own budget
        self.identifiers.update(m.upper() for m in RECORD_ID.findall(text or ""))

    # ------------------------------------------------------------------ derived facts

    def price_amounts(self, product_ids: Iterable[str]) -> Set[float]:
        """Lowest prices of listed products, plus pairwise sums ("together that's ₹X")."""
        lows = []
        for pid in product_ids:
            product = self.products.get(pid)
            if product:
                prices = [_as_number(v.get("mrp_inr")) for v in product.get("variants", []) if v.get("is_active", True)]
                prices = [p for p in prices if p is not None] or [_as_number(product.get("mrp_inr")) or 0.0]
                lows.append(min(prices))
        sums = {round(a + b, 2) for i, a in enumerate(lows) for b in lows[i + 1:]}
        return sums | {round(x, 2) for x in lows}

    def in_stock(self, product_id: str, sizes: Iterable[str] = ()) -> bool:
        """In stock at all — and, when sizes are known, in at least one of them that the product is made in."""
        product = self.products.get(product_id)
        if not product or int(product.get("stock") or 0) <= 0:
            return False
        by_size = product.get("stock_by_size") or {}
        offered = [s for s in sizes if s in by_size]
        return any(by_size[s] > 0 for s in offered) if offered else True
