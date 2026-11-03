from typing import Any, Callable, Dict, List, Optional
import uuid

from .client import PlatformApiClient
from .gateway import (
    AGENT_ENDPOINT_WHITELIST,
    AGENT_VALUE_CEILINGS_INR,
    check_prompt_injection,
    scrub_pii,
)
from .nodes import (
    run_analytics_node,
    run_cart_node,
    run_catalog_node,
    run_config_node,
    run_fulfillment_node,
    run_inventory_node,
    run_order_node,
    run_returns_node,
    run_support_node,
)
from .prompts import PROMPT_VERSION, get_agent_prompt
from .schemas.state import (
    AGENT_SERVICE_ACCOUNT_MAP,
    AgentGraphState,
    AgentRequest,
    AgentResponse,
    AgentRole,
)


def _new_trace_id() -> str:
    return f"TRC-{uuid.uuid4().int % 900000 + 100000:06d}"


def classify_agent_role(req: AgentRequest) -> str:
    if req.preferred_agent and req.preferred_agent in AGENT_SERVICE_ACCOUNT_MAP:
        return req.preferred_agent

    msg = req.message.lower()

    if any(k in msg for k in ("audit log", "business_config", "return policy", "gst slab", "shipping policy", "policy rule", "policies")):
        return AgentRole.CONFIG.value

    if any(k in msg for k in ("analytics", "gmv", "retention rate", "average order value", "revenue report")):
        return AgentRole.ANALYTICS.value

    if any(k in msg for k in ("inventory list", "low stock", "discontinue", "adjust stock", "update stock", "update inventory")):
        return AgentRole.INVENTORY.value

    if any(k in msg for k in ("escalate", "human agent", "concierge ticket", "speak to manager", "exchange", "complaint", "grievance")):
        return AgentRole.SUPPORT.value

    if any(k in msg for k in ("return", "refund", "ret-", "rfd-", "defective", "damaged", "security tag", "qc")):
        return AgentRole.RETURNS.value

    if any(k in msg for k in ("shipment", "shp-", "tracking", "courier", "schedule pickup", "dispatch", "reserve inventory")):
        return AgentRole.FULFILLMENT.value

    if any(k in msg for k in ("cancel order", "place order", "checkout", "order status", "ord-", "initiate payment", "buy ", "purchase ")):
        return AgentRole.ORDER.value

    if any(k in msg for k in ("cart", "shopping bag", "add to bag", "add to cart", "coupon", "atelier10", "summer20")):
        return AgentRole.CART.value

    return AgentRole.CATALOG.value


NODE_DISPATCH: Dict[str, Callable[[AgentGraphState, PlatformApiClient], AgentGraphState]] = {
    AgentRole.CATALOG.value: run_catalog_node,
    AgentRole.CART.value: run_cart_node,
    AgentRole.ORDER.value: run_order_node,
    AgentRole.FULFILLMENT.value: run_fulfillment_node,
    AgentRole.SUPPORT.value: run_support_node,
    AgentRole.RETURNS.value: run_returns_node,
    AgentRole.INVENTORY.value: run_inventory_node,
    AgentRole.ANALYTICS.value: run_analytics_node,
    AgentRole.CONFIG.value: run_config_node,
}


class NoirAtelierMultiAgentOrchestrator:
    """9-Agent State Machine Orchestrator calling shared /api/* endpoints over HTTP."""

    def __init__(self, client: Optional[PlatformApiClient] = None) -> None:
        self.client = client or PlatformApiClient()

    def invoke(self, req: AgentRequest) -> AgentResponse:
        trace_id = _new_trace_id()
        state = AgentGraphState(trace_id=trace_id, request=req)

        # Step 1: Input Guardrail Node
        injection_code = check_prompt_injection(req.message)
        if injection_code is not None:
            state.blocked_reason = injection_code
            state.status = "blocked_prompt_injection"
            state.routed_agent = "gateway_guardrail"
            state.service_account = "none"
            state.reply = (
                "Your request was blocked by the Noir Atelier security gateway due to an "
                f"unpermitted instruction override attempt ({injection_code})."
            )
            return self._finalize(state)

        # Step 2: Supervisor Router Node
        role = classify_agent_role(req)
        state.routed_agent = role
        state.service_account = AGENT_SERVICE_ACCOUNT_MAP[role]

        # Step 3: Specialist Agent Node Execution
        handler = NODE_DISPATCH[role]
        state = handler(state, self.client)

        # Step 4: Output Synthesizer & PII Scrubber
        return self._finalize(state)

    @staticmethod
    def _finalize(state: AgentGraphState) -> AgentResponse:
        return AgentResponse(
            trace_id=state.trace_id,
            session_id=state.request.session_id,
            routed_agent=state.routed_agent,
            service_account=state.service_account,
            status=state.status,
            reply=scrub_pii(state.reply),
            data=state.data,
            tool_traces=state.tool_traces,
            policy_citations=list(dict.fromkeys(state.policy_citations)),
        )


def get_agent_registry_metadata() -> List[Dict[str, Any]]:
    registry: List[Dict[str, Any]] = []
    for role in AgentRole:
        role_val = role.value
        registry.append(
            {
                "agent_name": role_val,
                "service_account": AGENT_SERVICE_ACCOUNT_MAP[role_val],
                "prompt_version": PROMPT_VERSION,
                "system_prompt": get_agent_prompt(role_val),
                "allowed_endpoints": [
                    f"{m} {p}" for m, p in AGENT_ENDPOINT_WHITELIST.get(role_val, [])
                ],
                "value_ceiling_inr": AGENT_VALUE_CEILINGS_INR.get(role_val),
            }
        )
    return registry
