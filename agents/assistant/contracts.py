"""Contracts of the shopping assistant.

Two strictly separate shapes:

* ``ChatReply``  what the SHOPPER receives. ``extra="forbid"`` and no trace fields at all,
  so internal details cannot leak through the API by construction.
* ``TurnTrace``  what OPERATORS can inspect (stored in agent_traces): intent, plan note,
  every tool call, the evaluation, errors, usage. Never returned by the chat endpoint.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------- shopper-facing


class ChatReply(BaseModel):
    """The only shape /api/agents/chat ever returns."""

    model_config = ConfigDict(extra="forbid")

    reference_id: str = Field(description="Opaque support reference for this reply")
    session_id: str
    status: Literal["answer", "unavailable", "blocked"] = "answer"
    persona: str
    reply: str
    products: List[Dict[str, Any]] = Field(default_factory=list, description="Product cards, built from catalogue data")
    follow_up_prompts: List[str] = Field(default_factory=list)
    # Presentation extras the storefront already renders (legacy runtime only).
    action_feedback: Optional[Dict[str, Any]] = None
    stylist_mode: Optional[str] = None
    stylist_notes: List[str] = Field(default_factory=list)
    total_mrp_inr: Optional[float] = None


# ---------------------------------------------------------------------------- runtime inputs


@dataclass(frozen=True)
class ConversationTurn:
    role: Literal["user", "assistant"]
    text: str
    product_ids: List[str] = field(default_factory=list)


@dataclass
class ChatContext:
    """Everything the runtime may know about the shopper — set by the server, never by the model."""

    trace_id: str
    session_id: str
    customer_id: Optional[str]  # authenticated shopper, else None (guest)
    customer_name: Optional[str] = None
    history: List[ConversationTurn] = field(default_factory=list)

    @property
    def signed_in(self) -> bool:
        return self.customer_id is not None


# ---------------------------------------------------------------------------- internal trace

TraceStatus = Literal["answered", "fallback", "error", "blocked"]


@dataclass
class ToolCallRecord:
    name: str
    input: Dict[str, Any]
    status: Literal["ok", "error", "denied", "timeout", "budget", "invalid"]
    http_status: Optional[int] = None
    latency_ms: float = 0.0
    summary: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class Evaluation:
    passed: bool = True
    attempts: int = 0
    problems: List[str] = field(default_factory=list)
    template_used: bool = False


@dataclass
class TurnTrace:
    trace_id: str
    session_id: str
    customer_id: Optional[str]
    runtime: Literal["llm", "offline"]
    user_message: str
    model: Optional[str] = None
    status: TraceStatus = "answered"
    intent: Optional[str] = None
    plan_note: Optional[str] = None
    reply: str = ""
    product_ids: List[str] = field(default_factory=list)
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    evaluation: Evaluation = field(default_factory=Evaluation)
    errors: List[str] = field(default_factory=list)
    usage: Dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0

    def to_record(self) -> Dict[str, Any]:
        """Plain dict for persistence (agent_traces row)."""
        return asdict(self)


@dataclass
class TurnResult:
    reply: ChatReply
    trace: TurnTrace
    # Conversation memory to persist for the next turn (text only, no internals).
    remember: List[ConversationTurn] = field(default_factory=list)
