import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request

from agents.assistant import AssistantRuntime, ChatContext, ChatReply, ConversationTurn
from agents.client import PlatformApiClient
from agents.llm import build_llm
from agents.main import AGENT_PERSONA_LABELS, NoirAtelierMultiAgentOrchestrator, get_agent_registry_metadata
from agents.schemas.state import AgentRequest, AgentResponse, AgentRole
from agents.stylist import StylistPipeline

from sqlalchemy.orm import Session

from ..auth import ActorContext, require_authenticated, require_permissions, resolve_optional_actor
from ..config import get_settings
from ..database import get_db
from ..schemas.stylist_schema import ProfileSaveRequest
from ..services.agent_trace_service import get_trace, list_traces, save_trace
from ..services.assistant_session_service import append_history, load_history
from ..services.stylist_session_service import clear_profile, get_profile, save_profile

logger = logging.getLogger("noir.api.agents")
router = APIRouter()

_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_SHARED_DEFAULT_SESSION = "SES-1001"  # AgentRequest's default; never let shoppers share it


@router.get("/api/agents/registry")
def api_agents_registry() -> List[Dict[str, Any]]:
    """Public: display names only. Prompts, endpoints and risk profiles are internal."""
    return [{"agent_name": item["agent_name"], "persona": item["persona"]} for item in get_agent_registry_metadata()]


@router.get("/api/admin/agents/registry")
def api_admin_agents_registry(
    _actor: ActorContext = Depends(require_permissions("agents:trace_read")),
) -> List[Dict[str, Any]]:
    return get_agent_registry_metadata()


@router.post("/api/agents/chat", response_model=ChatReply)
def api_agents_chat(
    req: AgentRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_optional_actor),
) -> ChatReply:
    """Shopper chat. Returns ONLY the shopper-facing reply; the internal trace is stored, never returned."""
    from fastapi.testclient import TestClient

    settings = get_settings()
    client = PlatformApiClient(in_process_client=TestClient(request.app))
    if settings.agent_runtime != "llm":
        return _legacy_chat(req, actor, client)

    session_id = _session_id(req.session_id)
    # Identity comes from authentication only — never from the request body.
    customer_id = actor.actor_id if actor.actor_type == "customer" else None
    ctx = ChatContext(
        trace_id=f"TRC-{uuid.uuid4().hex[:20].upper()}",
        session_id=session_id,
        customer_id=customer_id,
        customer_name=(actor.name or "").split(" ")[0] or None if customer_id else None,
        history=[
            ConversationTurn(t["role"], t["text"], list(t.get("product_ids") or []))
            for t in load_history(db, session_id, customer_id)
            if t.get("role") in ("user", "assistant")
        ],
    )
    runtime = AssistantRuntime(
        client,
        build_llm(),
        persona=AGENT_PERSONA_LABELS[AgentRole.ASSISTANT.value],
        max_tool_calls=settings.agent_max_steps,
        deadline_sec=settings.assistant_turn_deadline_sec,
        effort=settings.assistant_effort,
    )
    result = runtime.handle(req.message, ctx)
    try:
        save_trace(db, result.trace.to_record())
        append_history(db, session_id, customer_id, [vars(t) for t in result.remember])
        db.commit()
    except Exception:  # observability must never cost the shopper their answer
        db.rollback()
        logger.exception("could not persist assistant turn %s", ctx.trace_id)
    return result.reply


def _session_id(raw: Optional[str]) -> str:
    if raw and raw != _SHARED_DEFAULT_SESSION and _SESSION_ID.match(raw):
        return raw
    return f"SES-{uuid.uuid4().hex.upper()}"


def _legacy_chat(req: AgentRequest, actor: ActorContext, client: PlatformApiClient) -> ChatReply:
    """Keyword-routed agents (AGENT_RUNTIME=legacy), mapped to the same shopper-safe shape."""
    if actor.actor_type == "customer" and not req.customer_id:
        req.customer_id = actor.actor_id
    if actor.actor_type == "admin" and req.actor_role == "customer":
        req.actor_role = actor.role
    orchestrator = NoirAtelierMultiAgentOrchestrator(client=client)
    if get_settings().stylist_enabled:
        res = StylistPipeline(client, delegate=orchestrator.invoke, llm=build_llm()).handle(req)
    else:
        res = orchestrator.invoke(req)
    return chat_reply_from_legacy(res)


def chat_reply_from_legacy(res: AgentResponse) -> ChatReply:
    data = res.data or {}
    status = "blocked" if res.status.startswith("blocked") else "unavailable" if res.status == "error" else "answer"
    products = [p for p in (data.get("products") or []) if isinstance(p, dict)][:6]
    return ChatReply(
        reference_id=res.trace_id,
        session_id=res.session_id,
        status=status,
        persona=AGENT_PERSONA_LABELS.get(res.routed_agent, "Concierge"),
        reply=res.reply,
        products=products,
        follow_up_prompts=[str(p) for p in (data.get("follow_up_prompts") or [])][:3],
        action_feedback=data.get("action_feedback") if isinstance(data.get("action_feedback"), dict) else None,
        stylist_mode=data.get("stylist_mode"),
        stylist_notes=[str(n) for n in (data.get("stylist_notes") or [])],
        total_mrp_inr=data.get("total_mrp_inr"),
    )


# --- Internal assistant traces (staff only: agents:trace_read) ---------------------


@router.get("/api/admin/agents/traces")
def api_list_agent_traces(
    session_id: Optional[str] = Query(default=None, max_length=64),
    customer_id: Optional[str] = Query(default=None, max_length=16),
    status: Optional[str] = Query(default=None, max_length=16),
    before: Optional[datetime] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_permissions("agents:trace_read")),
) -> List[Dict[str, Any]]:
    return list_traces(db, session_id=session_id, customer_id=customer_id, status=status, before=before, limit=limit)


@router.get("/api/admin/agents/traces/{trace_id}")
def api_get_agent_trace(
    trace_id: str,
    db: Session = Depends(get_db),
    _actor: ActorContext = Depends(require_permissions("agents:trace_read")),
) -> Dict[str, Any]:
    return get_trace(db, trace_id)


# --- Living style profile (conversational stylist) -----------------------------
# Writes come from the stylist agent (svc-stylist, on behalf of a shopper); the
# shopper can read and erase their own profile.


@router.get("/api/agents/sessions/{session_id}/profile")
def api_get_style_profile(
    session_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return get_profile(db, actor, session_id)


@router.put("/api/agents/sessions/{session_id}/profile")
def api_save_style_profile(
    session_id: str,
    req: ProfileSaveRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return save_profile(db, actor, session_id, req)


@router.delete("/api/agents/sessions/{session_id}/profile")
def api_clear_style_profile(
    session_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_authenticated),
) -> Dict[str, Any]:
    return clear_profile(db, actor, session_id)
