"""Search: the assistant's tools — each one a thin, validated wrapper over a real backend API.

Rules every tool follows
  * Calls go through PlatformApiClient as `svc-assistant` (client-side whitelist +
    server-side agent_permissions), always ON BEHALF OF the shopper the server
    authenticated — never an id the model supplies. Order tools need a signed-in shopper.
  * Inputs are validated here (types, lengths, catalogue vocabulary) before any call;
    a bad input returns an error result the model can correct, never an exception.
  * The model sees a compact, whitelisted view of each payload (no pickup codes,
    payment ids, internal fields). The full payload goes into Evidence for grounding
    and product cards.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..client import PlatformApiClient
from ..schemas.state import AgentRole
from .contracts import ChatContext
from .evidence import Evidence

ROLE = AgentRole.ASSISTANT.value
REPLY_TOOL = "reply_to_customer"

SORTS = ["featured", "price_asc", "price_desc", "rating", "newest"]
POLICY_TOPICS = ["returns", "shipping", "payments", "offers", "store", "all"]
INTENTS = [
    "product_search", "product_question", "sizing", "styling_advice", "order_status",
    "shipment_tracking", "returns", "store_policy", "preferences", "action_request",
    "greeting", "out_of_scope", "other",
]
_ORDER_ID = re.compile(r"^ORD-\d{3,6}$")
_SHIPMENT_OR_ORDER = re.compile(r"^(?:ORD|SHP)-\d{3,6}$")
_RETURN_ID = re.compile(r"^RET-\d{3,6}$")
_PRODUCT_REF = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,40}$")


class ToolInputError(ValueError):
    """Invalid model input — returned to the model as a correctable error."""


@dataclass
class ToolOutcome:
    content: Dict[str, Any]  # what the model sees
    is_error: bool = False
    http_status: Optional[int] = None
    summary: Dict[str, Any] = field(default_factory=dict)  # what the trace records


@dataclass
class ToolEnv:
    client: PlatformApiClient
    ctx: ChatContext
    evidence: Evidence
    vocabulary: Dict[str, List[str]]


Handler = Callable[[ToolEnv, Dict[str, Any]], ToolOutcome]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Optional[Handler]
    requires_customer: bool = False
    strict: bool = False

    def definition(self) -> Dict[str, Any]:
        spec: Dict[str, Any] = {"name": self.name, "description": self.description, "input_schema": self.input_schema}
        if self.strict:
            spec["strict"] = True
        return spec


# ============================================================================ helpers


def _api(env: ToolEnv, tool: str, method: str, endpoint: str, *, params=None, body=None) -> Tuple[int, Any]:
    return env.client.call(
        ROLE,
        tool,
        method,
        endpoint,
        on_behalf_of=env.ctx.customer_id,  # server-authenticated shopper only
        trace_id=env.ctx.trace_id,
        params=params,
        json_body=body,
    )


def _api_error(status: int, payload: Any) -> ToolOutcome:
    body = payload if isinstance(payload, dict) else {}
    message = body.get("message") or body.get("detail") or f"Request failed with status {status}"
    if status == 403:
        message = "Not available for this shopper (the record belongs to someone else or sign-in is required)."
    content = {"error": str(message)[:400], "status": status}
    if isinstance(body.get("details"), dict) and status == 422:
        content["details"] = body["details"]  # e.g. allowed values for a field
    return ToolOutcome(content=content, is_error=True, http_status=status, summary={"error_code": body.get("code")})


def _text(args: Dict[str, Any], key: str, max_len: int, required: bool = False) -> Optional[str]:
    value = args.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ToolInputError(f"'{key}' is required.")
        return None
    if not isinstance(value, str):
        raise ToolInputError(f"'{key}' must be a string.")
    return value.strip()[:max_len]


def _number(args: Dict[str, Any], key: str) -> Optional[float]:
    value = args.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ToolInputError(f"'{key}' must be a non-negative number.")
    return float(value)


def _vocab(env: ToolEnv, args: Dict[str, Any], key: str, kind: str, many: bool = False):
    raw = args.get(key)
    if raw is None or raw == [] or raw == "":
        return [] if many else None
    values = raw if isinstance(raw, list) else [raw]
    if not all(isinstance(v, str) for v in values) or len(values) > 6:
        raise ToolInputError(f"'{key}' must be {'a list of up to 6 strings' if many else 'a string'}.")
    allowed = env.vocabulary.get(kind, [])
    norm = [v.strip().upper() if kind == "departments" else v.strip().lower() for v in values]
    unknown = [v for v in norm if v not in allowed]
    if unknown:
        raise ToolInputError(f"Unknown {kind[:-1].replace('_', ' ')} {unknown}. Valid values: {allowed}")
    return norm if many else norm[0]


def product_brief(p: Dict[str, Any], detailed: bool = False) -> Dict[str, Any]:
    """The model's view of a product: facts only, prices and stock per size."""
    brief = {
        "product_id": p.get("product_id"),
        "name": p.get("name"),
        "department": p.get("department"),
        "category": (p.get("category") or {}).get("name"),
        "color": p.get("color"),
        "materials": [m.get("family") for m in p.get("materials", [])],
        "price_by_size": {v["size"]: float(v["mrp_inr"]) for v in p.get("variants", []) if v.get("is_active", True)},
        "stock_by_size": dict(p.get("stock_by_size") or {}),
        "occasions": list(p.get("occasions") or []),
        "palettes": list(p.get("color_palettes") or []),
        "rating": p.get("average_rating"),
        "final_sale": bool(p.get("final_sale")),
    }
    if detailed:
        brief.update(
            {
                "description": (p.get("description") or "")[:700],
                "fit_guide": p.get("fit_guide"),
                "fabric_and_care": p.get("fabric_and_care"),
                "country_of_origin": p.get("country_of_origin"),
                "review_count": p.get("review_count"),
            }
        )
    return brief


_ORDER_FIELDS = (
    "order_id", "status", "status_label", "order_date", "grand_total_inr", "shipping_fee_inr",
    "discount_inr", "payment_status", "tracking_number", "can_cancel", "can_return", "cancelled_at",
)


def order_brief(o: Dict[str, Any]) -> Dict[str, Any]:
    """Shopper-safe order view: no pickup codes, payment ids or internal flags."""
    view = {k: o.get(k) for k in _ORDER_FIELDS if o.get(k) is not None}
    view["items"] = [
        {"product_id": i.get("product_id"), "name": i.get("product_name"), "size": i.get("size"),
         "quantity": i.get("quantity"), "unit_price_inr": i.get("unit_mrp_inr")}
        for i in o.get("items", [])
    ]
    return view


# ============================================================================ handlers


def search_products(env: ToolEnv, args: Dict[str, Any]) -> ToolOutcome:
    query = _text(args, "query", 120)
    department = _vocab(env, args, "department", "departments")
    product_type = _vocab(env, args, "product_type", "product_types")
    colors = _vocab(env, args, "colors", "colors", many=True)
    materials = _vocab(env, args, "materials", "materials", many=True)
    occasions = _vocab(env, args, "occasions", "occasions", many=True)
    palettes = _vocab(env, args, "palettes", "palettes", many=True)
    size = (_text(args, "size", 8) or "").upper() or None
    if size and size not in env.vocabulary.get("sizes", []):
        raise ToolInputError(f"Unknown size '{size}'. Valid sizes: {env.vocabulary.get('sizes', [])}")
    min_price, max_price = _number(args, "min_price"), _number(args, "max_price")
    sort = args.get("sort") or "featured"
    if sort not in SORTS:
        raise ToolInputError(f"'sort' must be one of {SORTS}.")
    limit = args.get("limit") or 6
    if not isinstance(limit, int) or not 1 <= limit <= 8:
        raise ToolInputError("'limit' must be an integer from 1 to 8.")

    params: Dict[str, Any] = {"in_stock_only": True, "sort": sort, "limit": limit * 3 if size else limit}
    for key, value in (("q", query), ("department", department), ("category", product_type),
                       ("color", ",".join(colors)), ("material", ",".join(materials)),
                       ("occasion", ",".join(occasions)), ("palette", ",".join(palettes)),
                       ("min_price", min_price), ("max_price", max_price)):
        if value not in (None, ""):
            params[key] = value

    status, payload = _api(env, "search_products", "GET", "/api/catalog/search", params=params)
    if status != 200 or not isinstance(payload, dict):
        return _api_error(status, payload)
    items = payload.get("items", [])
    if size:
        env.evidence.requested_sizes.add(size)
        items = [i for i in items if (i.get("stock_by_size") or {}).get(size, 0) > 0]
    items = items[:limit]
    for item in items:
        env.evidence.add_product(item)
    interpretation = payload.get("interpretation") or {}
    content = {
        "total_matches": payload.get("total", len(items)),
        "returned": len(items),
        "products": [product_brief(i) for i in items],
        "search_notes": {
            "relaxed": bool(interpretation.get("relaxed")),
            "ignored_filters": interpretation.get("skipped_dimensions") or [],
            "relaxed_filters": interpretation.get("relaxed_dimensions") or [],
            "ignored_words": interpretation.get("ignored_terms") or [],
            "size_filter": size,
        },
    }
    return ToolOutcome(content=content, http_status=status,
                       summary={"returned": len(items), "product_ids": [i["product_id"] for i in items]})


def get_product(env: ToolEnv, args: Dict[str, Any]) -> ToolOutcome:
    ref = (_text(args, "product_id", 40, required=True) or "").upper()
    if not _PRODUCT_REF.match(ref):
        raise ToolInputError("'product_id' must look like PRD-001 or a product SKU.")
    status, payload = _api(env, "get_product", "GET", f"/api/products/{ref}")
    if status != 200 or not isinstance(payload, dict):
        return _api_error(status, payload)
    env.evidence.add_product(payload)
    return ToolOutcome(content={"product": product_brief(payload, detailed=True)}, http_status=status,
                       summary={"product_id": payload.get("product_id")})


def get_pairings(env: ToolEnv, args: Dict[str, Any]) -> ToolOutcome:
    ref = (_text(args, "product_id", 40, required=True) or "").upper()
    if not _PRODUCT_REF.match(ref):
        raise ToolInputError("'product_id' must look like PRD-001 or a product SKU.")
    status, payload = _api(env, "get_pairings", "GET", f"/api/products/{ref}/recommendations")
    if status != 200 or not isinstance(payload, list):
        return _api_error(status, payload)
    items = [p for p in payload if int(p.get("stock") or 0) > 0][:4]
    for item in items:
        env.evidence.add_product(item)
    return ToolOutcome(content={"pairs_with": [product_brief(i) for i in items]}, http_status=status,
                       summary={"product_ids": [i["product_id"] for i in items]})


def get_store_policies(env: ToolEnv, args: Dict[str, Any]) -> ToolOutcome:
    topic = args.get("topic") or "all"
    if topic not in POLICY_TOPICS:
        raise ToolInputError(f"'topic' must be one of {POLICY_TOPICS}.")
    status, payload = _api(env, "get_store_policies", "GET", "/api/config/policies")
    if status != 200 or not isinstance(payload, dict):
        return _api_error(status, payload)
    cfg = payload.get("business_config") or {}
    policies = payload.get("policies") or []

    def rules(*topics: str) -> List[Dict[str, Any]]:
        return [{"title": p.get("title"), "rule": p.get("rule_text")} for p in policies if p.get("topic") in topics]

    sections: Dict[str, Any] = {
        "returns": {"settings": cfg.get("returns_and_refunds"), "rules": rules("returns", "final_sale", "cancellations")},
        "shipping": {"settings": cfg.get("shipping"), "zones": [
            {"name": z.get("name"), "fee_inr": z.get("base_fee_inr"), "estimated_days": z.get("estimated_days")}
            for z in payload.get("shipping_zones") or []]},
        "payments": {"methods": [
            {"name": m.get("name"), "min_order_inr": m.get("min_order_inr"), "max_order_inr": m.get("max_order_inr")}
            for m in payload.get("payment_methods") or []], "tax": cfg.get("tax")},
        "offers": {"coupons": payload.get("coupons") or [], "loyalty": rules("vip_loyalty")},
        "store": {"store": {k: v for k, v in (cfg.get("store") or {}).items() if k in ("name", "currency", "departments", "grievance_officer")}},
    }
    # Only shopper-facing sections: never demo accounts, staff roles or UI configuration.
    content = sections if topic == "all" else {topic: sections[topic]}
    env.evidence.add_payload(content)
    return ToolOutcome(content=content, http_status=status, summary={"topic": topic})


def _need_customer(env: ToolEnv) -> Optional[ToolOutcome]:
    if env.ctx.customer_id:
        return None
    return ToolOutcome(content={"error": "The shopper is not signed in; ask them to sign in to see their orders."},
                       is_error=True, summary={"error_code": "sign_in_required"})


def list_my_orders(env: ToolEnv, args: Dict[str, Any]) -> ToolOutcome:
    if (blocked := _need_customer(env)) is not None:
        return blocked
    status, payload = _api(env, "list_my_orders", "GET", "/api/orders")
    if status != 200 or not isinstance(payload, list):
        return _api_error(status, payload)
    orders = [order_brief(o) for o in payload[:10]]
    env.evidence.add_payload(orders)
    return ToolOutcome(content={"orders": orders, "total_orders": len(payload)}, http_status=status,
                       summary={"returned": len(orders)})


def get_order(env: ToolEnv, args: Dict[str, Any]) -> ToolOutcome:
    if (blocked := _need_customer(env)) is not None:
        return blocked
    order_id = (_text(args, "order_id", 16, required=True) or "").upper()
    if not _ORDER_ID.match(order_id):
        raise ToolInputError("'order_id' must look like ORD-1001.")
    status, payload = _api(env, "get_order", "GET", f"/api/orders/{order_id}")
    if status != 200 or not isinstance(payload, dict):
        return _api_error(status, payload)
    view = order_brief(payload)
    env.evidence.add_payload(view)
    return ToolOutcome(content={"order": view}, http_status=status, summary={"order_id": order_id})


def track_shipment(env: ToolEnv, args: Dict[str, Any]) -> ToolOutcome:
    if (blocked := _need_customer(env)) is not None:
        return blocked
    ref = (_text(args, "order_or_shipment_id", 16, required=True) or "").upper()
    if not _SHIPMENT_OR_ORDER.match(ref):
        raise ToolInputError("'order_or_shipment_id' must look like ORD-1001 or SHP-1001.")
    status, payload = _api(env, "track_shipment", "GET", f"/api/shipments/{ref}")
    if status == 404:
        content = {"shipment": None, "note": "No shipment has been dispatched yet for this order."}
        return ToolOutcome(content=content, http_status=status, summary={"ref": ref, "found": False})
    if status != 200 or not isinstance(payload, dict):
        return _api_error(status, payload)
    view = {k: payload.get(k) for k in ("shipment_id", "order_id", "carrier", "tracking_number", "status",
                                         "scheduled_pickup", "delivered_date")}
    env.evidence.add_payload(view)
    return ToolOutcome(content={"shipment": view}, http_status=status, summary={"ref": ref, "found": True})


def get_return_status(env: ToolEnv, args: Dict[str, Any]) -> ToolOutcome:
    if (blocked := _need_customer(env)) is not None:
        return blocked
    return_id = (_text(args, "return_id", 16, required=True) or "").upper()
    if not _RETURN_ID.match(return_id):
        raise ToolInputError("'return_id' must look like RET-1001.")
    status, payload = _api(env, "get_return_status", "GET", f"/api/returns/{return_id}")
    if status != 200 or not isinstance(payload, dict):
        return _api_error(status, payload)
    view = {k: payload.get(k) for k in ("return_id", "order_id", "status", "reason_category", "approval_tier",
                                         "refund_id", "refund_status", "refund_amount_inr", "created_at")
            if payload.get(k) is not None}
    env.evidence.add_payload(view)
    return ToolOutcome(content={"return": view}, http_status=status, summary={"return_id": return_id})


_PROFILE_LISTS = ("product_types", "colors", "palettes", "materials", "sizes")
_PROFILE_SCALARS = ("occasion", "department", "budget_min_inr", "budget_max_inr")


def get_style_profile(env: ToolEnv, args: Dict[str, Any]) -> ToolOutcome:
    status, payload = _api(env, "get_style_profile", "GET", f"/api/agents/sessions/{env.ctx.session_id}/profile")
    if status != 200 or not isinstance(payload, dict):
        return _api_error(status, payload)
    profile = payload.get("profile") or {}
    profile.pop("confidence", None)
    env.evidence.add_payload(profile)
    return ToolOutcome(content={"profile": profile}, http_status=status, summary={})


def save_style_profile(env: ToolEnv, args: Dict[str, Any]) -> ToolOutcome:
    """Merge the given preference fields into the session profile (provided fields replace)."""
    path = f"/api/agents/sessions/{env.ctx.session_id}/profile"
    status, payload = _api(env, "save_style_profile", "GET", path)
    if status != 200 or not isinstance(payload, dict):
        return _api_error(status, payload)
    profile = dict(payload.get("profile") or {})
    changed = []
    for key in _PROFILE_LISTS:
        if key in args and args[key] is not None:
            if not isinstance(args[key], list) or not all(isinstance(v, str) for v in args[key]):
                raise ToolInputError(f"'{key}' must be a list of strings.")
            profile[key] = [v.strip().upper() if key == "sizes" else v.strip().lower() for v in args[key]][:10]
            changed.append(key)
    for key in _PROFILE_SCALARS:
        if key in args:
            value = args[key]
            if key.startswith("budget"):
                value = _number(args, key)
            elif value is not None:
                value = str(value).strip().upper() if key == "department" else str(value).strip().lower()
            profile[key] = value
            changed.append(key)
    avoid = args.get("avoid")
    if isinstance(avoid, dict):
        merged = dict(profile.get("avoid") or {})
        for key in ("colors", "palettes", "materials", "product_types"):
            if isinstance(avoid.get(key), list):
                merged[key] = [str(v).strip().lower() for v in avoid[key]][:10]
        profile["avoid"] = merged
        changed.append("avoid")
    if not changed:
        raise ToolInputError("Provide at least one preference field to save.")
    status, saved = _api(env, "save_style_profile", "PUT", path, body={"profile": profile})
    if status != 200 or not isinstance(saved, dict):
        return _api_error(status, saved)
    return ToolOutcome(content={"saved": changed, "profile": saved.get("profile")}, http_status=status,
                       summary={"saved": changed})


# ============================================================================ registry

_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": {"type": "string"}}

TOOLS: List[ToolSpec] = [
    ToolSpec(
        "search_products",
        "Search the live Noir Atelier catalogue (in-stock pieces only). Use for any request to find, browse, "
        "compare or recommend garments. Put the shopper's own words in `query` (the search engine understands "
        "synonyms like 'kurta', 'office wear', 'earthy'); use the structured filters only with values from the "
        "catalogue vocabulary in your instructions. Set `size` when the shopper's size is known so only pieces "
        "available in that size come back. Returns prices and stock per size.",
        {
            "type": "object",
            "properties": {
                "query": {**_STR, "description": "Free-text description in the shopper's words."},
                "department": {**_STR, "description": "Department code from the vocabulary, e.g. MEN."},
                "product_type": {**_STR, "description": "One product type slug from the vocabulary."},
                "colors": {**_STR_LIST, "description": "Colour families from the vocabulary."},
                "materials": {**_STR_LIST, "description": "Material families from the vocabulary."},
                "occasions": {**_STR_LIST, "description": "Occasion codes from the vocabulary."},
                "palettes": {**_STR_LIST, "description": "Palette codes from the vocabulary."},
                "size": {**_STR, "description": "Size the shopper wears, e.g. M or 8Y."},
                "min_price": {"type": "number", "description": "Minimum price in INR."},
                "max_price": {"type": "number", "description": "Maximum price in INR (the shopper's budget)."},
                "sort": {"type": "string", "enum": SORTS},
                "limit": {"type": "integer", "description": "How many products to return (1-8, default 6)."},
            },
            "additionalProperties": False,
        },
        search_products,
    ),
    ToolSpec(
        "get_product",
        "Get full details of one product: description, fit guide, fabric and care, origin, price and stock per size. "
        "Use when the shopper asks about a specific piece, its sizing or materials.",
        {"type": "object", "properties": {"product_id": {**_STR, "description": "e.g. PRD-001"}},
         "required": ["product_id"], "additionalProperties": False},
        get_product,
    ),
    ToolSpec(
        "get_pairings",
        "Get in-stock pieces that pair well with a product (to complete a look).",
        {"type": "object", "properties": {"product_id": {**_STR, "description": "e.g. PRD-001"}},
         "required": ["product_id"], "additionalProperties": False},
        get_pairings,
    ),
    ToolSpec(
        "get_store_policies",
        "Get the store's current rules: returns and cancellations, shipping fees and times, payment methods and "
        "tax, offers and coupons, store contact. Use for any policy question instead of answering from memory.",
        {"type": "object", "properties": {"topic": {"type": "string", "enum": POLICY_TOPICS}},
         "required": ["topic"], "additionalProperties": False},
        get_store_policies,
    ),
    ToolSpec(
        "list_my_orders",
        "List the signed-in shopper's recent orders with status and totals.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        list_my_orders,
        requires_customer=True,
    ),
    ToolSpec(
        "get_order",
        "Get one of the signed-in shopper's orders by id (status, items, totals, whether it can still be "
        "cancelled or returned).",
        {"type": "object", "properties": {"order_id": {**_STR, "description": "e.g. ORD-1001"}},
         "required": ["order_id"], "additionalProperties": False},
        get_order,
        requires_customer=True,
    ),
    ToolSpec(
        "track_shipment",
        "Track the delivery of one of the signed-in shopper's orders (carrier, tracking number, status).",
        {"type": "object", "properties": {"order_or_shipment_id": {**_STR, "description": "ORD-1001 or SHP-1001"}},
         "required": ["order_or_shipment_id"], "additionalProperties": False},
        track_shipment,
        requires_customer=True,
    ),
    ToolSpec(
        "get_return_status",
        "Get the status of one of the signed-in shopper's returns and its refund.",
        {"type": "object", "properties": {"return_id": {**_STR, "description": "e.g. RET-1001"}},
         "required": ["return_id"], "additionalProperties": False},
        get_return_status,
        requires_customer=True,
    ),
    ToolSpec(
        "get_style_profile",
        "Read what this conversation has learned about the shopper's preferences (sizes, colours, budget, "
        "occasion, things to avoid).",
        {"type": "object", "properties": {}, "additionalProperties": False},
        get_style_profile,
    ),
    ToolSpec(
        "save_style_profile",
        "Remember the shopper's stated preferences for later turns. Only save what the shopper said; use "
        "vocabulary values. Provided fields replace the stored ones.",
        {
            "type": "object",
            "properties": {
                "department": _STR, "occasion": _STR,
                "product_types": _STR_LIST, "colors": _STR_LIST, "palettes": _STR_LIST,
                "materials": _STR_LIST, "sizes": _STR_LIST,
                "budget_min_inr": {"type": "number"}, "budget_max_inr": {"type": "number"},
                "avoid": {
                    "type": "object",
                    "properties": {"colors": _STR_LIST, "palettes": _STR_LIST, "materials": _STR_LIST,
                                   "product_types": _STR_LIST},
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
        save_style_profile,
    ),
    ToolSpec(
        REPLY_TOOL,
        "Send your final answer to the shopper. Call this exactly once, alone, after you have the facts. "
        "`message` is what the shopper reads. `product_ids` are the products to show as cards (only ids returned "
        "by tools in this turn, at most 4; empty list if none). `follow_up_prompts` are up to 3 short next "
        "questions the shopper might tap. `intent` classifies what the shopper wanted and `plan_note` is one "
        "sentence on how you answered — both are internal and never shown.",
        {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "product_ids": {"type": "array", "items": {"type": "string"}},
                "follow_up_prompts": {"type": "array", "items": {"type": "string"}},
                "intent": {"type": "string", "enum": INTENTS},
                "plan_note": {"type": "string"},
            },
            "required": ["message", "product_ids", "follow_up_prompts", "intent", "plan_note"],
            "additionalProperties": False,
        },
        None,
        strict=True,
    ),
]

TOOLS_BY_NAME: Dict[str, ToolSpec] = {t.name: t for t in TOOLS}

# What the shopper sees while a tool runs (streamed progress) — never the tool name.
PROGRESS_LABELS: Dict[str, str] = {
    "search_products": "Searching the collection…",
    "get_product": "Looking at the details…",
    "get_pairings": "Finding pieces that pair well…",
    "get_store_policies": "Checking our store policies…",
    "list_my_orders": "Looking up your orders…",
    "get_order": "Looking up your order…",
    "track_shipment": "Checking your delivery…",
    "get_return_status": "Checking your return…",
    "get_style_profile": "Recalling your preferences…",
    "save_style_profile": "Noting your preferences…",
}


def tools_for(ctx: ChatContext) -> List[ToolSpec]:
    """Guests never see order tools (the model cannot even try them)."""
    return [t for t in TOOLS if ctx.signed_in or not t.requires_customer]
