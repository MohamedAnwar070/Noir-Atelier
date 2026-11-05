from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request

from agents.client import PlatformApiClient
from agents.main import NoirAtelierMultiAgentOrchestrator, get_agent_registry_metadata
from agents.schemas.state import AgentRequest, AgentResponse
from agents.stylist import StylistPipeline, build_llm

from sqlalchemy.orm import Session

from ..auth import ActorContext, require_authenticated, resolve_optional_actor
from ..config import get_settings
from ..database import get_db
from ..schemas.stylist_schema import ProfileSaveRequest
from ..services.stylist_session_service import clear_profile, get_profile, save_profile

router = APIRouter()


@router.get("/api/agents/registry")
def api_agents_registry() -> List[Dict[str, Any]]:
    return get_agent_registry_metadata()


@router.post("/api/agents/chat", response_model=AgentResponse)
def api_agents_chat(
    req: AgentRequest,
    request: Request,
    actor: ActorContext = Depends(resolve_optional_actor),
) -> AgentResponse:
    from fastapi.testclient import TestClient

    if actor.actor_type == "customer" and not req.customer_id:
        req.customer_id = actor.actor_id
    if actor.actor_type == "admin" and req.actor_role == "customer":
        req.actor_role = actor.role

    in_proc = TestClient(request.app)
    client = PlatformApiClient(in_process_client=in_proc)
    orchestrator = NoirAtelierMultiAgentOrchestrator(client=client)
    if not get_settings().stylist_enabled:
        return orchestrator.invoke(req)
    # The stylist handles shopping conversations and delegates everything else
    # (cart, orders, returns, support handoff) to the specialist agents.
    return StylistPipeline(client, delegate=orchestrator.invoke, llm=build_llm()).handle(req)


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
