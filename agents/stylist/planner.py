"""[3] Planner — ask one question, search, or refine? Deterministic and cheap.

No model call: the decision only depends on how much of the brief is known and
whether the shopper is reacting to products already shown. Keeping it in code
makes behaviour predictable and testable.
"""

import re
from typing import List, Optional

from .contracts import Plan, PlanAction, ProfileUpdate, StyleProfile
from .profile_ops import known_constraints


_WANTS_ALTERNATIVES = re.compile(
    r"\b(something else|anything else|other (?:options|ones|pieces)|others|different (?:ones|options|pieces)"
    r"|alternatives?|show me more|more options)\b",
    re.IGNORECASE,
)


def _opening_question(profile: StyleProfile) -> str:
    who = f" for your {profile.recipient}" if profile.recipient else ""
    return f"Happy to help{who}! What's the occasion, and is there a budget you'd like me to keep to?"


def plan_turn(
    profile: StyleProfile, update: ProfileUpdate, last_shown_ids: Optional[List[str]], message: str = ""
) -> Plan:
    if not known_constraints(profile):
        return Plan(PlanAction.ASK, "no searchable constraint yet", _opening_question(profile))
    wants_alternatives = bool(_WANTS_ALTERNATIVES.search(message))
    if last_shown_ids and not update.reset and (wants_alternatives or not update.is_noop()):
        # Rejections ("not white") are handled precisely by the avoid filter; only an
        # explicit request for alternatives hides last turn's picks.
        return Plan(PlanAction.REFINE, "shopper reacted to earlier suggestions", exclude_previous=wants_alternatives)
    return Plan(PlanAction.SEARCH, "brief has searchable constraints")


def follow_up_question(profile: StyleProfile) -> str:
    """The single most useful thing still unknown about the brief."""
    if profile.budget_max_inr is None:
        return "Is there a budget you'd like me to stay within?"
    if not (profile.colors or profile.palettes):
        return "Any colours you love — or would rather avoid?"
    if not profile.sizes:
        return "Which size should I check availability for?"
    return "Would you like something more festive, or more understated?"
