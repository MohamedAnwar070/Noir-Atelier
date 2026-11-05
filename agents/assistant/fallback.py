"""Deterministic replies used when the model is unavailable or its draft cannot be verified.

No intent keywords here: the shopper's message is handed to the catalogue search
engine as a query (its vocabulary and synonyms are data-driven), and the reply is
written only from what the backend returned.
"""

from typing import Any, Dict, List, Optional, Tuple

from ..stylist.money import format_inr
from .evidence import Evidence
from .tools import ToolEnv, ToolInputError, search_products

MAX_FALLBACK_CARDS = 3


def price_text(product: Dict[str, Any]) -> str:
    prices = [float(v["mrp_inr"]) for v in product.get("variants", []) if v.get("is_active", True)]
    if not prices:
        return format_inr(float(product.get("mrp_inr") or 0))
    low, high = min(prices), max(prices)
    return format_inr(low) if low == high else f"from {format_inr(low)}"


def _listing(products: List[Dict[str, Any]]) -> str:
    return " ".join(f"{p['name']} ({price_text(p)})." for p in products)


def template_from_evidence(evidence: Evidence, sizes: List[str]) -> Tuple[str, List[str]]:
    """A safe reply from verified facts only (used after a draft failed verification twice)."""
    picks = [pid for pid in evidence.products if evidence.in_stock(pid, sizes)][:MAX_FALLBACK_CARDS]
    if picks:
        return (
            "Here is what I can confirm from the collection right now: "
            + _listing([evidence.products[p] for p in picks])
            + " Tap a piece for sizes and details.",
            picks,
        )
    return (
        "I want to be sure everything I tell you is accurate, and I couldn't confirm that just now. "
        "Could you rephrase or add a detail such as the garment, colour or occasion? "
        "For order questions, My Orders always shows the latest status.",
        [],
    )


def offline_reply(env: ToolEnv, message: str) -> Tuple[str, List[str], Optional[str]]:
    """Reply without a model: search the catalogue with the shopper's words. Returns (text, ids, error)."""
    error, picks = None, []
    try:
        outcome = search_products(env, {"query": message[:120], "limit": MAX_FALLBACK_CARDS})
        if outcome.is_error:
            error = str(outcome.content.get("error"))
        picks = list(outcome.summary.get("product_ids") or [])[:MAX_FALLBACK_CARDS]
    except ToolInputError as exc:  # cannot happen with a plain query; kept for safety
        error = str(exc)
    notice = "I'm working in a simpler mode at the moment, so I can search the collection but not answer detailed questions."
    if picks:
        return (
            f"{notice} These pieces match what you asked: "
            + _listing([env.evidence.products[p] for p in picks])
            + " For orders, deliveries and returns, please use My Orders.",
            picks,
            error,
        )
    return (
        f"{notice} I couldn't find in-stock pieces for that. Try a garment type, colour or occasion — "
        "for example \"linen shirt for summer\". For orders, deliveries and returns, please use My Orders.",
        [],
        error,
    )
