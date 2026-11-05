"""Pure profile operations: applying one turn's update to the living style profile.

    merge(profile, update) -> new profile      (no I/O, deterministic, unit-tested)

Semantics
  * reset            → start a fresh brief, then apply the rest of the update
  * scalar fields    → replaced when the update sets them
  * list fields      → replaced when the update sets them (de-duplicated, order kept)
  * avoid lists      → accumulate across turns, and anything avoided is removed from
                       the matching preference list ("too bright" can't stay wanted)
  * confidence       → per-field values overwrite older ones
"""

from typing import Iterable, List

from .contracts import AvoidList, ProfileUpdate, StyleProfile

_SCALARS = ("occasion", "department", "budget_min_inr", "budget_max_inr", "recipient", "location", "timing")
_LISTS = ("product_types", "colors", "palettes", "materials", "sizes")
_AVOIDABLE = ("colors", "palettes", "materials", "product_types")


def _dedupe(values: Iterable[str]) -> List[str]:
    seen: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def merge(profile: StyleProfile, update: ProfileUpdate) -> StyleProfile:
    data = (StyleProfile() if update.reset else profile).model_dump()

    for name in _SCALARS:
        value = getattr(update, name)
        if value is not None:
            data[name] = value
    for name in _LISTS:
        value = getattr(update, name)
        if value is not None:
            data[name] = _dedupe(value)

    avoid = data["avoid"]
    for name in _AVOIDABLE:
        avoid[name] = _dedupe([*avoid[name], *getattr(update.avoid, name)])
        data[name] = [v for v in data[name] if v not in avoid[name]]

    data["confidence"] = {**data["confidence"], **update.confidence}
    return StyleProfile.model_validate(data)


def known_constraints(profile: StyleProfile) -> List[str]:
    """Which parts of the brief are filled in — drives the planner's 'ask or search' decision."""
    filled = [name for name in ("occasion", "department") if getattr(profile, name)]
    filled += [name for name in _LISTS if getattr(profile, name)]
    if profile.budget_max_inr is not None or profile.budget_min_inr is not None:
        filled.append("budget")
    return filled


__all__ = ["merge", "known_constraints", "AvoidList"]
