"""[4] Writer — the stylist's voice. The only step that speaks to the shopper.

Live mode: Claude (reasoning tier) writes from the tool results only. Its JSON
schema restricts ``product_ids`` to the IDs actually returned this turn, and the
critic checks the text (prices, stock, names) before anything is shown.

Template mode: a deterministic writer used offline, and as the last resort when
the model's drafts keep failing the critic. It only ever states facts copied
from WorkerResults, so it passes the critic by construction.
"""

import json
from typing import Any, Dict, List, Optional

from .contracts import Draft, Plan, PlanAction, ProductFact, StyleProfile, WorkerResults
from .llm import StructuredLlm
from .money import format_inr
from .planner import follow_up_question
from .prompts import WRITER_SYSTEM

MAX_CARDS = 3


def _price(fact: ProductFact) -> str:
    """'at ₹2,399' for one price, 'from ₹2,399' when sizes are priced differently."""
    if fact.price_min == fact.price_max:
        return f"at {format_inr(fact.price_min)}"
    return f"from {format_inr(fact.price_min)}"


def _fact_json(fact: ProductFact) -> Dict[str, Any]:
    return {
        "product_id": fact.product_id,
        "name": fact.name,
        "department": fact.department,
        "category": fact.category,
        "color": fact.color,
        "materials": fact.materials,
        "price_inr": fact.price_min if fact.price_min == fact.price_max else {"from": fact.price_min, "to": fact.price_max},
        "in_stock": fact.in_stock,
        "stock": fact.stock,
        "sizes": fact.sizes,
        "gst_rate_pct_included": fact.gst_rate_pct,
    }


def _reply_schema(product_ids: List[str]) -> Dict[str, Any]:
    ids: Dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    if product_ids:
        ids["items"] = {"type": "string", "enum": product_ids}
    return {
        "type": "object",
        "properties": {"reply": {"type": "string"}, "product_ids": ids},
        "required": ["reply", "product_ids"],
        "additionalProperties": False,
    }


def write_with_llm(
    llm: StructuredLlm,
    *,
    message: str,
    profile: StyleProfile,
    results: WorkerResults,
    plan: Plan,
    feedback: Optional[List[str]] = None,
) -> Draft:
    payload: Dict[str, Any] = {
        "shopper_message": message,
        "style_profile": profile.model_dump(mode="json", exclude={"confidence", "schema_version"}),
        "plan": plan.action.value,
        "tool_results": [_fact_json(f) for f in results.products],
        "results_relaxed": results.relaxed,
    }
    if feedback:
        payload["your_previous_draft_was_rejected_because"] = feedback
    data = llm.generate_json(
        tier="reasoning",
        system_blocks=[WRITER_SYSTEM],
        user=json.dumps(payload, ensure_ascii=False),
        schema=_reply_schema([f.product_id for f in results.products]),
        max_tokens=4096,
        effort="low",
    )
    return Draft(reply=str(data["reply"]).strip(), product_ids=list(dict.fromkeys(data.get("product_ids", []))), source="llm")


def _brief(profile: StyleProfile) -> str:
    parts: List[str] = []
    if profile.occasion:
        parts.append(profile.occasion.replace("_", " "))
    if profile.recipient:
        parts.append(f"your {profile.recipient}")
    return " for ".join(parts) if parts else "you"


def write_template(profile: StyleProfile, results: WorkerResults, plan: Plan) -> Draft:
    if plan.action is PlanAction.ASK:
        return Draft(reply=plan.question or follow_up_question(profile), product_ids=[], source="template")

    picks = [f for f in results.products if f.in_stock][:MAX_CARDS]
    if not picks:
        hint = (
            "Would you like me to widen the budget a little, or try another colour?"
            if profile.budget_max_inr is not None
            else "Could you tell me a little more — the occasion, a colour you like, or a budget?"
        )
        return Draft(reply=f"I couldn't find an in-stock piece that fits that brief just now. {hint}", product_ids=[], source="template")

    first = picks[0]
    sentences = [
        f"For {_brief(profile)}, I'd start with the {first.name}, {_price(first)} including GST — "
        f"{first.color.lower()}{', ' + ' and '.join(first.materials) if first.materials else ''}, and in stock."
    ]
    if len(picks) > 1:
        second = picks[1]
        sentences.append(f"The {second.name}, {_price(second)}, is another lovely option.")
    if results.relaxed:
        sentences.append("Nothing matched every detail you mentioned, so these keep to the essentials of your brief.")
    elif profile.budget_max_inr is not None:
        subject = {1: "It is", 2: "Both are"}.get(len(picks), "All of these are")
        sentences.append(f"{subject} within your {format_inr(float(profile.budget_max_inr))} budget.")
    sentences.append(follow_up_question(profile))
    return Draft(reply=" ".join(sentences), product_ids=[f.product_id for f in picks], source="template")
