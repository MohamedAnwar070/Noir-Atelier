"""The stylist graph — one turn of the conversational personal stylist.

    message
      │  guardrails: prompt-injection check, PII scrubbed before any model sees it
      ▼
    [1] route ──────────── not shopping ─► delegate to the specialist agents
      │ discovery                           (cart, orders, returns, support/handoff)
      ▼
    load (parallel): live catalogue attributes · saved profile
      ▼
    [2] extract update ─► merge ─► living style profile
      ▼
    [3] plan ── ask one question ───────────────────────────┐
      │ search / refine                                     │
      ▼                                                     │
    workers (parallel): full-brief search · broadened search│
      ▼                                                     │
    [4] write ◄── problems ── [5] critic (max 2 rewrites) ──┤
      │ pass (or template fallback, grounded by construction)
      ▼                                                     ▼
    save profile + turn trace (audited) ─► reply + product cards + profile

Every node degrades instead of failing: no model → deterministic rules; a tool
error → fewer results; a draft that keeps failing the critic → template reply.
"""

import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.app.schemas.stylist_schema import TurnTrace

from ..client import PlatformApiClient
from ..gateway import check_prompt_injection, scrub_pii
from ..schemas.state import AgentRequest, AgentResponse, AgentRole, MemorySnapshot, ReActStep
from .contracts import Draft, Plan, PlanAction, Route, StyleProfile, Verdict, WorkerResults
from .critic import review
from .extractor import extract_update
from .llm import LlmError, StructuredLlm
from .planner import plan_turn
from .profile_ops import merge
from .router import route_message
from .workers import StylistTools, ToolBudget, ToolBudgetExceeded, collect_results, run_parallel, search_params
from .writer import MAX_CARDS, write_template, write_with_llm

MAX_REWRITES = 2
PATTERNS = ["routing", "prompt_chaining", "parallelization", "orchestrator_workers", "evaluator_optimizer"]
SHOPPER_ROLES = {"customer"}


def _trace_id() -> str:
    return f"TRC-{uuid.uuid4().int % 900000 + 100000:06d}"


class StylistPipeline:
    def __init__(
        self,
        client: PlatformApiClient,
        *,
        delegate: Callable[[AgentRequest], AgentResponse],
        llm: Optional[StructuredLlm] = None,
    ) -> None:
        self._client = client
        self._delegate = delegate
        self._llm = llm

    # ------------------------------------------------------------------ entry --

    def handle(self, req: AgentRequest) -> AgentResponse:
        # Staff tooling, explicit specialist requests and blocked input keep their existing paths.
        if req.actor_role not in SHOPPER_ROLES:
            return self._delegate(req)
        if req.preferred_agent and req.preferred_agent not in (AgentRole.STYLIST.value, AgentRole.CATALOG.value):
            return self._delegate(req)
        if check_prompt_injection(req.message):
            return self._delegate(req)  # the orchestrator's gateway blocks and reports it

        started = time.perf_counter()
        trace_id = _trace_id()
        safe_message = scrub_pii(req.message)
        steps: List[ReActStep] = []

        route, route_reason, llm_routed = route_message(req, self._llm, safe_message)
        steps.append(ReActStep(step_number=1, layer="perception", thought=f"route={route.value}", observation=route_reason))
        if route is not Route.DISCOVERY:
            response = self._delegate(req)
            response.active_patterns = list(dict.fromkeys([*response.active_patterns, "routing"]))
            return response

        tools = StylistTools(self._client, trace_id=trace_id, on_behalf_of=req.customer_id, budget=ToolBudget())
        loaded = run_parallel({"attributes": tools.attributes, "profile": lambda: tools.get_profile(req.session_id)})
        attributes = self._ok_payload(loaded["attributes"])
        if attributes is None:
            # Without the live catalogue we cannot ground a reply: hand over rather than guess.
            return self._delegate(req)
        pricing = attributes.get("pricing", {})
        saved = self._ok_payload(loaded["profile"]) or {}
        profile = StyleProfile.model_validate(saved.get("profile") or {})
        last_shown: List[str] = list(saved.get("last_shown_ids") or [])

        update, llm_extracted = extract_update(
            llm=self._llm,
            message=safe_message,
            profile=profile,
            attributes=attributes,
            interpret=lambda text: self._interpret(tools, text),
        )
        new_profile = merge(profile, update)
        plan = plan_turn(new_profile, update, last_shown, safe_message)
        steps.append(
            ReActStep(
                step_number=2,
                layer="reasoning",
                thought=f"profile updated; plan={plan.action.value}",
                planned_action=plan.reason,
            )
        )

        results = WorkerResults()
        if plan.action is not PlanAction.ASK:
            results = self._search(tools, new_profile, pricing, update, plan, last_shown)
            steps.append(
                ReActStep(
                    step_number=3,
                    layer="action",
                    thought="parallel search workers",
                    observation=f"{len(results.products)} grounded products (matches={results.total_matches}, relaxed={results.relaxed})",
                )
            )

        draft, verdict, attempts, llm_wrote = self._compose(safe_message, new_profile, results, plan, pricing)
        steps.append(
            ReActStep(
                step_number=4,
                layer="reflection",
                thought=f"critic {'passed' if verdict.passed else 'failed'} after {attempts} draft(s) ({draft.source})",
                reflection="; ".join(verdict.problems) or "grounded",
            )
        )

        turn = TurnTrace(
            trace_id=trace_id,
            route=route.value,
            plan=plan.action.value,
            tools_called=list(tools.budget.used),
            product_ids_shown=draft.product_ids,
            critic_attempts=attempts,
            critic_passed=verdict.passed,
            llm_used=llm_routed or llm_extracted or llm_wrote,
        )
        saved_turns = self._save(tools, req.session_id, new_profile, turn)

        return AgentResponse(
            trace_id=trace_id,
            session_id=req.session_id,
            routed_agent=AgentRole.STYLIST.value,
            service_account="svc-stylist",
            status="clarify_missing_info" if plan.action is PlanAction.ASK else "answer",
            reply=draft.reply,
            data={
                "products": [results.display_items[pid] for pid in draft.product_ids if pid in results.display_items],
                "style_profile": new_profile.model_dump(mode="json"),
                "plan": plan.action.value,
                "results_relaxed": results.relaxed,
                "catalog_version": attributes.get("version"),
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "action_feedback": {
                    "type": "stylist_suggestions",
                    "badge": "Personal Stylist",
                    "title": "Your brief" if plan.action is PlanAction.ASK else f"{len(draft.product_ids)} pieces picked for you",
                    "summary": _brief_summary(new_profile),
                },
            },
            tool_traces=tools.traces,
            active_patterns=PATTERNS,
            react_steps=steps,
            memory=MemorySnapshot(
                namespace=f"{req.customer_id or 'ANON'}:{req.session_id}",
                short_term_turns=saved_turns,
                episodic_events=[f"plan={plan.action.value}", *(f"shown={pid}" for pid in draft.product_ids)],
            ),
            steps_taken=len(steps),
            reflection_verified=verdict.passed,
        )

    # ------------------------------------------------------------------ nodes --

    @staticmethod
    def _ok_payload(outcome: Any) -> Optional[Dict[str, Any]]:
        if isinstance(outcome, Exception):
            return None
        status, payload = outcome
        return payload if status == 200 and isinstance(payload, dict) else None

    @staticmethod
    def _interpret(tools: StylistTools, text: str) -> Dict[str, Any]:
        """Offline extraction uses the search engine's own interpretation of the words."""
        try:
            status, payload = tools.search({"q": text, "limit": 1})
        except ToolBudgetExceeded:
            return {}
        return (payload or {}).get("interpretation", {}) if status == 200 else {}

    @staticmethod
    def _search(
        tools: StylistTools,
        profile: StyleProfile,
        pricing: Dict[str, Any],
        update: Any,
        plan: Plan,
        last_shown: List[str],
    ) -> WorkerResults:
        exclude = last_shown if plan.exclude_previous else []
        outcomes = run_parallel(
            {
                "primary": lambda: tools.search(search_params(profile)),
                "broad": lambda: tools.search(search_params(profile, broaden=True)),
            }
        )
        return collect_results(profile, outcomes["primary"], outcomes["broad"], pricing, exclude_ids=exclude)

    def _compose(
        self,
        message: str,
        profile: StyleProfile,
        results: WorkerResults,
        plan: Plan,
        pricing: Dict[str, Any],
    ) -> Tuple[Draft, Verdict, int, bool]:
        """Evaluator-optimizer loop: draft → critic → rewrite (max 2) → grounded template."""
        attempts = 0
        if self._llm is not None and plan.action is not PlanAction.ASK:
            feedback: Optional[List[str]] = None
            for _ in range(1 + MAX_REWRITES):
                attempts += 1
                try:
                    draft = write_with_llm(
                        self._llm, message=message, profile=profile, results=results, plan=plan, feedback=feedback
                    )
                except (LlmError, KeyError, ValueError, TypeError):
                    break
                draft = Draft(draft.reply, draft.product_ids[:MAX_CARDS], draft.source)
                verdict = review(draft, results, profile, pricing)
                if verdict.passed:
                    return draft, verdict, attempts, True
                feedback = verdict.problems

        attempts += 1
        draft = write_template(profile, results, plan)
        verdict = review(draft, results, profile, pricing)
        if not verdict.passed:  # should be impossible — never show an ungrounded reply
            draft = Draft("Let me take another look at the collection for you — could you tell me a bit more about what you need?", [], "template")
            verdict = review(draft, results, profile, pricing)
        return draft, verdict, attempts, False

    @staticmethod
    def _save(tools: StylistTools, session_id: str, profile: StyleProfile, turn: TurnTrace) -> int:
        status, payload = tools.save_profile(
            session_id, {"profile": profile.model_dump(mode="json"), "turn": turn.model_dump(mode="json")}
        )
        return int(payload.get("turns", 0)) if status == 200 and isinstance(payload, dict) else 0


def _brief_summary(profile: StyleProfile) -> str:
    parts: List[str] = []
    if profile.occasion:
        parts.append(profile.occasion.replace("_", " ").title())
    if profile.recipient:
        parts.append(f"for {profile.recipient}")
    if profile.palettes:
        parts.append(" / ".join(profile.palettes) + " tones")
    if profile.colors:
        parts.append(", ".join(profile.colors))
    if profile.product_types:
        parts.append(", ".join(t.replace("-", " ") for t in profile.product_types))
    if profile.budget_max_inr is not None:
        parts.append(f"up to ₹{float(profile.budget_max_inr):,.0f}")
    return " · ".join(parts) or "Tell me the occasion and budget"
