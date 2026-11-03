import re
from typing import Any, Dict, List, Optional, Tuple

from ..client import PlatformApiClient
from ..tools.product_tools import CatalogTools

PRODUCT_ID_RE = re.compile(r"\b(PRD-\d{3})\b", re.IGNORECASE)
SIZE_EXPLICIT_RE = re.compile(
    r"(?:\bsize\s+|\bin\s+size\s+|\bsize:\s*|\b)(XS|S|M|L|XL|4Y|6Y|8Y|10Y|12Y)\b",
    re.IGNORECASE,
)
QTY_PATTERNS = [
    re.compile(r"\b(?:buy|purchase|order|add|get|want|need)\s+(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\s*(?:x|pcs?|pieces?|units?|qty|quantity|of)\b", re.IGNORECASE),
    re.compile(r"\b(?:qty|quantity)\s*[:=]?\s*(\d{1,2})\b", re.IGNORECASE),
]
WORD_NUMBERS = {
    "one": 1,
    "a": 1,
    "an": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
}

STOP_WORDS = {
    "i",
    "want",
    "to",
    "buy",
    "purchase",
    "order",
    "place",
    "add",
    "in",
    "my",
    "bag",
    "cart",
    "shopping",
    "for",
    "the",
    "a",
    "an",
    "of",
    "please",
    "can",
    "you",
    "me",
    "show",
    "find",
    "get",
    "with",
    "and",
    "or",
    "women",
    "men",
    "kids",
    "womens",
    "mens",
    "size",
}


def format_inr(val: Any) -> str:
    try:
        num = float(val)
        if num.is_integer():
            return f"₹{int(num):,}"
        return f"₹{num:,.2f}"
    except Exception:
        return f"₹{val}"


def _active_variants(prod: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [v for v in (prod.get("variants") or []) if v.get("is_active", True)]


def format_price_range(prod: Dict[str, Any]) -> str:
    """Product price as the storefront shows it: one price, or "₹min – ₹max" when sizes differ."""
    prices = sorted({float(v["mrp_inr"]) for v in _active_variants(prod)})
    if len(prices) > 1:
        return f"{format_inr(prices[0])} – {format_inr(prices[-1])}"
    return format_inr(prices[0] if prices else prod.get("mrp_inr", 0))


def format_size_prices(prod: Dict[str, Any]) -> str:
    """Per-size price list, e.g. "S ₹2,399 · M ₹2,499"; falls back to plain sizes."""
    variants = _active_variants(prod)
    if variants:
        return " · ".join(f"{v['size']} {format_inr(v['mrp_inr'])}" for v in variants)
    return ", ".join(prod.get("sizes_available", []))


def extract_quantity(msg: str, context: Dict[str, Any]) -> int:
    if context.get("quantity") is not None:
        return max(1, min(99, int(context["quantity"])))
    for pat in QTY_PATTERNS:
        m = pat.search(msg)
        if m:
            return max(1, min(99, int(m.group(1))))
    msg_lower = msg.lower()
    for word, val in WORD_NUMBERS.items():
        if re.search(rf"\b(?:buy|purchase|order|add)\s+{word}\b", msg_lower):
            return val
    return 1


def extract_size(msg: str, context: Dict[str, Any], available_sizes: Optional[List[str]] = None) -> str:
    if context.get("size"):
        return str(context["size"]).strip().upper()
    cleaned = re.sub(r"\((?:MEN|WOMEN|KIDS)\)", "", msg, flags=re.IGNORECASE)
    explicit = re.search(r"\bsize\s+(XS|S|M|L|XL|4Y|6Y|8Y|10Y|12Y)\b", cleaned, re.IGNORECASE)
    if explicit:
        return explicit.group(1).upper()
    token_m = re.search(r"\b(XS|XL|4Y|6Y|8Y|10Y|12Y)\b", cleaned, re.IGNORECASE)
    if token_m:
        return token_m.group(1).upper()
    single_m = re.search(r"(?:\bsize\s*|\bin\s+|\()(S|M|L)(?:\)|\b)", cleaned)
    if single_m:
        return single_m.group(1).upper()
    if available_sizes:
        if "M" in available_sizes:
            return "M"
        return str(available_sizes[0]).upper()
    return "M"


def resolve_product_from_message(
    msg: str,
    context: Dict[str, Any],
    client: PlatformApiClient,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    cat_tools = CatalogTools(client)
    scratch_traces: list = []
    code, catalog = cat_tools.search_products(trace_id="TRC-RESOLVE", traces=scratch_traces)
    all_products: List[Dict[str, Any]] = catalog if (code == 200 and isinstance(catalog, list)) else []

    explicit_id = context.get("product_id")
    if not explicit_id:
        pm = PRODUCT_ID_RE.search(msg)
        if pm:
            explicit_id = pm.group(1).upper()

    if explicit_id:
        for p in all_products:
            if p.get("product_id", "").upper() == str(explicit_id).upper():
                return p, all_products
        return {"product_id": str(explicit_id).upper(), "name": str(explicit_id).upper(), "sizes_available": ["M"]}, all_products

    msg_clean = re.sub(r"[^a-z0-9\s]", " ", msg.lower())
    msg_tokens = [t for t in msg_clean.split() if len(t) > 2 and t not in STOP_WORDS]

    best_prod: Optional[Dict[str, Any]] = None
    best_score = 0

    for p in all_products:
        name_lower = str(p.get("name", "")).lower()
        if name_lower and name_lower in msg.lower():
            return p, all_products
        prod_text = f"{p.get('name', '')} {p.get('color', '')} {p.get('department', '')}".lower()
        prod_tokens = set(re.sub(r"[^a-z0-9\s]", " ", prod_text).split())
        score = sum(2 if tok in name_lower else (1 if tok in prod_tokens else 0) for tok in msg_tokens)
        if score > best_score:
            best_score = score
            best_prod = p

    if best_score >= 2 and best_prod is not None:
        return best_prod, all_products

    return None, all_products


def is_generic_browse_query(msg: str) -> bool:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", msg.lower()).strip()
    generic_phrases = {
        "i want to buy",
        "want to buy",
        "i want to shop",
        "help me shop",
        "what can i buy",
        "what do you have",
        "what do you sell",
        "show me products",
        "show all products",
        "show all garments",
        "show me garments",
        "browse",
        "collection",
        "all garments",
        "hi",
        "hello",
        "hey",
    }
    return cleaned in generic_phrases
