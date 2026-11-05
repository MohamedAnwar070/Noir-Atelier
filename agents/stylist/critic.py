"""[5] Critic — deterministic grounding check of a draft reply before the shopper sees it.

Deliberately code, not a model: grounding rules are exact, so they are checked
exactly. A draft passes only if
  * every product it lists came from this turn's tool results,
  * every listed product is in stock and (if a budget is set) within it,
  * every rupee amount it writes is a price/total/threshold we actually have,
  * every stock count it states matches the tool result,
  * it does not name a product from the results without listing it.
Failures come back as plain-language problems the writer can fix on retry.
"""

import re
from itertools import combinations
from typing import Dict, List, Set

from .contracts import Draft, ProductFact, StyleProfile, Verdict, WorkerResults
from .money import amounts_in

_STOCK_CLAIM = re.compile(r"\b(\d+)\s+(?:units?|pieces?)\b|\b(\d+)\s+(?:in stock|left|available)\b", re.IGNORECASE)


def _allowed_amounts(listed: List[ProductFact], profile: StyleProfile, pricing: Dict) -> Set[float]:
    amounts: Set[float] = set()
    for fact in listed:
        amounts |= {fact.price_min, fact.price_max}
    for a, b in combinations(listed, 2):  # "together that's ₹X" for an outfit of two
        amounts.add(a.price_min + b.price_min)
    for value in (profile.budget_max_inr, profile.budget_min_inr,
                  pricing.get("free_shipping_threshold_inr"), pricing.get("default_shipping_fee_inr")):
        if value is not None:
            amounts.add(float(value))
    return {round(a, 2) for a in amounts}


def review(draft: Draft, results: WorkerResults, profile: StyleProfile, pricing: Dict) -> Verdict:
    problems: List[str] = []
    facts = results.by_id()

    if not draft.reply.strip():
        problems.append("The reply is empty.")

    unknown = [pid for pid in draft.product_ids if pid not in facts]
    if unknown:
        problems.append(f"Lists products that were not in the tool results: {', '.join(unknown)}.")
    listed = [facts[pid] for pid in draft.product_ids if pid in facts]

    for fact in listed:
        if not fact.in_stock:
            problems.append(f"{fact.name} is out of stock and must not be recommended.")
        elif fact.available_in(profile.sizes) is False:
            problems.append(f"{fact.name} is sold out in the shopper's size ({', '.join(profile.sizes)}).")
        if profile.budget_max_inr is not None and fact.price_min > float(profile.budget_max_inr):
            problems.append(f"{fact.name} costs more than the shopper's budget.")

    allowed = _allowed_amounts(listed, profile, pricing)
    for amount in amounts_in(draft.reply):
        if round(amount, 2) not in allowed:
            problems.append(f"The amount ₹{amount:,.0f} is not a price from the tool results.")

    # A stated count may be the total or one size's count ("only 3 left in M").
    stocks = {f.stock for f in listed} | {q for f in listed for q in f.stock_by_size.values()}
    for match in _STOCK_CLAIM.finditer(draft.reply):
        claimed = int(match.group(1) or match.group(2))
        if claimed not in stocks:
            problems.append(f"The stock count {claimed} does not match the tool results.")

    lowered = draft.reply.lower()
    for fact in facts.values():
        if fact.product_id not in draft.product_ids and fact.name.lower() in lowered:
            problems.append(f"Mentions {fact.name} without listing its product id.")

    return Verdict(passed=not problems, problems=problems)
