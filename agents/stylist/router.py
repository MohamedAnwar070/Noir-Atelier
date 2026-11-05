"""[1] Router — is this message about shopping, or for another specialist?

Claude (fast tier) classifies when live; the existing keyword classifier is the
fallback, so routing never depends on the model being available.
"""

from typing import Tuple

from ..main import classify_agent_role
from ..schemas.state import AgentRequest, AgentRole
from .contracts import Route
from .llm import LlmError, StructuredLlm
from .prompts import ROUTER_SYSTEM

ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": [r.value for r in Route]},
        "reason": {"type": "string"},
    },
    "required": ["route", "reason"],
    "additionalProperties": False,
}

_ROLE_TO_ROUTE = {
    AgentRole.CATALOG.value: Route.DISCOVERY,
    AgentRole.CART.value: Route.CART,
    AgentRole.ORDER.value: Route.ORDER_STATUS,
    AgentRole.FULFILLMENT.value: Route.ORDER_STATUS,
    AgentRole.RETURNS.value: Route.RETURNS,
}


def keyword_route(req: AgentRequest) -> Route:
    """Deterministic fallback built on the existing multi-agent classifier."""
    return _ROLE_TO_ROUTE.get(classify_agent_role(req), Route.SUPPORT)


def route_message(req: AgentRequest, llm: StructuredLlm | None, safe_message: str) -> Tuple[Route, str, bool]:
    """Return (route, reason, llm_used)."""
    if llm is not None:
        try:
            data = llm.generate_json(
                tier="fast",
                system_blocks=[ROUTER_SYSTEM],
                user=safe_message,
                schema=ROUTE_SCHEMA,
                max_tokens=1024,
                effort="low",
            )
            return Route(data["route"]), str(data.get("reason", ""))[:120], True
        except (LlmError, KeyError, ValueError):
            pass  # fall through to the keyword router
    route = keyword_route(req)
    return route, "keyword classifier", False
