"""Reference (lookup) data shipped with the application.

Single definition used by:
  * migrations 0003 & 0004 — to populate existing databases,
  * scripts/seed_demo.py — to populate fresh databases.

``ensure_reference_data`` only INSERTs rows that are missing; it never
overwrites a row, so labels/flags edited by an admin survive deploys.
After the first install this data is owned by the database (admin APIs),
not by this file.
"""

from typing import Any, Dict, Iterable, List, Optional, Tuple, Type

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AgentPermission,
    Category,
    Color,
    Department,
    Material,
    Occasion,
    OrderStatus,
    Palette,
    Permission,
    RefundStatus,
    ReturnReason,
    Role,
    RolePermission,
    SearchSynonym,
)

DEPARTMENTS: List[Dict[str, Any]] = [
    {"code": "MEN", "name": "Men", "display_order": 1},
    {"code": "WOMEN", "name": "Women", "display_order": 2},
    {"code": "KIDS", "name": "Kids", "display_order": 3},
]

# Product-type taxonomy. IDs follow the CAT-<2 digits> convention (utils/id_generator).
CATEGORIES: List[Dict[str, Any]] = [
    {"category_id": "CAT-10", "slug": "tops", "name": "Tops", "parent_id": None, "display_order": 10},
    {"category_id": "CAT-11", "slug": "shirt", "name": "Shirts", "parent_id": "CAT-10", "display_order": 11},
    {"category_id": "CAT-12", "slug": "t-shirt", "name": "T-Shirts", "parent_id": "CAT-10", "display_order": 12},
    {"category_id": "CAT-20", "slug": "outerwear", "name": "Outerwear", "parent_id": None, "display_order": 20},
    {"category_id": "CAT-21", "slug": "overshirt", "name": "Overshirts", "parent_id": "CAT-20", "display_order": 21},
    {"category_id": "CAT-30", "slug": "knitwear", "name": "Knitwear", "parent_id": None, "display_order": 30},
    {"category_id": "CAT-40", "slug": "dress", "name": "Dresses", "parent_id": None, "display_order": 40},
]

COLORS: List[Dict[str, Any]] = [
    {"name": "Noir Black", "family": "black", "hex_code": "#111111"},
    {"name": "Obsidian", "family": "black", "hex_code": "#0B0B0C"},
    {"name": "Charcoal", "family": "grey", "hex_code": "#36454F"},
    {"name": "Ivory", "family": "white", "hex_code": "#FFFFF0"},
    {"name": "Midnight Navy", "family": "blue", "hex_code": "#191970"},
]

MATERIALS: List[Dict[str, Any]] = [
    {"name": "Belgian Linen", "family": "linen"},
    {"name": "Merino Wool", "family": "wool"},
    {"name": "Mulberry Silk", "family": "silk"},
    {"name": "Pima Cotton", "family": "cotton"},
    {"name": "Recycled Polyamide", "family": "polyamide"},
]

# term → (dimension, value). Values are department codes, category slugs,
# colour families or material families. Plural/singular forms of names and
# families are matched automatically by the search engine; synonyms cover
# genuinely different words.
SYNONYMS: List[Dict[str, Any]] = [
    # product types
    *({"term": t, "dimension": "product_type", "value": "t-shirt"} for t in ("tee", "tees", "tshirt", "tshirts", "t shirt")),
    *({"term": t, "dimension": "product_type", "value": "shirt"} for t in ("button-up", "button up", "button down", "button-down")),
    *({"term": t, "dimension": "product_type", "value": "knitwear"} for t in ("sweater", "sweaters", "jumper", "jumpers", "pullover", "pullovers", "crewneck", "crewnecks", "knit", "knits")),
    *({"term": t, "dimension": "product_type", "value": "outerwear"} for t in ("jacket", "jackets", "coat", "coats")),
    *({"term": t, "dimension": "product_type", "value": "overshirt"} for t in ("shacket", "shackets", "shirt jacket")),
    *({"term": t, "dimension": "product_type", "value": "dress"} for t in ("gown", "gowns", "frock", "frocks")),
    *({"term": t, "dimension": "product_type", "value": "tops"} for t in ("top",)),
    # departments
    *({"term": t, "dimension": "department", "value": "MEN"} for t in ("mens", "men's", "man", "gents", "male")),
    *({"term": t, "dimension": "department", "value": "WOMEN"} for t in ("womens", "women's", "woman", "ladies", "female")),
    *({"term": t, "dimension": "department", "value": "KIDS"} for t in ("kid", "kids'", "children", "child", "boys", "girls")),
    # colours
    *({"term": t, "dimension": "color", "value": "blue"} for t in ("navy",)),
    *({"term": t, "dimension": "color", "value": "grey"} for t in ("gray",)),
    *({"term": t, "dimension": "color", "value": "white"} for t in ("cream", "off-white", "off white")),
    # materials
    *({"term": t, "dimension": "material", "value": "wool"} for t in ("merino", "woolen", "woollen")),
    *({"term": t, "dimension": "material", "value": "linen"} for t in ("flax",)),
    # occasions — how shoppers describe an event
    *({"term": t, "dimension": "occasion", "value": "wedding"} for t in ("engagement", "reception", "sangeet", "shaadi", "marriage", "wedding guest", "weddings")),
    *({"term": t, "dimension": "occasion", "value": "festive"} for t in ("diwali", "eid", "puja", "pooja", "navratri", "onam", "pongal", "festival", "festivals")),
    *({"term": t, "dimension": "occasion", "value": "evening"} for t in ("party", "parties", "cocktail", "cocktails", "dinner", "date night", "night out")),
    *({"term": t, "dimension": "occasion", "value": "black_tie"} for t in ("black tie", "black-tie", "gala", "formal", "opera")),
    *({"term": t, "dimension": "occasion", "value": "work"} for t in ("office", "meeting", "meetings", "business", "interview", "workwear")),
    *({"term": t, "dimension": "occasion", "value": "resort"} for t in ("vacation", "holiday", "beach", "summer")),
    *({"term": t, "dimension": "occasion", "value": "travel"} for t in ("flight", "trip", "travelling", "traveling")),
    *({"term": t, "dimension": "occasion", "value": "lounge"} for t in ("home", "lounging", "loungewear", "relaxed")),
    *({"term": t, "dimension": "occasion", "value": "everyday"} for t in ("casual", "daily", "weekend")),
    # palettes — colour moods rather than hues
    *({"term": t, "dimension": "palette", "value": "muted"} for t in ("calm", "subtle", "understated", "soft", "dusty", "gentle")),
    *({"term": t, "dimension": "palette", "value": "pale"} for t in ("pastel", "pastels", "airy")),
    *({"term": t, "dimension": "palette", "value": "jewel"} for t in ("bold", "vibrant", "bright", "jewel tone", "jewel tones", "regal")),
    *({"term": t, "dimension": "palette", "value": "earthy"} for t in ("earth", "earth tones", "warm")),
    *({"term": t, "dimension": "palette", "value": "neutral"} for t in ("minimal", "minimalist", "classic", "monochrome")),
    *({"term": t, "dimension": "palette", "value": "dark"} for t in ("deep", "moody", "darker", "deeper")),
    *({"term": t, "dimension": "palette", "value": "pale"} for t in ("lighter", "paler")),
    *({"term": t, "dimension": "palette", "value": "muted"} for t in ("softer", "calmer", "less bright", "toned down")),
]

# Occasions a garment can be worn to. Product assignments are curated data
# (see backend/data/style_tags_draft.json), never inferred at runtime.
OCCASIONS: List[Dict[str, Any]] = [
    {"code": "everyday", "name": "Everyday", "display_order": 1},
    {"code": "work", "name": "Work", "display_order": 2},
    {"code": "travel", "name": "Travel", "display_order": 3},
    {"code": "resort", "name": "Resort & summer", "display_order": 4},
    {"code": "lounge", "name": "Lounge", "display_order": 5},
    {"code": "evening", "name": "Evening & parties", "display_order": 6},
    {"code": "festive", "name": "Festive", "display_order": 7},
    {"code": "wedding", "name": "Weddings & engagements", "display_order": 8},
    {"code": "black_tie", "name": "Black tie", "display_order": 9},
]

# Colour moods. Colour→palette assignments are curated data (same draft file).
PALETTES: List[Dict[str, Any]] = [
    {"code": "muted", "name": "Muted & calm", "display_order": 1},
    {"code": "neutral", "name": "Neutral", "display_order": 2},
    {"code": "pale", "name": "Pale & light", "display_order": 3},
    {"code": "earthy", "name": "Earthy", "display_order": 4},
    {"code": "dark", "name": "Dark", "display_order": 5},
    {"code": "jewel", "name": "Jewel tones", "display_order": 6},
]

# Every status the order/refund state machines can produce.
ORDER_STATUSES: List[Dict[str, Any]] = [
    {"code": "pending", "label": "Awaiting payment", "tone": "warning", "is_cancellable": True, "display_order": 1},
    {"code": "paid", "label": "Paid", "tone": "success", "is_cancellable": True, "display_order": 2},
    {"code": "confirmed", "label": "Confirmed", "tone": "info", "is_cancellable": True, "display_order": 3},
    {"code": "needs_review", "label": "Under review", "tone": "warning", "display_order": 4},
    {"code": "shipped", "label": "Shipped", "tone": "info", "display_order": 5},
    {"code": "delivered", "label": "Delivered", "tone": "success", "is_returnable": True, "display_order": 6},
    {"code": "picked_up", "label": "Collected", "tone": "success", "is_returnable": True, "display_order": 7},
    {"code": "pending_return", "label": "Return in progress", "tone": "warning", "display_order": 8},
    {"code": "returned", "label": "Returned", "tone": "neutral", "display_order": 9},
    {"code": "refunded", "label": "Refunded", "tone": "neutral", "display_order": 10},
    {"code": "cancelled", "label": "Cancelled", "tone": "error", "display_order": 11},
    {"code": "expired", "label": "Hold expired", "tone": "error", "display_order": 12},
]

REFUND_STATUSES: List[Dict[str, Any]] = [
    {"code": "qc_passed", "label": "Ready to refund", "tone": "info", "display_order": 1},
    {"code": "pending_approval", "label": "Awaiting approval", "tone": "warning", "awaiting_approval": True, "display_order": 2},
    {"code": "awaiting_secondary_approval", "label": "Awaiting 2nd approval", "tone": "warning", "awaiting_approval": True, "display_order": 3},
    {"code": "approved", "label": "Approved", "tone": "success", "display_order": 4},
    {"code": "processed", "label": "Refunded", "tone": "success", "display_order": 5},
]

RETURN_REASONS: List[Dict[str, Any]] = [
    {"code": "size_mismatch", "label": "Size or fit isn't right", "display_order": 1},
    {"code": "style_preference", "label": "Style or silhouette preference", "display_order": 2},
    {"code": "changed_mind", "label": "Changed my mind", "display_order": 3},
    {"code": "not_as_described", "label": "Not as described", "display_order": 4},
    {"code": "fabric_defect", "label": "Fabric or stitching defect", "is_defect_claim": True, "display_order": 5},
    {"code": "damaged_in_transit", "label": "Damaged in transit", "is_defect_claim": True, "display_order": 6},
]

FIT_FEEDBACK_OPTIONS: List[Dict[str, str]] = [
    {"code": "true_to_size", "label": "Fits true to size"},
    {"code": "runs_small", "label": "Runs slightly small"},
    {"code": "runs_large", "label": "Runs slightly relaxed"},
]

# Canonical RBAC Roles & Granular Permissions (resource:action).
ROLES: List[Dict[str, Any]] = [
    {
        "code": "customer",
        "name": "Maison Client",
        "description": "Authenticated customer able to curate bags, place orders, manage addresses, submit verified reviews, and initiate returns.",
        "actor_type": "customer",
        "hierarchy_level": 10,
        "is_system": True,
        "is_active": True,
    },
    {
        "code": "support_agent",
        "name": "Client Concierge",
        "description": "Maison client-service specialist authorized to inspect orders, returns, and resolve escalated support tickets.",
        "actor_type": "admin",
        "hierarchy_level": 40,
        "is_system": True,
        "is_active": True,
    },
    {
        "code": "catalog_manager",
        "name": "Archive & Merchandising Curator",
        "description": "Curates garment pieces, size variants, inventory stock levels, colours, materials, and search taxonomy.",
        "actor_type": "admin",
        "hierarchy_level": 50,
        "is_system": True,
        "is_active": True,
    },
    {
        "code": "service_account",
        "name": "AI Orchestrator Service Account",
        "description": "Scoped multi-agent service identity further constrained by per-endpoint whitelists in agent_permissions.",
        "actor_type": "agent",
        "hierarchy_level": 60,
        "is_system": True,
        "is_active": True,
    },
    {
        "code": "manager",
        "name": "Boutique Store Manager",
        "description": "Oversees boutique operations, inventory, merchandising, fulfillment scheduling, analytics, and Tier 2/3 return approvals.",
        "actor_type": "admin",
        "hierarchy_level": 70,
        "is_system": True,
        "is_active": True,
    },
    {
        "code": "finance_admin",
        "name": "Finance & Compliance Controller",
        "description": "Governs GST/financial analytics, business policies, audit logs, payout execution, and Tier 3 dual-approval refunds.",
        "actor_type": "admin",
        "hierarchy_level": 80,
        "is_system": True,
        "is_active": True,
    },
    {
        "code": "super_admin",
        "name": "Maison Executive Administrator",
        "description": "Full executive governance across RBAC role assignments, staff accounts, policies, catalog, orders, refunds, and audit logs.",
        "actor_type": "admin",
        "hierarchy_level": 100,
        "is_system": True,
        "is_active": True,
    },
]

PERMISSIONS: List[Dict[str, Any]] = [
    {"code": "catalog:read", "resource": "catalog", "action": "read", "description": "Browse products, categories, variants, and recommendations."},
    {"code": "catalog:write", "resource": "catalog", "action": "write", "description": "Create, update, or discontinue products and size variants."},
    {"code": "catalog:manage_taxonomy", "resource": "catalog", "action": "manage_taxonomy", "description": "Manage departments, categories, colours, materials, and search synonyms."},
    {"code": "inventory:read", "resource": "inventory", "action": "read", "description": "Inspect vault stock availability and low-stock alerts."},
    {"code": "inventory:write", "resource": "inventory", "action": "write", "description": "Adjust, reserve, restock, and synchronize garment inventory."},
    {"code": "cart:manage", "resource": "cart", "action": "manage", "description": "Manage personal shopping bag items and promotional codes."},
    {"code": "reviews:write", "resource": "reviews", "action": "write", "description": "Submit verified garment fit and quality reviews."},
    {"code": "orders:create", "resource": "orders", "action": "create", "description": "Create inventory holds, orders, and initiate payment settlement."},
    {"code": "orders:read_own", "resource": "orders", "action": "read_own", "description": "View own orders, GST tax invoices, and courier tracking."},
    {"code": "orders:read_all", "resource": "orders", "action": "read_all", "description": "Inspect all client orders, invoices, and shipment records."},
    {"code": "orders:cancel_own", "resource": "orders", "action": "cancel_own", "description": "Cancel own eligible pre-dispatch orders."},
    {"code": "orders:manage_fulfillment", "resource": "orders", "action": "manage_fulfillment", "description": "Schedule white-glove courier pickups and shipments."},
    {"code": "orders:analytics", "resource": "orders", "action": "analytics", "description": "Access GMV, revenue, and order status telemetry."},
    {"code": "customers:read_own", "resource": "customers", "action": "read_own", "description": "Read own client profile, saved addresses, and preferences."},
    {"code": "customers:write_own", "resource": "customers", "action": "write_own", "description": "Update own client profile and delivery addresses."},
    {"code": "customers:read_all", "resource": "customers", "action": "read_all", "description": "Inspect client profiles for concierge support and governance."},
    {"code": "customers:analytics", "resource": "customers", "action": "analytics", "description": "Access client retention and repeat-buyer analytics."},
    {"code": "returns:create", "resource": "returns", "action": "create", "description": "Initiate garment return requests on eligible delivered orders."},
    {"code": "returns:read_own", "resource": "returns", "action": "read_own", "description": "Track own return QC status and refund progress."},
    {"code": "returns:read_all", "resource": "returns", "action": "read_all", "description": "Inspect all return requests and pending refund queues."},
    {"code": "refunds:approve_tier2", "resource": "refunds", "action": "approve_tier2", "description": "Approve Tier 2 operational returns (Store Manager authority)."},
    {"code": "refunds:approve_tier3", "resource": "refunds", "action": "approve_tier3", "description": "Co-approve high-value Tier 3 returns under dual-control governance."},
    {"code": "refunds:process", "resource": "refunds", "action": "process", "description": "Execute approved refund payouts to original settlement channels."},
    {"code": "support:create_own", "resource": "support", "action": "create_own", "description": "Escalate order or styling inquiries to Maison concierge."},
    {"code": "support:read_all", "resource": "support", "action": "read_all", "description": "View all client support escalations and SLA queues."},
    {"code": "support:resolve", "resource": "support", "action": "resolve", "description": "Acknowledge and resolve support tickets."},
    {"code": "config:read", "resource": "config", "action": "read", "description": "Read Maison policies, GST rules, shipping zones, and payment ceilings."},
    {"code": "config:write", "resource": "config", "action": "write", "description": "Modify Maison business configuration and operational thresholds."},
    {"code": "audit:read", "resource": "audit", "action": "read", "description": "Inspect immutable compliance and security audit logs."},
    {"code": "audit:write", "resource": "audit", "action": "write", "description": "Record administrative compliance audit entries."},
    {"code": "users:read", "resource": "users", "action": "read", "description": "View staff directory, client accounts, and RBAC permission matrix."},
    {"code": "users:manage_roles", "resource": "users", "action": "manage_roles", "description": "Provision staff accounts, assign RBAC roles, and suspend/reactivate users."},
    {"code": "agents:trace_read", "resource": "agents", "action": "trace_read", "description": "Inspect internal shopping-assistant traces (tool calls, checks, errors) for audit and debugging."},
]

_ALL_PERMISSION_CODES: List[str] = [p["code"] for p in PERMISSIONS]

ROLE_PERMISSION_MAP: Dict[str, List[str]] = {
    "customer": [
        "catalog:read",
        "cart:manage",
        "reviews:write",
        "orders:create",
        "orders:read_own",
        "orders:cancel_own",
        "customers:read_own",
        "customers:write_own",
        "returns:create",
        "returns:read_own",
        "support:create_own",
        "config:read",
    ],
    "support_agent": [
        "catalog:read",
        "inventory:read",
        "orders:read_all",
        "customers:read_all",
        "returns:read_all",
        "support:read_all",
        "support:resolve",
        "config:read",
    ],
    "catalog_manager": [
        "catalog:read",
        "catalog:write",
        "catalog:manage_taxonomy",
        "inventory:read",
        "inventory:write",
        "orders:analytics",
        "config:read",
    ],
    "manager": [
        "catalog:read",
        "catalog:write",
        "catalog:manage_taxonomy",
        "inventory:read",
        "inventory:write",
        "orders:read_all",
        "orders:manage_fulfillment",
        "orders:analytics",
        "customers:read_all",
        "customers:analytics",
        "returns:read_all",
        "refunds:approve_tier2",
        "refunds:approve_tier3",
        "refunds:process",
        "support:read_all",
        "support:resolve",
        "config:read",
        "config:write",
        "audit:read",
        "users:read",
        "agents:trace_read",
    ],
    "finance_admin": [
        "catalog:read",
        "inventory:read",
        "orders:read_all",
        "orders:analytics",
        "customers:read_all",
        "customers:analytics",
        "returns:read_all",
        "refunds:approve_tier3",
        "refunds:process",
        "support:read_all",
        "config:read",
        "config:write",
        "audit:read",
        "audit:write",
        "users:read",
    ],
    "super_admin": list(_ALL_PERMISSION_CODES),
    "service_account": [
        "catalog:read",
        "inventory:read",
        "inventory:write",
        "orders:read_all",
        "orders:manage_fulfillment",
        "orders:analytics",
        "customers:read_all",
        "customers:analytics",
        "returns:read_all",
        "refunds:process",
        "config:read",
        "config:write",
        "audit:read",
        "audit:write",
    ],
}

# (model, natural key used to detect existing rows, rows) — insertion order respects FKs.
_REGISTRY: List[tuple] = [
    (Department, "code", DEPARTMENTS),
    (Category, "category_id", CATEGORIES),
    (Color, "name", COLORS),
    (Material, "name", MATERIALS),
    (Occasion, "code", OCCASIONS),
    (Palette, "code", PALETTES),
    (SearchSynonym, "term", SYNONYMS),
    (OrderStatus, "code", ORDER_STATUSES),
    (RefundStatus, "code", REFUND_STATUSES),
    (ReturnReason, "code", RETURN_REASONS),
    (Role, "code", ROLES),
    (Permission, "code", PERMISSIONS),
]


def _insert_missing(session: Session, model: Type, key: str, rows: List[Dict[str, Any]]) -> int:
    existing = set(session.scalars(select(getattr(model, key))).all())
    missing = [row for row in rows if row[key] not in existing]
    session.add_all(model(**row) for row in missing)
    session.flush()
    return len(missing)


def _insert_missing_role_permissions(session: Session) -> int:
    existing_pairs: set[Tuple[str, str]] = {
        (r, p)
        for r, p in session.execute(select(RolePermission.role_code, RolePermission.permission_code)).all()
    }
    to_add: List[RolePermission] = []
    for role_code, perm_codes in ROLE_PERMISSION_MAP.items():
        for perm_code in perm_codes:
            if (role_code, perm_code) not in existing_pairs:
                to_add.append(RolePermission(role_code=role_code, permission_code=perm_code))
    if to_add:
        session.add_all(to_add)
        session.flush()
    return len(to_add)


# Least-privilege grant for the conversational stylist: read the catalogue and
# read/write only its own session profile. Cart, order and refund actions stay
# with their own agents. Mirrored client-side in agents/gateway.py (defence in
# depth); a test asserts the two lists are identical.
STYLIST_AGENT_PERMISSION: Dict[str, Any] = {
    "agent_type": "stylist_agent",
    "service_account": "svc-stylist",
    "resource_type": "catalog",
    "action": "read",
    "allowed_endpoints": [
        "/api/catalog/attributes",
        "/api/catalog/search",
        "/api/products/{id}",
        "/api/products/{id}/recommendations",
        "/api/agents/sessions/{id}/profile",
    ],
    "customer_scoped": True,
}

# The shopping assistant (LLM agent runtime): read-only, and customer-scoped — it can
# read a shopper's orders, shipments and returns only while acting for that shopper.
# Mirrored client-side in agents/gateway.py; a test asserts the two stay identical.
ASSISTANT_AGENT_PERMISSION: Dict[str, Any] = {
    "agent_type": "shopping_assistant",
    "service_account": "svc-assistant",
    "resource_type": "storefront",
    "action": "read",
    "allowed_endpoints": [
        "/api/catalog/attributes",
        "/api/catalog/search",
        "/api/products/{id}",
        "/api/products/{id}/recommendations",
        "/api/config/policies",
        "/api/orders",
        "/api/orders/{id}",
        "/api/shipments/{id}",
        "/api/returns/{id}",
        "/api/agents/sessions/{id}/profile",
    ],
    "customer_scoped": True,
}

AGENT_PERMISSIONS: List[Dict[str, Any]] = [STYLIST_AGENT_PERMISSION, ASSISTANT_AGENT_PERMISSION]


def _insert_missing_agent_permissions(session: Session) -> int:
    existing = set(session.scalars(select(AgentPermission.service_account)).all())
    missing = [p for p in AGENT_PERMISSIONS if p["service_account"] not in existing]
    session.add_all(AgentPermission(**p) for p in missing)
    session.flush()
    return len(missing)


def ensure_reference_data(
    session: Session,
    *,
    tables: Optional[Iterable[str]] = None,
    synonym_dimensions: Optional[Iterable[str]] = None,
) -> Dict[str, int]:
    """Insert any missing reference rows. Returns {table: rows_inserted}.

    With no arguments (seed / fresh database) everything is ensured. Migrations
    pass ``tables`` (and ``synonym_dimensions``) to stay frozen at their own
    revision: they must never write to tables or CHECK values that a *later*
    revision introduces, or replaying an old database forward would fail.
    """
    wanted = set(tables) if tables is not None else None
    dims = set(synonym_dimensions) if synonym_dimensions is not None else None

    def included(table: str) -> bool:
        return wanted is None or table in wanted

    counts: Dict[str, int] = {}
    for model, key, rows in _REGISTRY:
        if not included(model.__tablename__):
            continue
        if model is SearchSynonym and dims is not None:
            rows = [r for r in rows if r["dimension"] in dims]
        counts[model.__tablename__] = _insert_missing(session, model, key, rows)
    if included(RolePermission.__tablename__):
        counts[RolePermission.__tablename__] = _insert_missing_role_permissions(session)
    if included(AgentPermission.__tablename__):
        counts[AgentPermission.__tablename__] = _insert_missing_agent_permissions(session)
    return counts
