import re
from typing import Dict, List, Optional, Tuple

from .schemas.state import AGENT_SERVICE_ACCOUNT_MAP, AgentRole, ToolRiskLevel

INJECTION_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    (
        "ignore_instructions",
        re.compile(
            r"\b(ignore|disregard|override|forget)\b.{0,40}\b(previous|prior|system|all|above)\b.{0,30}\b(instructions?|prompts?|rules?|policies)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "system_prompt_leak",
        re.compile(
            r"\b(reveal|print|show|output|dump)\b.{0,30}\b(system\s+prompt|hidden\s+instructions|secret\s+key|jwt_secret)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "privilege_escalation",
        re.compile(
            r"\b(act\s+as|you\s+are\s+now|switch\s+to|elevate\s+to|pretend\s+to\s+be)\b.{0,30}\b(super_admin|finance_admin|root|developer\s+mode|unrestricted|dan)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "bypass_policy",
        re.compile(
            r"\b(bypass|skip|disable)\b.{0,30}\b(security\s+tag|qc\s+check|approval\s+tier|verification|policy\s+gate)\b",
            re.IGNORECASE,
        ),
    ),
]

CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
AADHAAR_PATTERN = re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")
BEARER_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)


def check_prompt_injection(text: str) -> Optional[str]:
    for reason_code, pattern in INJECTION_PATTERNS:
        if pattern.search(text or ""):
            return reason_code
    return None


def scrub_pii(text: str) -> str:
    if not text:
        return text
    cleaned = CARD_PATTERN.sub("[REDACTED_CARD]", text)
    cleaned = AADHAAR_PATTERN.sub("[REDACTED_ID]", cleaned)
    cleaned = BEARER_PATTERN.sub("Bearer [REDACTED_TOKEN]", cleaned)
    return cleaned


AGENT_ENDPOINT_WHITELIST: Dict[str, List[Tuple[str, str]]] = {
    # Conversational stylist: read-only catalogue + its own session profile.
    # Mirrors the server-side grant in backend/app/reference_data.STYLIST_AGENT_PERMISSION
    # (defence in depth; a test asserts the two stay identical). DELETE is deliberately
    # absent — erasing a profile is the shopper's right, not the agent's.
    AgentRole.STYLIST.value: [
        ("GET", "/api/catalog/attributes"),
        ("GET", "/api/catalog/search"),
        ("GET", "/api/products/{id}"),
        ("GET", "/api/products/{id}/recommendations"),
        ("GET", "/api/agents/sessions/{id}/profile"),
        ("PUT", "/api/agents/sessions/{id}/profile"),
    ],
    AgentRole.CATALOG.value: [
        ("GET", "/api/products/search"),
        ("GET", "/api/products/{id}"),
        ("GET", "/api/products/{id}/recommendations"),
        ("GET", "/api/categories"),
        ("GET", "/api/catalog/meta"),
        ("GET", "/api/catalog/search"),
    ],
    AgentRole.CART.value: [
        ("POST", "/api/cart/add"),
        ("DELETE", "/api/cart/remove/{item_id}"),
        ("GET", "/api/cart"),
        ("POST", "/api/cart/clear"),
        ("POST", "/api/coupons/validate"),
        ("POST", "/api/orders/calculate"),
    ],
    AgentRole.ORDER.value: [
        ("POST", "/api/orders"),
        ("GET", "/api/orders/{id}"),
        ("POST", "/api/orders/{id}/cancel"),
        ("POST", "/api/payments/initiate"),
    ],
    AgentRole.FULFILLMENT.value: [
        ("GET", "/api/shipments/{id}"),
        ("POST", "/api/shipments/schedule"),
        ("POST", "/api/inventory/reserve"),
    ],
    AgentRole.SUPPORT.value: [
        ("GET", "/api/orders/{id}"),
        ("GET", "/api/refunds"),
        ("POST", "/api/returns"),
        ("POST", "/api/support/escalate"),
    ],
    AgentRole.RETURNS.value: [
        ("POST", "/api/returns"),
        ("GET", "/api/returns/{id}"),
        ("POST", "/api/refunds/{id}/approve"),
        ("POST", "/api/refunds/{id}/process"),
        ("POST", "/api/inventory/restock"),
    ],
    AgentRole.INVENTORY.value: [
        ("GET", "/api/inventory/list"),
        ("PUT", "/api/inventory/{id}"),
        ("POST", "/api/products/{id}/discontinue"),
    ],
    AgentRole.ANALYTICS.value: [
        ("GET", "/api/orders/analytics"),
        ("GET", "/api/customers/analytics"),
        ("GET", "/api/products/analytics"),
    ],
    AgentRole.CONFIG.value: [
        ("GET", "/api/config/policies"),
        ("PUT", "/api/admin/config/policies"),
        ("GET", "/api/audit/log"),
    ],
}

AGENT_VALUE_CEILINGS_INR: Dict[str, int] = {
    AgentRole.ORDER.value: 50000,
    AgentRole.RETURNS.value: 5000,
}


def classify_endpoint_risk(method: str, endpoint: str) -> str:
    m = method.upper()
    path = endpoint.lower()
    if m == "GET":
        return ToolRiskLevel.READ_ONLY.value
    if any(k in path for k in ("/orders", "/payments", "/refunds", "/returns")):
        return ToolRiskLevel.FINANCIAL.value
    if m == "DELETE" or "clear" in path or "discontinue" in path:
        return ToolRiskLevel.DELETE.value
    if m in ("PUT", "PATCH"):
        return ToolRiskLevel.MODIFY.value
    return ToolRiskLevel.CREATE.value


def _match_path(pattern: str, actual_path: str) -> bool:
    clean_actual = actual_path.split("?", 1)[0].rstrip("/") or "/"
    regex_str = "^" + re.sub(r"\{[^/]+\}", r"[^/]+", pattern.rstrip("/")) + "/?$"
    return bool(re.match(regex_str, clean_actual))


class ToolPolicyGateError(PermissionError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ToolPolicyGate:
    """Client-side pre-flight policy gate before dispatching HTTP requests to /api/*."""

    @staticmethod
    def verify_call(
        agent_role: str,
        method: str,
        endpoint: str,
        amount_inr: Optional[float] = None,
    ) -> str:
        if agent_role not in AGENT_SERVICE_ACCOUNT_MAP:
            raise ToolPolicyGateError(
                "unknown_agent_role",
                f"Agent role '{agent_role}' is not registered in the agent registry.",
            )

        allowed_list = AGENT_ENDPOINT_WHITELIST.get(agent_role, [])
        method_upper = method.upper()
        matched = any(
            m == method_upper and _match_path(pat, endpoint)
            for m, pat in allowed_list
        )
        if not matched:
            svc = AGENT_SERVICE_ACCOUNT_MAP[agent_role]
            raise ToolPolicyGateError(
                "endpoint_not_whitelisted",
                f"Agent '{agent_role}' ({svc}) is not permitted to call '{method_upper} {endpoint}'.",
            )

        if amount_inr is not None and agent_role == AgentRole.ORDER.value:
            ceiling = AGENT_VALUE_CEILINGS_INR[AgentRole.ORDER.value]
            if amount_inr > ceiling:
                raise ToolPolicyGateError(
                    "order_ceiling_exceeded",
                    f"Order value INR {amount_inr:,.2f} exceeds svc-order autonomous ceiling of INR {ceiling:,.2f}.",
                )

        return AGENT_SERVICE_ACCOUNT_MAP[agent_role]
