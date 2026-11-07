"""The shopping-assistant runtime: one bounded tool-use loop per shopper message.

    Understand + Plan   the configured LLM reads the conversation and decides which tools to call
                        (no keyword routing, no hand-written intent map)
    Search              tools call the real backend APIs (validated, permission-gated, on behalf of
                        the authenticated shopper), in parallel when independent
    Evaluate            the drafted reply is checked against the turn's evidence (grounding.review);
                        one rewrite is allowed, then a template built from verified facts
    Respond             ChatReply — text + product cards built by code from catalogue payloads
    Log                 TurnTrace — intent, plan note, every tool call, evaluation, errors, usage

Limits per turn (settings): AGENT_MAX_STEPS tool calls, a model-call cap, and a wall-clock deadline.
Any model failure degrades to the deterministic search reply instead of an error page.
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..client import PlatformApiClient
from ..gateway import check_prompt_injection, scrub_pii
from ..llm import LlmError, ToolUse, ToolUsingLlm
from .contracts import ChatContext, ChatReply, ConversationTurn, ToolCallRecord, TurnResult, TurnTrace
from .evidence import Evidence
from .fallback import offline_reply, template_from_evidence
from .grounding import MAX_CARDS, is_internal, review
from .prompt import INSTRUCTIONS, shopper_context, vocabulary_block, vocabulary_values
from .tools import PROGRESS_LABELS, REPLY_TOOL, ROLE, ToolEnv, ToolInputError, ToolOutcome, ToolSpec, tools_for

logger = logging.getLogger("noir.assistant")

MAX_INPUT_CHARS = 1000
MAX_MODEL_CALLS = 6
MAX_REWRITES = 1
MAX_TOKENS = 8000
MAX_HISTORY_TURNS = 12
TOOL_WORKERS = 4


Progress = Callable[[str], None]


class _TurnBudgetExceeded(RuntimeError):
    pass


@dataclass
class _Final:
    message: str
    product_ids: List[str]
    follow_ups: List[str] = field(default_factory=list)
    intent: Optional[str] = None
    plan_note: Optional[str] = None
    template: bool = False


class AssistantRuntime:
    def __init__(
        self,
        client: PlatformApiClient,
        llm: Optional[ToolUsingLlm],
        *,
        persona: str,
        max_tool_calls: int = 6,
        deadline_sec: float = 45.0,
        effort: str = "low",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.llm = llm
        self.persona = persona
        self.max_tool_calls = max(1, int(max_tool_calls))
        self.deadline_sec = float(deadline_sec)
        self.effort = effort
        self.clock = clock
        self._progress: Optional[Progress] = None

    # ================================================================== entry point

    def handle(self, message: str, ctx: ChatContext, on_progress: Optional[Progress] = None) -> TurnResult:
        """Run one turn. ``on_progress`` receives shopper-safe status labels while it works."""
        self._progress = on_progress
        started = self.clock()
        text = scrub_pii((message or "").strip())[:MAX_INPUT_CHARS]
        trace = TurnTrace(
            trace_id=ctx.trace_id,
            session_id=ctx.session_id,
            customer_id=ctx.customer_id,
            runtime="llm" if self.llm is not None else "offline",
            user_message=text,
        )
        signal = check_prompt_injection(text)
        if signal:
            # A signal for operators, not a router: the model and the permission design handle it.
            trace.errors.append(f"injection_signal:{signal}")

        evidence = Evidence()
        evidence.add_user_text(text)
        attributes = self._attributes(ctx, trace)
        env = ToolEnv(self.client, ctx, evidence, vocabulary_values(attributes))

        if self.llm is None:
            final = self._offline(env, text, trace)
        else:
            self._emit("Understanding your request…")
            try:
                final = self._loop(env, text, attributes, trace, started)
                trace.status = "fallback" if final.template else "answered"
            except LlmError as exc:
                trace.errors.append(f"llm:{exc.reason}")
                final = self._offline(env, text, trace)
            except _TurnBudgetExceeded as exc:
                trace.errors.append(f"budget:{exc}")
                final = self._template(evidence, trace)
            except Exception as exc:  # never let a bug reach the shopper as a 500
                logger.exception("assistant turn %s failed", ctx.trace_id)
                trace.errors.append(f"internal:{type(exc).__name__}")
                trace.status = "error"
                final = self._template(evidence, trace)
                trace.status = "error"

        cards = [evidence.products[pid] for pid in final.product_ids if pid in evidence.products]
        trace.reply = scrub_pii(final.message)
        trace.product_ids = [c["product_id"] for c in cards]
        trace.intent = final.intent
        trace.plan_note = (final.plan_note or "")[:300] or None
        trace.latency_ms = int((self.clock() - started) * 1000)

        reply = ChatReply(
            reference_id=ctx.trace_id,
            session_id=ctx.session_id,
            status="answer",
            persona=self.persona,
            reply=final.message,
            products=cards,
            follow_up_prompts=final.follow_ups,
        )
        remember = [
            ConversationTurn("user", text),
            ConversationTurn("assistant", final.message, trace.product_ids),
        ]
        return TurnResult(reply=reply, trace=trace, remember=remember)

    # ================================================================== the loop

    def _loop(self, env: ToolEnv, text: str, attributes: Dict[str, Any], trace: TurnTrace, started: float) -> _Final:
        specs = tools_for(env.ctx)
        allowed = {s.name: s for s in specs}
        system = [INSTRUCTIONS, vocabulary_block(attributes)]
        tool_defs = [s.definition() for s in specs]
        messages = history_messages(env.ctx.history) + [
            {"role": "user", "content": [{"type": "text", "text": shopper_context(env.ctx)}, {"type": "text", "text": text}]}
        ]
        usage = trace.usage
        usage.update({"model_calls": 0, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "request_ids": []})
        tool_calls = 0
        rewrites = 0

        for _ in range(MAX_MODEL_CALLS):
            self._check_deadline(started)
            turn = self.llm.converse(
                system_blocks=system, tools=tool_defs, messages=messages, max_tokens=MAX_TOKENS, effort=self.effort
            )
            trace.model = turn.model
            usage["model_calls"] += 1
            for key in ("input_tokens", "output_tokens", "cache_read_tokens"):
                usage[key] += int(turn.usage.get(key, 0))
            if turn.request_id:
                usage["request_ids"].append(turn.request_id)
            messages.append({"role": "assistant", "content": turn.content})

            if not turn.tool_uses:
                # Answered in plain text instead of the reply tool: verify it the same way (no cards).
                if not turn.text.strip():
                    messages.append({"role": "user", "content": "Please answer the shopper with reply_to_customer."})
                    continue
                verdict = review(turn.text, [], env.evidence, self._sizes(env))
                trace.evaluation.attempts += 1
                if verdict.passed:
                    trace.evaluation.passed = True
                    return _Final(turn.text.strip(), [])
                trace.evaluation.problems.extend(verdict.problems)
                if rewrites >= MAX_REWRITES:
                    return self._template(env.evidence, trace, sizes=self._sizes(env))
                rewrites += 1
                messages.append({"role": "user", "content": _rewrite_request(verdict.problems)})
                continue

            replies = [u for u in turn.tool_uses if u.name == REPLY_TOOL]
            others = [u for u in turn.tool_uses if u.name != REPLY_TOOL]
            if others:
                for label in dict.fromkeys(PROGRESS_LABELS.get(u.name, "Working on it…") for u in others):
                    self._emit(label)
                results, tool_calls = self._run_tools(others, allowed, env, trace, tool_calls, started)
                results += [
                    _tool_result(u.id, {"error": "Call reply_to_customer alone, after reading the tool results."}, True)
                    for u in replies
                ]
                messages.append({"role": "user", "content": results})
                continue

            call, extra = replies[0], replies[1:]
            final, problem = _parse_reply(call.input)
            if final is None:
                messages.append({"role": "user", "content": [_tool_result(call.id, {"error": problem}, True)]
                                 + [_tool_result(u.id, {"error": "Only one reply per turn."}, True) for u in extra]})
                continue
            self._emit("Checking the details…" if not rewrites else "Double-checking the details…")
            verdict = review(final.message, final.product_ids, env.evidence, self._sizes(env))
            trace.evaluation.attempts += 1
            trace.intent, trace.plan_note = final.intent, final.plan_note
            if verdict.passed:
                trace.evaluation.passed = True
                return final
            trace.evaluation.problems.extend(verdict.problems)
            if rewrites >= MAX_REWRITES:
                fallback = self._template(env.evidence, trace, sizes=self._sizes(env))
                fallback.intent, fallback.plan_note = final.intent, final.plan_note
                return fallback
            rewrites += 1
            messages.append({"role": "user", "content": [_tool_result(call.id, {"error": _rewrite_request(verdict.problems)}, True)]
                             + [_tool_result(u.id, {"error": "Only one reply per turn."}, True) for u in extra]})

        trace.errors.append("budget:model_calls")
        return self._template(env.evidence, trace, sizes=self._sizes(env))

    # ================================================================== tools

    def _run_tools(
        self,
        uses: List[ToolUse],
        allowed: Dict[str, ToolSpec],
        env: ToolEnv,
        trace: TurnTrace,
        used: int,
        started: float,
    ) -> Tuple[List[Dict[str, Any]], int]:
        results: List[Optional[Dict[str, Any]]] = [None] * len(uses)
        runnable: List[Tuple[int, ToolUse, ToolSpec]] = []
        for index, use in enumerate(uses):
            spec = allowed.get(use.name)
            if spec is None or spec.handler is None:
                results[index] = _tool_result(use.id, {"error": f"Unknown tool '{use.name}'."}, True)
                trace.tool_calls.append(ToolCallRecord(use.name, _safe_input(use.input), "invalid", error="unknown_tool"))
            elif used >= self.max_tool_calls:
                results[index] = _tool_result(use.id, {"error": "The tool budget for this turn is used up. Answer with what you have."}, True)
                trace.tool_calls.append(ToolCallRecord(use.name, _safe_input(use.input), "budget"))
            else:
                used += 1
                runnable.append((index, use, spec))

        if runnable:
            with ThreadPoolExecutor(max_workers=min(TOOL_WORKERS, len(runnable))) as pool:
                futures = [(index, use, pool.submit(self._invoke, spec, env, use.input)) for index, use, spec in runnable]
                for index, use, future in futures:
                    remaining = max(0.5, self.deadline_sec - (self.clock() - started))
                    try:
                        outcome, status, latency = future.result(timeout=remaining)
                    except FutureTimeout:
                        outcome, status, latency = ToolOutcome({"error": "The request timed out."}, is_error=True), "timeout", remaining * 1000
                    results[index] = _tool_result(use.id, outcome.content, outcome.is_error)
                    trace.tool_calls.append(
                        ToolCallRecord(
                            name=use.name,
                            input=_safe_input(use.input),
                            status=status,
                            http_status=outcome.http_status,
                            latency_ms=round(latency, 1),
                            summary=outcome.summary,
                            error=str(outcome.content.get("error"))[:300] if outcome.is_error else None,
                        )
                    )
                    self._learn_sizes(env, use.name, outcome)
        return [r for r in results if r is not None], used

    @staticmethod
    def _invoke(spec: ToolSpec, env: ToolEnv, args: Dict[str, Any]) -> Tuple[ToolOutcome, str, float]:
        t0 = time.perf_counter()
        try:
            outcome = spec.handler(env, dict(args or {}))
            status = "error" if outcome.is_error else "ok"
            if outcome.is_error and outcome.http_status == 403:
                status = "denied"
        except ToolInputError as exc:
            outcome, status = ToolOutcome({"error": str(exc)}, is_error=True), "invalid"
        except Exception as exc:  # a tool bug must not end the turn
            logger.exception("tool %s failed", spec.name)
            outcome, status = ToolOutcome({"error": "This lookup failed; try another approach."}, is_error=True,
                                          summary={"exception": type(exc).__name__}), "error"
        return outcome, status, (time.perf_counter() - t0) * 1000

    @staticmethod
    def _learn_sizes(env: ToolEnv, name: str, outcome: ToolOutcome) -> None:
        """Sizes from the shopper's saved profile also constrain which cards may be shown."""
        if name in ("get_style_profile", "save_style_profile") and not outcome.is_error:
            sizes = (outcome.content.get("profile") or {}).get("sizes") or []
            env.evidence.requested_sizes.update(str(s).upper() for s in sizes)

    @staticmethod
    def _sizes(env: ToolEnv) -> List[str]:
        return sorted(env.evidence.requested_sizes)

    # ================================================================== fallbacks & helpers

    def _emit(self, label: str) -> None:
        """Send a progress label; a broken listener must never break the turn."""
        if self._progress is None:
            return
        try:
            self._progress(label)
        except Exception:  # pragma: no cover - listener failure is non-fatal
            logger.warning("progress listener failed", exc_info=True)

    def _offline(self, env: ToolEnv, text: str, trace: TurnTrace) -> _Final:
        self._emit(PROGRESS_LABELS["search_products"])
        message, ids, error = offline_reply(env, text)
        trace.tool_calls.append(ToolCallRecord("search_products", {"query": text[:120]}, "error" if error else "ok",
                                               summary={"product_ids": ids}, error=error))
        trace.status = "fallback"
        trace.evaluation.template_used = True
        return _Final(message, ids)

    def _template(self, evidence: Evidence, trace: TurnTrace, sizes: Optional[List[str]] = None) -> _Final:
        message, ids = template_from_evidence(evidence, sizes or sorted(evidence.requested_sizes))
        trace.status = "fallback"
        trace.evaluation.template_used = True
        trace.evaluation.passed = False
        return _Final(message, ids, template=True)

    def _attributes(self, ctx: ChatContext, trace: TurnTrace) -> Dict[str, Any]:
        status, payload = self.client.call(ROLE, "catalog_vocabulary", "GET", "/api/catalog/attributes",
                                           on_behalf_of=ctx.customer_id, trace_id=ctx.trace_id)
        if status != 200 or not isinstance(payload, dict):
            trace.errors.append(f"vocabulary:http_{status}")
            return {}
        return payload

    def _check_deadline(self, started: float) -> None:
        if self.clock() - started > self.deadline_sec:
            raise _TurnBudgetExceeded("deadline")


# ====================================================================== module helpers


def history_messages(history: List[ConversationTurn]) -> List[Dict[str, Any]]:
    """Earlier turns as plain text (no tool details); always starts with a user message."""
    turns = history[-MAX_HISTORY_TURNS:]
    while turns and turns[0].role != "user":
        turns = turns[1:]
    messages = []
    for turn in turns:
        text = turn.text
        if turn.role == "assistant" and turn.product_ids:
            text += f"\n[Products shown: {', '.join(turn.product_ids)}]"
        messages.append({"role": turn.role, "content": text})
    return messages


def _tool_result(tool_use_id: str, content: Dict[str, Any], is_error: bool) -> Dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(content, ensure_ascii=False, default=str),
        "is_error": bool(is_error),
    }


def _rewrite_request(problems: List[str]) -> str:
    return ("Not sent to the shopper — it could not be verified against the tool results:\n- "
            + "\n- ".join(problems)
            + "\nFix these (use only facts from this turn's tool results) and call reply_to_customer again.")


def _parse_reply(args: Dict[str, Any]) -> Tuple[Optional[_Final], str]:
    message = args.get("message")
    ids = args.get("product_ids")
    follow = args.get("follow_up_prompts")
    if not isinstance(message, str) or not isinstance(ids, list) or not isinstance(follow, list):
        return None, "message must be a string; product_ids and follow_up_prompts must be lists."
    clean_ids = list(dict.fromkeys(str(i).strip().upper() for i in ids if isinstance(i, str)))[: MAX_CARDS + 1]
    follow_ups = [f.strip()[:80] for f in follow if isinstance(f, str) and f.strip() and not is_internal(f)][:3]
    return _Final(
        message=message.strip(),
        product_ids=clean_ids,
        follow_ups=follow_ups,
        intent=str(args.get("intent") or "")[:32] or None,
        plan_note=str(args.get("plan_note") or "")[:300] or None,
    ), ""


def _safe_input(args: Dict[str, Any]) -> Dict[str, Any]:
    """Tool input for the trace, with any PII-looking text scrubbed and size-capped."""
    if not args:
        return {}
    raw = scrub_pii(json.dumps(args, ensure_ascii=False, default=str))
    if len(raw) > 2000:
        return {"truncated": raw[:2000]}
    return json.loads(raw)
