from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request

from agents.client import PlatformApiClient
from agents.main import NoirAtelierMultiAgentOrchestrator, get_agent_registry_metadata
from agents.schemas.state import AgentRequest, AgentResponse

from ..auth import ActorContext, resolve_optional_actor

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
    return orchestrator.invoke(req)
