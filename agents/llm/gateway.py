"""The one place that talks to the configured LLM provider.

Design rules
  * Only this module imports the Anthropic SDK. The stylist and the shopping assistant
    depend on the small protocols below, so both run (and are tested) offline with a
    scripted fake model.
  * Every failure (timeout, rate limit, auth, refusal, truncation, bad JSON …) raises
    ``LlmError`` with a short machine ``reason``. Callers degrade to a deterministic
    fallback instead of breaking the shopper's request.
  * Credentials and models come from settings (.env): LLM_PROVIDER, ANTHROPIC_API_KEY
    (or an `ant auth` profile), LLM_MODEL_REASONING, LLM_MODEL_FAST, LLM_TIMEOUT_SEC,
    USE_LIVE_LLM.

Model tiers
  fast       LLM_MODEL_FAST       routing, extraction                (default claude-haiku-5-5)
  reasoning  LLM_MODEL_REASONING  assistant loop, stylist replies    (default claude-sonnet-5-5)
"""

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Literal, Optional, Protocol

logger = logging.getLogger("noir.llm")

Tier = Literal["fast", "reasoning"]

# Models that accept server-side refusal fallback ("default" routing) on the Claude API.
_FALLBACK_CAPABLE = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LlmError(RuntimeError):
    """The model could not produce a usable answer. ``reason`` is a short machine code."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass(frozen=True)
class ToolUse:
    id: str
    name: str
    input: Dict[str, Any]


@dataclass
class LlmTurn:
    """One model response in a tool-use conversation, provider-neutral."""

    stop_reason: str  # end_turn | tool_use
    content: List[Dict[str, Any]]  # verbatim assistant content to append back (keeps thinking blocks)
    tool_uses: List[ToolUse]
    text: str
    model: str
    request_id: Optional[str] = None
    usage: Dict[str, int] = field(default_factory=dict)


class StructuredLlm(Protocol):
    def generate_json(
        self,
        *,
        tier: Tier,
        system_blocks: List[str],
        user: str,
        schema: Dict[str, Any],
        max_tokens: int,
        effort: str = "low",
    ) -> Dict[str, Any]: ...


class ToolUsingLlm(Protocol):
    def converse(
        self,
        *,
        system_blocks: List[str],
        tools: List[Dict[str, Any]],
        messages: List[Dict[str, Any]],
        max_tokens: int,
        effort: str = "low",
        tier: Tier = "reasoning",
    ) -> LlmTurn: ...


@dataclass
class LlmUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    request_ids: List[str] = field(default_factory=list)


class ClaudeGateway:
    """StructuredLlm + ToolUsingLlm backed by the official Anthropic SDK."""

    def __init__(self, *, fast_model: str, reasoning_model: str, timeout_sec: float, api_key: Optional[str] = None):
        import anthropic  # imported lazily: offline mode never needs the SDK

        self._anthropic = anthropic
        # api_key=None lets the SDK resolve credentials itself (env var or `ant auth` profile).
        self._client = anthropic.Anthropic(api_key=api_key or None, timeout=timeout_sec, max_retries=2)
        self._models: Dict[str, str] = {"fast": fast_model, "reasoning": reasoning_model}
        self.usage = LlmUsage()

    # ------------------------------------------------------------------ transport

    def _create(self, params: Dict[str, Any]) -> Any:
        anthropic = self._anthropic
        try:
            if params["model"] in _FALLBACK_CAPABLE:
                # If a safety classifier declines, the API retries on a fallback model in the same call.
                return self._client.beta.messages.create(**params, betas=[_FALLBACK_BETA], fallbacks="default")
            return self._client.messages.create(**params)
        except anthropic.APITimeoutError as exc:
            raise LlmError("timeout", str(exc)) from exc
        except anthropic.RateLimitError as exc:
            raise LlmError("rate_limited", str(exc)) from exc
        except anthropic.AuthenticationError as exc:
            raise LlmError("auth", "Anthropic credentials missing or invalid") from exc
        except anthropic.PermissionDeniedError as exc:
            raise LlmError("permission_denied", str(exc)) from exc
        except anthropic.BadRequestError as exc:
            raise LlmError("bad_request", str(exc)) from exc
        except anthropic.APIStatusError as exc:
            raise LlmError(f"api_{exc.status_code}", str(exc)) from exc
        except anthropic.APIConnectionError as exc:
            raise LlmError("connection", str(exc)) from exc

    @staticmethod
    def _system(system_blocks: List[str]) -> List[Dict[str, Any]]:
        system: List[Dict[str, Any]] = [{"type": "text", "text": block} for block in system_blocks]
        # Render order is tools -> system -> messages: one breakpoint here caches both.
        system[-1]["cache_control"] = {"type": "ephemeral"}
        return system

    def _record_usage(self, response: Any) -> Dict[str, int]:
        usage = getattr(response, "usage", None)
        counts = {
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            "cache_read_tokens": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            "cache_write_tokens": int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
        }
        self.usage.calls += 1
        self.usage.input_tokens += counts["input_tokens"]
        self.usage.output_tokens += counts["output_tokens"]
        self.usage.cache_read_tokens += counts["cache_read_tokens"]
        request_id = getattr(response, "_request_id", None)
        if request_id:
            self.usage.request_ids.append(request_id)
        return counts

    @staticmethod
    def _check_stop(response: Any, model: str, max_tokens: int) -> None:
        if response.stop_reason == "refusal":
            raise LlmError("refusal", str(getattr(response, "stop_details", "")))
        if response.stop_reason == "max_tokens":
            raise LlmError("max_tokens", f"{model} hit max_tokens={max_tokens}")

    # ------------------------------------------------------------------ JSON calls (stylist)

    def generate_json(
        self,
        *,
        tier: Tier,
        system_blocks: List[str],
        user: str,
        schema: Dict[str, Any],
        max_tokens: int,
        effort: str = "low",
    ) -> Dict[str, Any]:
        model = self._models[tier]
        response = self._create(
            {
                "model": model,
                "max_tokens": max_tokens,
                "system": self._system(system_blocks),
                "messages": [{"role": "user", "content": user}],
                "output_config": {"format": {"type": "json_schema", "schema": schema}, "effort": effort},
            }
        )
        self._record_usage(response)
        self._check_stop(response, model, max_tokens)
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise LlmError("no_text")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LlmError("invalid_json", str(exc)) from exc
        if not isinstance(data, dict):
            raise LlmError("invalid_json", "expected a JSON object")
        return data

    # ------------------------------------------------------------------ tool-use calls (assistant)

    def converse(
        self,
        *,
        system_blocks: List[str],
        tools: List[Dict[str, Any]],
        messages: List[Dict[str, Any]],
        max_tokens: int,
        effort: str = "low",
        tier: Tier = "reasoning",
    ) -> LlmTurn:
        model = self._models[tier]
        response = self._create(
            {
                "model": model,
                "max_tokens": max_tokens,
                "system": self._system(system_blocks),
                "tools": tools,
                "tool_choice": {"type": "auto"},  # forced tool use is rejected on current models
                "messages": messages,
                "output_config": {"effort": effort},
            }
        )
        usage = self._record_usage(response)
        self._check_stop(response, model, max_tokens)
        if response.stop_reason not in ("end_turn", "tool_use"):
            raise LlmError("unexpected_stop", str(response.stop_reason))
        content = [_block_dict(block) for block in response.content]
        tool_uses = [ToolUse(b.id, b.name, dict(b.input or {})) for b in response.content if b.type == "tool_use"]
        text = "".join(b.text for b in response.content if b.type == "text")
        return LlmTurn(
            stop_reason=response.stop_reason,
            content=content,
            tool_uses=tool_uses,
            text=text,
            model=getattr(response, "model", model),
            request_id=getattr(response, "_request_id", None),
            usage=usage,
        )


def _block_dict(block: Any) -> Dict[str, Any]:
    """SDK content block -> request dict, unchanged (thinking signatures, fallback markers kept)."""
    if hasattr(block, "to_dict"):
        return block.to_dict()
    return block.model_dump(mode="json", exclude_none=True)


@lru_cache(maxsize=1)
def build_llm() -> Optional[ClaudeGateway]:
    """Live gateway when USE_LIVE_LLM is on for a supported provider, else None (offline).

    Cached per process so the SDK's HTTP connection pool is reused across turns.
    """
    from backend.app.config import get_settings

    settings = get_settings()
    if not settings.use_live_llm:
        return None
    if settings.llm_provider != "anthropic":
        logger.warning("LLM_PROVIDER=%s is not supported by this gateway; running offline", settings.llm_provider)
        return None
    try:
        return ClaudeGateway(
            fast_model=settings.llm_model_fast,
            reasoning_model=settings.llm_model_reasoning,
            timeout_sec=float(settings.llm_timeout_sec),
            api_key=settings.anthropic_api_key or None,
        )
    except Exception as exc:  # SDK missing or misconfigured: run offline rather than fail requests
        logger.warning("Live LLM disabled: %s", exc)
        return None
