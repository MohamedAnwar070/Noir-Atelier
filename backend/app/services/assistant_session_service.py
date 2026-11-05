"""Conversation memory for the shopping assistant (agent_sessions.state_snapshot).

Only plain text and shown product ids are kept — no tool details, no traces. A
session belongs to the shopper who first used it while signed in: another shopper's
session is never read or written (a guest session is claimed on first signed-in use).
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models import AgentSession

HISTORY_KEY = "assistant_history"
MAX_STORED_TURNS = 24  # 12 exchanges
MAX_TURN_CHARS = 1500


def _row(db: Session, session_id: str) -> Optional[AgentSession]:
    return db.get(AgentSession, session_id)


def _owned(row: AgentSession, customer_id: Optional[str]) -> bool:
    return row.customer_id is None or row.customer_id == customer_id


def load_history(db: Session, session_id: str, customer_id: Optional[str]) -> List[Dict[str, Any]]:
    row = _row(db, session_id)
    if row is None or not _owned(row, customer_id):
        return []
    return list((row.state_snapshot or {}).get(HISTORY_KEY, []))


def append_history(db: Session, session_id: str, customer_id: Optional[str], turns: List[Dict[str, Any]]) -> bool:
    """Append turns; returns False (and stores nothing) for a session owned by someone else."""
    row = _row(db, session_id)
    if row is None:
        row = AgentSession(session_id=session_id, customer_id=customer_id, state_snapshot={})
        db.add(row)
    elif not _owned(row, customer_id):
        return False
    elif row.customer_id is None and customer_id:
        row.customer_id = customer_id  # a guest session is claimed when its shopper signs in
    snapshot = dict(row.state_snapshot or {})
    history = list(snapshot.get(HISTORY_KEY, []))
    for turn in turns:
        history.append(
            {
                "role": turn["role"],
                "text": str(turn["text"])[:MAX_TURN_CHARS],
                "product_ids": list(turn.get("product_ids") or [])[:6],
            }
        )
    snapshot[HISTORY_KEY] = history[-MAX_STORED_TURNS:]
    row.state_snapshot = snapshot  # reassign so the JSON column is marked dirty
    return True
