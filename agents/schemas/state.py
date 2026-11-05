from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    CATALOG = "catalog_agent"
    CART = "cart_agent"
    ORDER = "order_agent"
    FULFILLMENT = "fulfillment_agent"
    SUPPORT = "support_agent"
    RETURNS = "returns_agent"
    INVENTORY = "inventory_agent"
    ANALYTICS = "analytics_agent"
    CONFIG = "config_agent"
    STYLIST = "stylist_agent"
    ASSISTANT = "shopping_assistant"


class ToolRiskLevel(str, Enum):
    READ_ONLY = "read_only"
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    FINANCIAL = "financial"


AGENT_SERVICE_ACCOUNT_MAP: Dict[str, str] = {
    AgentRole.CATALOG.value: "svc-catalog",
    AgentRole.CART.value: "svc-cart",
    AgentRole.ORDER.value: "svc-order",
    AgentRole.FULFILLMENT.value: "svc-fulfillment",
    AgentRole.SUPPORT.value: "svc-support",
    AgentRole.RETURNS.value: "svc-returns",
    AgentRole.INVENTORY.value: "svc-inventory",
    AgentRole.ANALYTICS.value: "svc-analytics",
    AgentRole.CONFIG.value: "svc-config",
    AgentRole.STYLIST.value: "svc-stylist",
    AgentRole.ASSISTANT.value: "svc-assistant",
}


class ToolCallTrace(BaseModel):
    agent_name: str
    service_account: str
    tool_name: str
    http_method: str
    endpoint: str
    risk_level: str = ToolRiskLevel.READ_ONLY.value
    status_code: int
    latency_ms: float
    allowed_by_gate: bool = True
    error: Optional[str] = None
    summary: Dict[str, Any] = Field(default_factory=dict)


class ReActStep(BaseModel):
    step_number: int
    layer: str  # perception | reasoning | action | reflection
    thought: str
    planned_action: Optional[str] = None
    observation: Optional[str] = None
    reflection: Optional[str] = None


class MemorySnapshot(BaseModel):
    namespace: str = "CUS-001:SES-1001"
    short_term_turns: int = 0
    episodic_events: List[str] = Field(default_factory=list)
    rag_sources: List[str] = Field(default_factory=list)


class AgentRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str = "SES-1001"
    customer_id: Optional[str] = "CUS-001"
    actor_role: str = "customer"  # customer | manager | finance_admin | super_admin
    preferred_agent: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    request_key: Optional[str] = None


class AgentResponse(BaseModel):
    trace_id: str
    session_id: str
    routed_agent: str
    service_account: str
    status: str  # answer | action_completed | pending_approval | blocked_prompt_injection | blocked_unauthorized | clarify_missing_info | escalated
    reply: str
    data: Dict[str, Any] = Field(default_factory=dict)
    tool_traces: List[ToolCallTrace] = Field(default_factory=list)
    policy_citations: List[str] = Field(default_factory=list)
    active_patterns: List[str] = Field(default_factory=list)
    react_steps: List[ReActStep] = Field(default_factory=list)
    memory: MemorySnapshot = Field(default_factory=MemorySnapshot)
    steps_taken: int = 0
    step_budget_max: int = 10
    reflection_verified: bool = True


class AgentGraphState(BaseModel):
    trace_id: str
    request: AgentRequest
    routed_agent: str = AgentRole.CATALOG.value
    service_account: str = "svc-catalog"
    intent: str = "general"
    extracted_entities: Dict[str, Any] = Field(default_factory=dict)
    blocked_reason: Optional[str] = None
    status: str = "answer"
    reply: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)
    tool_traces: List[ToolCallTrace] = Field(default_factory=list)
    policy_citations: List[str] = Field(default_factory=list)
    active_patterns: List[str] = Field(default_factory=list)
    react_steps: List[ReActStep] = Field(default_factory=list)
    memory: MemorySnapshot = Field(default_factory=MemorySnapshot)
    steps_taken: int = 0
    step_budget_max: int = 10
    reflection_verified: bool = True
