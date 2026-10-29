import re
from typing import Dict, Pattern, Tuple


ENTITY_ID_PATTERNS: Dict[str, Pattern[str]] = {
    "product": re.compile(r"^PRD-\d{3,4}$"),
    "sku": re.compile(r"^PRD-\d{3,4}-[A-Z]{2,4}-[A-Z0-9]{1,4}$"),
    "category": re.compile(r"^CAT-(?:MEN|WMN|KID|\d{2})$"),
    "customer": re.compile(r"^CUS-\d{3,5}$"),
    "address": re.compile(r"^ADR-\d{3,5}$"),
    "cart": re.compile(r"^CRT-\d{3,5}$"),
    "order": re.compile(r"^ORD-\d{4,6}$"),
    "payment": re.compile(r"^PAY-\d{4,6}$"),
    "invoice": re.compile(r"^INV-\d{4,6}$"),
    "shipment": re.compile(r"^SHP-\d{4,6}$"),
    "return": re.compile(r"^RET-\d{4,6}$"),
    "refund": re.compile(r"^RFD-\d{4,6}$"),
    "ticket": re.compile(r"^TKT-\d{4,6}$"),
    "policy": re.compile(r"^POL-[A-Z]{3}-\d{2}$"),
    "trace": re.compile(r"^TRC-\d{6}$"),
}

PREFIX_MAP: Dict[str, Tuple[str, int]] = {
    "product": ("PRD", 3),
    "customer": ("CUS", 3),
    "address": ("ADR", 3),
    "cart": ("CRT", 3),
    "order": ("ORD", 4),
    "payment": ("PAY", 4),
    "invoice": ("INV", 4),
    "shipment": ("SHP", 4),
    "return": ("RET", 4),
    "refund": ("RFD", 4),
    "ticket": ("TKT", 4),
    "trace": ("TRC", 6),
}


def format_short_id(entity_type: str, seq_number: int) -> str:
    if entity_type not in PREFIX_MAP:
        raise ValueError(f"Unsupported entity_type: {entity_type}")
    prefix, width = PREFIX_MAP[entity_type]
    return f"{prefix}-{seq_number:0{width}d}"


def format_sku(product_id: str, color_code: str, size_code: str) -> str:
    candidate = f"{product_id.strip().upper()}-{color_code.strip().upper()}-{size_code.strip().upper()}"
    if not validate_short_id("sku", candidate):
        raise ValueError(f"Invalid SKU format: {candidate}")
    return candidate


def validate_short_id(entity_type: str, entity_id: str) -> bool:
    pattern = ENTITY_ID_PATTERNS.get(entity_type)
    if not pattern:
        return False
    return bool(pattern.match((entity_id or "").strip()))
