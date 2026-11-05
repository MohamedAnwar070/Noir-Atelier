"""Persistence and validation for the stylist's living style profile.

Storage: agent_sessions.state_snapshot["style_profile"] (Postgres). This module is
the ProfileStore's server side; a Redis cache can sit in front of it later
without changing the API.

Rules
  * Every catalogue value in the profile must exist in the live catalogue with at
    least one product — otherwise 422 with the allowed values, so the stylist can
    correct itself.
  * Writes: the stylist agent (on behalf of a shopper). Reads: the agent, the
    owning shopper, staff. Delete: the owning shopper or the agent.
  * Every write is audited with the profile before/after and the turn trace.
"""

from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from ..auth import ActorContext
from ..models import AgentSession
from ..schemas.stylist_schema import CATALOG_FIELDS, ProfileSaveRequest, StyleProfile
from ..utils.exceptions import AppError
from .audit_service import record_audit
from .catalog_attributes_service import get_catalog_attributes

PROFILE_KEY = "style_profile"
TURNS_KEY = "stylist_turns"
# Products shown last turn, so the planner can tell a reaction ("too bright") from a new brief.
SHOWN_KEY = "last_shown_ids"


def allowed_profile_values(db: Session) -> Dict[str, List[str]]:
    """Live, non-empty values per catalogue-backed profile field."""
    attrs = get_catalog_attributes(db)
    return {
        "department": [d["code"] for d in attrs["departments"]],
        "product_types": [t["slug"] for t in attrs["product_types"]],
        "colors": [c["family"] for c in attrs["colors"]],
        "palettes": [p["code"] for p in attrs["palettes"]],
        "materials": [m["family"] for m in attrs["materials"]],
        "sizes": [s["size"] for s in attrs["sizes"]],
        "occasion": [o["code"] for o in attrs["occasions"]],
    }


def validate_profile(db: Session, profile: StyleProfile) -> None:
    allowed = allowed_profile_values(db)
    invalid: Dict[str, List[str]] = {}

    def check(field: str, values: List[str], allowed_key: Optional[str] = None) -> None:
        pool: Set[str] = set(allowed[allowed_key or field])
        bad = sorted(v for v in values if v not in pool)
        if bad:
            invalid[field] = bad

    for field in CATALOG_FIELDS:
        value = getattr(profile, field)
        check(field, value if isinstance(value, list) else ([value] if value else []))
    for field in ("colors", "palettes", "materials", "product_types"):
        check(f"avoid.{field}", getattr(profile.avoid, field), field)
    if profile.budget_min_inr is not None and profile.budget_max_inr is not None:
        if profile.budget_min_inr > profile.budget_max_inr:
            invalid["budget"] = ["budget_min_inr is greater than budget_max_inr"]

    if invalid:
        raise AppError(
            "invalid_profile_values",
            "The style profile uses values that are not in the live catalogue.",
            422,
            details={"invalid": invalid, "allowed": allowed},
        )


def _session(db: Session, session_id: str) -> Optional[AgentSession]:
    return db.get(AgentSession, session_id.strip())


def _authorize(actor: ActorContext, row: Optional[AgentSession], action: str) -> None:
    if actor.actor_type == "agent":
        return  # endpoint access is enforced by agent_permissions (svc-stylist only)
    if actor.actor_type == "customer":
        if action == "write":
            raise AppError("forbidden", "Only the stylist can update a style profile.", 403)
        if row is not None and row.customer_id not in (None, actor.actor_id):
            raise AppError("forbidden", "This style profile belongs to another shopper.", 403)
        return
    if actor.actor_type == "admin" and action == "read":
        return
    raise AppError("forbidden", "Not allowed to access style profiles.", 403)


def _serialize(session_id: str, row: Optional[AgentSession]) -> Dict[str, Any]:
    snapshot = (row.state_snapshot or {}) if row else {}
    profile = StyleProfile.model_validate(snapshot.get(PROFILE_KEY) or {})
    return {
        "session_id": session_id,
        "customer_id": row.customer_id if row else None,
        "profile": profile.model_dump(mode="json"),
        "turns": int(snapshot.get(TURNS_KEY, 0)),
        "last_shown_ids": list(snapshot.get(SHOWN_KEY, [])),
    }


def get_profile(db: Session, actor: ActorContext, session_id: str) -> Dict[str, Any]:
    row = _session(db, session_id)
    _authorize(actor, row, "read")
    return _serialize(session_id, row)


def save_profile(db: Session, actor: ActorContext, session_id: str, req: ProfileSaveRequest) -> Dict[str, Any]:
    row = _session(db, session_id)
    _authorize(actor, row, "write")
    validate_profile(db, req.profile)

    customer_id = actor.on_behalf_of if actor.actor_type == "agent" else None
    if row is None:
        row = AgentSession(session_id=session_id.strip(), customer_id=customer_id, state_snapshot={})
        db.add(row)
    elif customer_id and row.customer_id not in (None, customer_id):
        raise AppError("forbidden", "This session belongs to another shopper.", 403)
    elif customer_id and row.customer_id is None:
        row.customer_id = customer_id

    snapshot = dict(row.state_snapshot or {})
    before = snapshot.get(PROFILE_KEY) or {}
    after = req.profile.model_dump(mode="json")
    snapshot[PROFILE_KEY] = after
    snapshot[TURNS_KEY] = int(snapshot.get(TURNS_KEY, 0)) + 1
    if req.turn is not None:
        snapshot[SHOWN_KEY] = list(req.turn.product_ids_shown)
    row.state_snapshot = snapshot  # reassign so the JSON column is marked dirty

    record_audit(
        db,
        actor,
        "agent_session",
        row.session_id,
        "stylist_turn",
        {"before": before, "after": after, "turn": req.turn.model_dump(mode="json") if req.turn else None},
        "conversational_stylist",
    )
    db.commit()
    return _serialize(row.session_id, row)


def clear_profile(db: Session, actor: ActorContext, session_id: str) -> Dict[str, Any]:
    row = _session(db, session_id)
    if actor.actor_type not in ("agent", "customer"):
        raise AppError("forbidden", "Not allowed to clear style profiles.", 403)
    if actor.actor_type == "customer" and row is not None and row.customer_id not in (None, actor.actor_id):
        raise AppError("forbidden", "This style profile belongs to another shopper.", 403)
    if row is not None:
        snapshot = dict(row.state_snapshot or {})
        snapshot.pop(PROFILE_KEY, None)
        snapshot.pop(TURNS_KEY, None)
        snapshot.pop(SHOWN_KEY, None)
        row.state_snapshot = snapshot
        record_audit(db, actor, "agent_session", row.session_id, "stylist_profile_cleared", {}, "shopper_privacy_request")
        db.commit()
    return _serialize(session_id, row)
