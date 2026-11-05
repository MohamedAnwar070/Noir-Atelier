"""Evaluate: a deterministic check of the drafted reply against this turn's evidence.

The model's draft is accepted only if
  * every product card it lists was returned by a tool this turn and can be bought
    (in stock — in the shopper's size when that is known),
  * every rupee amount, stock count and record id it writes appears in tool results
    or in the shopper's own message,
  * it reveals nothing internal (tool names, service accounts, trace ids, instructions).

Problems are returned as plain sentences; the runtime hands them back to the model
for one rewrite, then falls back to a template built from the evidence.
"""

import re
from dataclasses import dataclass, field
from typing import Iterable, List

from ..stylist.money import amounts_in
from .evidence import RECORD_ID, Evidence

MAX_CARDS = 4
MAX_REPLY_CHARS = 1500

# "3 left", "only 2 in stock", "5 pieces available"
_STOCK_CLAIM = re.compile(
    r"\b(\d+)\s+(?:units?|pieces?)\b|\b(\d+)\s+(?:left|in stock|available)\b", re.IGNORECASE
)
# Internal vocabulary that must never reach a shopper.
_INTERNAL = re.compile(
    r"\b(?:svc-[a-z]+|TRC-\d+|tool[_ ]?call|system prompt|tool_result|reply_to_customer|"
    r"search_products|get_product|get_pairings|get_store_policies|list_my_orders|get_order|"
    r"track_shipment|get_return_status|get_style_profile|save_style_profile)\b",
    re.IGNORECASE,
)


def is_internal(text: str) -> bool:
    """True if ``text`` names internal machinery (tools, service accounts, trace ids)."""
    return bool(_INTERNAL.search(text or ""))


@dataclass
class Verdict:
    passed: bool
    problems: List[str] = field(default_factory=list)


def review(message: str, product_ids: List[str], evidence: Evidence, sizes: Iterable[str] = ()) -> Verdict:
    problems: List[str] = []
    sizes = list(sizes)
    text = message or ""

    if not text.strip():
        problems.append("The reply is empty.")
    if len(text) > MAX_REPLY_CHARS:
        problems.append(f"The reply is too long; keep it under {MAX_REPLY_CHARS} characters.")
    if len(product_ids) > MAX_CARDS:
        problems.append(f"List at most {MAX_CARDS} products.")

    for pid in product_ids:
        if pid not in evidence.products:
            problems.append(f"{pid} was not returned by a tool this turn; search or fetch it first, or drop it.")
        elif not evidence.in_stock(pid, sizes):
            name = evidence.products[pid].get("name", pid)
            where = f" in the shopper's size ({', '.join(sizes)})" if sizes else ""
            problems.append(f"{name} ({pid}) is sold out{where}; do not recommend it.")

    allowed_amounts = evidence.amounts | evidence.price_amounts(product_ids)
    for amount in amounts_in(text):
        if round(amount, 2) not in allowed_amounts:
            problems.append(f"The amount ₹{amount:,.0f} does not appear in the tool results.")

    for match in _STOCK_CLAIM.finditer(text):
        claimed = int(match.group(1) or match.group(2))
        if claimed not in evidence.stock_counts and float(claimed) not in evidence.numbers:
            problems.append(f"The count {claimed} does not match the stock in the tool results.")

    for record_id in {m.upper() for m in RECORD_ID.findall(text)}:
        if record_id not in evidence.identifiers:
            problems.append(f"{record_id} does not appear in the tool results; never invent order or product ids.")

    if _INTERNAL.search(text):
        problems.append("The reply mentions internal system details; describe results in shopper language only.")

    return Verdict(passed=not problems, problems=problems)
