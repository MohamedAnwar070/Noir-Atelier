"""[2] Profile extractor — what does this message change about the shopper's brief?

Live mode: Claude (fast tier) returns JSON whose schema is generated per turn
from the live catalogue, with enums — it cannot name a value that does not exist.
Offline mode (or on any model failure): the search engine's own interpreter
(GET /api/catalog/search?limit=1) maps words → attributes using the same
database vocabulary and synonyms as the storefront search box, plus a few
conversational rules (negation, recipient, timing, location).

Either way the result is filtered to live values before it is used, and the
server validates the merged profile again on save (defence in depth).
"""

import json
import re
from typing import Any, Dict, List, Optional, Set

from .contracts import AvoidList, ProfileUpdate, StyleProfile
from .llm import LlmError, StructuredLlm
from .prompts import EXTRACTOR_SYSTEM, catalogue_block

_LIST_FIELDS = ("product_types", "colors", "palettes", "materials", "sizes")
_AVOID_FIELDS = ("colors", "palettes", "materials", "product_types")

# dimension name in the search interpretation → profile field
_DIMENSION_FIELD = {
    "department": "department",
    "product_type": "product_types",
    "color": "colors",
    "material": "materials",
    "occasion": "occasion",
    "palette": "palettes",
}

_NEGATORS = {"no", "not", "without", "avoid", "too", "except", "hate", "dislike", "nothing", "never"}
_RESET = re.compile(r"\b(forget (that|it|this)|start over|start again|something else entirely|new search)\b", re.I)
_RECIPIENT = re.compile(r"\bfor (?:my|our) ([a-z]+)", re.I)
_TIMING = re.compile(
    r"\b(next (?:week|month|year)|this (?:weekend|week|month)|tomorrow|tonight|in \d+ (?:days|weeks|months))\b", re.I
)
_LOCATION = re.compile(r"\bin ([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)?)")
_FEMALE = {"sister", "mother", "mom", "mum", "wife", "daughter", "aunt", "grandmother", "girlfriend", "fiancee"}
_MALE = {"brother", "father", "dad", "husband", "son", "uncle", "grandfather", "boyfriend", "fiance"}
_CHILD = {"kid", "kids", "child", "baby", "nephew", "niece", "toddler"}


def allowed_values(attributes: Dict[str, Any]) -> Dict[str, List[str]]:
    """Live, non-empty values per profile field (only these may enter the profile)."""
    return {
        "department": [d["code"] for d in attributes.get("departments", [])],
        "product_types": [t["slug"] for t in attributes.get("product_types", [])],
        "colors": [c["family"] for c in attributes.get("colors", [])],
        "palettes": [p["code"] for p in attributes.get("palettes", [])],
        "materials": [m["family"] for m in attributes.get("materials", [])],
        "sizes": [s["size"] for s in attributes.get("sizes", [])],
        "occasion": [o["code"] for o in attributes.get("occasions", [])],
    }


# ------------------------------------------------------------------ live (LLM) --


def _enum_array(values: List[str]) -> Dict[str, Any]:
    return {"type": "array", "items": {"type": "string", "enum": values}}


def update_schema(allowed: Dict[str, List[str]]) -> Dict[str, Any]:
    """JSON Schema for this turn: every catalogue field is an enum of LIVE values only."""
    props: Dict[str, Any] = {
        "reset": {"type": "boolean"},
        "budget_min_inr": {"type": "number", "description": "0 if not mentioned"},
        "budget_max_inr": {"type": "number", "description": "0 if not mentioned"},
        "recipient": {"type": "string", "description": "short phrase, empty if not mentioned"},
        "location": {"type": "string", "description": "city or region, empty if not mentioned"},
        "timing": {"type": "string", "description": "e.g. 'next month', empty if not mentioned"},
        "confidence": {
            "type": "object",
            "properties": {k: {"type": "number"} for k in ("occasion", "palettes", "budget_max_inr")},
            "required": ["occasion", "palettes", "budget_max_inr"],
            "additionalProperties": False,
        },
    }
    for single in ("occasion", "department"):
        if allowed[single]:
            props[single] = {"type": "string", "enum": [*allowed[single], "none"]}
    for name in _LIST_FIELDS:
        if allowed[name]:
            props[name] = _enum_array(allowed[name])
    for name in _AVOID_FIELDS:
        if allowed[name]:
            props[f"avoid_{name}"] = _enum_array(allowed[name])
    return {"type": "object", "properties": props, "required": sorted(props), "additionalProperties": False}


def _from_llm_json(data: Dict[str, Any]) -> ProfileUpdate:
    text = lambda key: (data.get(key) or "").strip() or None  # noqa: E731
    number = lambda key: float(data[key]) if data.get(key) else None  # noqa: E731
    single = lambda key: data.get(key) if data.get(key) not in (None, "", "none") else None  # noqa: E731
    confidence = {k: float(v) for k, v in (data.get("confidence") or {}).items() if v}
    return ProfileUpdate(
        reset=bool(data.get("reset")),
        occasion=single("occasion"),
        department=single("department"),
        **{name: (data.get(name) or None) for name in _LIST_FIELDS},
        budget_min_inr=number("budget_min_inr"),
        budget_max_inr=number("budget_max_inr"),
        recipient=text("recipient"),
        location=text("location"),
        timing=text("timing"),
        avoid=AvoidList(**{name: data.get(f"avoid_{name}") or [] for name in _AVOID_FIELDS}),
        confidence={k: min(max(v, 0.0), 1.0) for k, v in confidence.items()},
    )


def extract_with_llm(llm: StructuredLlm, message: str, profile: StyleProfile, attributes: Dict[str, Any]) -> ProfileUpdate:
    allowed = allowed_values(attributes)
    user = json.dumps(
        {"current_profile": profile.model_dump(mode="json"), "shopper_message": message},
        ensure_ascii=False,
    )
    data = llm.generate_json(
        tier="fast",
        system_blocks=[EXTRACTOR_SYSTEM, catalogue_block(attributes)],
        user=user,
        schema=update_schema(allowed),
        max_tokens=2048,
        effort="low",
    )
    return _from_llm_json(data)


# --------------------------------------------------------------- offline rules --


def _negated(message: str, term: str) -> bool:
    lowered = message.lower()
    idx = lowered.find(term.lower())
    if idx < 0:
        return False
    preceding = re.findall(r"[a-z']+", lowered[:idx])[-3:]
    return any(word in _NEGATORS for word in preceding)


def extract_offline(message: str, interpretation: Dict[str, Any], allowed: Dict[str, List[str]]) -> ProfileUpdate:
    """Rule-based extraction on top of the search engine's interpretation of ``message``."""
    fields: Dict[str, Any] = {}
    avoid: Dict[str, List[str]] = {name: [] for name in _AVOID_FIELDS}
    confidence: Dict[str, float] = {}

    for item in interpretation.get("recognized", []):
        field = _DIMENSION_FIELD.get(item.get("dimension"))
        value = item.get("value")
        if not field or value not in allowed.get(field, []):
            continue  # not a live value (e.g. occasion tags awaiting review)
        if _negated(message, item.get("term", "")) and field in _AVOID_FIELDS:
            avoid[field].append(value)
            continue
        if field in _LIST_FIELDS:
            fields.setdefault(field, []).append(value)
        else:
            fields[field] = value
        confidence[field] = 0.9

    if interpretation.get("max_price"):
        fields["budget_max_inr"] = float(interpretation["max_price"])
        confidence["budget_max_inr"] = 0.95
    if interpretation.get("min_price"):
        fields["budget_min_inr"] = float(interpretation["min_price"])

    recipient = _RECIPIENT.search(message)
    if recipient:
        who = recipient.group(1).lower()
        fields["recipient"] = who
        if "department" not in fields:
            inferred = "WOMEN" if who in _FEMALE else "MEN" if who in _MALE else "KIDS" if who in _CHILD else None
            if inferred in allowed["department"]:
                fields["department"] = inferred
                confidence["department"] = 0.6
    timing = _TIMING.search(message)
    if timing:
        fields["timing"] = timing.group(1).lower()
    location = _LOCATION.search(message)
    if location:
        fields["location"] = location.group(1)

    return ProfileUpdate(
        reset=bool(_RESET.search(message)),
        avoid=AvoidList(**avoid),
        confidence=confidence,
        **fields,
    )


# ------------------------------------------------------------------ guard rail --


def keep_live_values(update: ProfileUpdate, allowed: Dict[str, List[str]]) -> ProfileUpdate:
    """Drop any catalogue value that is not live (whatever produced the update)."""
    data = update.model_dump()
    for field in ("occasion", "department"):
        if data[field] is not None and data[field] not in allowed[field]:
            data[field] = None
    for field in _LIST_FIELDS:
        if data[field] is not None:
            data[field] = [v for v in data[field] if v in allowed[field]] or None
    pool: Dict[str, Set[str]] = {f: set(allowed[f]) for f in _AVOID_FIELDS}
    data["avoid"] = {f: [v for v in data["avoid"][f] if v in pool[f]] for f in _AVOID_FIELDS}
    return ProfileUpdate.model_validate(data)


def extract_update(
    *,
    llm: Optional[StructuredLlm],
    message: str,
    profile: StyleProfile,
    attributes: Dict[str, Any],
    interpret: Any,
) -> tuple[ProfileUpdate, bool]:
    """Return (update, llm_used). ``interpret`` fetches the search interpretation (offline path)."""
    allowed = allowed_values(attributes)
    if llm is not None:
        try:
            return keep_live_values(extract_with_llm(llm, message, profile, attributes), allowed), True
        except (LlmError, KeyError, ValueError, TypeError):
            pass  # deterministic fallback below
    return keep_live_values(extract_offline(message, interpret(message), allowed), allowed), False
