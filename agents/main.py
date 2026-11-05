from typing import Any, Callable, Dict, List, Optional
import uuid

from .client import PlatformApiClient
from .gateway import (
    AGENT_ENDPOINT_WHITELIST,
    AGENT_VALUE_CEILINGS_INR,
    check_prompt_injection,
    classify_endpoint_risk,
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
    MemorySnapshot,
    ReActStep,
)

SESSION_MEMORY_STORE: Dict[str, Dict[str, Any]] = {}


def _new_trace_id() -> str:
    return f"TRC-{uuid.uuid4().int % 900000 + 100000:06d}"


def classify_agent_role(req: AgentRequest) -> str:
    if req.preferred_agent and req.preferred_agent in NODE_DISPATCH:
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
    """
    4-Layer Agentic Orchestrator (Perception -> Reasoning/Planning -> Tool Action -> Reflection)
    calling shared /api/* endpoints over HTTP with Step Budget & Tool Hierarchy Guardrails.
    """

    def __init__(self, client: Optional[PlatformApiClient] = None, max_steps: int = 10) -> None:
        self.client = client or PlatformApiClient()
        self.max_steps = max_steps

    def invoke(self, req: AgentRequest) -> AgentResponse:
        trace_id = _new_trace_id()
        namespace = f"{req.customer_id or 'ANON'}:{req.session_id}"
        mem_bucket = SESSION_MEMORY_STORE.setdefault(
            namespace,
            {"turns": 0, "episodic_events": []},
        )
        mem_bucket["turns"] = int(mem_bucket["turns"]) + 1

        state = AgentGraphState(
            trace_id=trace_id,
            request=req,
            step_budget_max=self.max_steps,
            active_patterns=[
                "tool_use",
                "planning",
                "react",
                "reflection",
                "multi_agent",
                "step_budget",
                "tool_hierarchy",
            ],
            memory=MemorySnapshot(
                namespace=namespace,
                short_term_turns=mem_bucket["turns"],
                episodic_events=list(mem_bucket["episodic_events"][-5:]),
            ),
        )

        # Layer 1 & 2: Perception & Input Guardrail
        state.steps_taken += 1
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
            state.react_steps.append(
                ReActStep(
                    step_number=state.steps_taken,
                    layer="perception",
                    thought=f"Observed prompt injection pattern '{injection_code}'.",
                    planned_action="Halt execution at gateway guardrail.",
                    observation="Blocked before any tool or LLM execution.",
                    reflection="Safety invariant preserved.",
                )
            )
            return self._finalize(state)

        state.react_steps.append(
            ReActStep(
                step_number=state.steps_taken,
                layer="perception",
                thought=f"Perceived input from actor '{req.customer_id}' ({req.actor_role}) in session '{req.session_id}'.",
                observation=f"Short-term memory turns={mem_bucket['turns']}.",
            )
        )

        # Layer 1: Reasoning & Supervisor Routing
        state.steps_taken += 1
        role = classify_agent_role(req)
        state.routed_agent = role
        state.service_account = AGENT_SERVICE_ACCOUNT_MAP[role]
        state.react_steps.append(
            ReActStep(
                step_number=state.steps_taken,
                layer="reasoning",
                thought=f"Supervisor analyzed intent and selected specialist '{role}' ({state.service_account}).",
                planned_action=f"Delegate to {role} with whitelisted /api/* tools.",
            )
        )

        # Step Budget Circuit Breaker Check
        if state.steps_taken >= state.step_budget_max:
            state.status = "escalated"
            state.reply = "Max step budget reached. Human review needed."
            return self._finalize(state)

        # Layer 4: Specialist Agent Tool Execution
        handler = NODE_DISPATCH[role]
        state = handler(state, self.client)
        state.steps_taken += max(1, len(state.tool_traces))

        tool_summary = (
            ", ".join(
                f"{t.tool_name} ({t.http_method} {t.endpoint} [{t.risk_level}] -> {t.status_code})"
                for t in state.tool_traces
            )
            or "No external HTTP call required"
        )
        state.react_steps.append(
            ReActStep(
                step_number=state.steps_taken,
                layer="action",
                thought=f"Executed {len(state.tool_traces)} scoped HTTP tool call(s) via ToolPolicyGate.",
                planned_action=tool_summary,
                observation=f"Agent status='{state.status}', citations={state.policy_citations}",
            )
        )

        # Layer 3 & Reflection: Self-Evaluation & Grounding Check
        state.steps_taken += 1
        rag_sources = [f"{t.http_method} {t.endpoint}" for t in state.tool_traces] + list(state.policy_citations)
        state.memory.rag_sources = list(dict.fromkeys(rag_sources))
        event_entry = f"[{trace_id}] {role} -> {state.status}"
        mem_bucket["episodic_events"].append(event_entry)
        state.memory.episodic_events = list(mem_bucket["episodic_events"][-5:])

        state.reflection_verified = all(t.allowed_by_gate for t in state.tool_traces)
        state.react_steps.append(
            ReActStep(
                step_number=state.steps_taken,
                layer="reflection",
                thought="Evaluated response for grounded database facts, PII scrubbing, and policy citations.",
                reflection=(
                    f"Verified={state.reflection_verified}; "
                    f"Grounded in {len(state.memory.rag_sources)} live source(s); "
                    f"Step budget used: {state.steps_taken}/{state.step_budget_max}."
                ),
            )
        )

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
            active_patterns=state.active_patterns,
            react_steps=state.react_steps,
            memory=state.memory,
            steps_taken=state.steps_taken,
            step_budget_max=state.step_budget_max,
            reflection_verified=state.reflection_verified,
        )


AGENT_PERSONA_LABELS: Dict[str, str] = {
    AgentRole.CATALOG.value: "Stylist",
    AgentRole.CART.value: "Shopping Bag",
    AgentRole.ORDER.value: "Order Desk",
    AgentRole.FULFILLMENT.value: "Shipping Desk",
    AgentRole.SUPPORT.value: "Concierge",
    AgentRole.RETURNS.value: "Returns",
    AgentRole.INVENTORY.value: "Stock Desk",
    AgentRole.ANALYTICS.value: "Insights",
    AgentRole.CONFIG.value: "Store Rules",
    AgentRole.STYLIST.value: "Personal Stylist",
    AgentRole.ASSISTANT.value: "Noir Concierge",
}


def get_agent_registry_metadata() -> List[Dict[str, Any]]:
    registry: List[Dict[str, Any]] = []
    for role in AgentRole:
        role_val = role.value
        endpoints = AGENT_ENDPOINT_WHITELIST.get(role_val, [])
        registry.append(
            {
                "agent_name": role_val,
                "persona": AGENT_PERSONA_LABELS.get(role_val, "Concierge"),
                "service_account": AGENT_SERVICE_ACCOUNT_MAP[role_val],
                "prompt_version": PROMPT_VERSION,
                "system_prompt": get_agent_prompt(role_val),
                "allowed_endpoints": [f"{m} {p}" for m, p in endpoints],
                "tool_risk_profile": [
                    {"endpoint": f"{m} {p}", "risk_level": classify_endpoint_risk(m, p)}
                    for m, p in endpoints
                ],
                "value_ceiling_inr": AGENT_VALUE_CEILINGS_INR.get(role_val),
                "step_budget_max": 10,
                "architecture_layers": [
                    "Layer 1: Reasoning (LLM Brain)",
                    "Layer 2: Orchestration (ReAct & Step Budget)",
                    "Layer 3: Memory & Agentic RAG",
                    "Layer 4: Scoped HTTP Tools",
                ],
            }
        )
    return registry
