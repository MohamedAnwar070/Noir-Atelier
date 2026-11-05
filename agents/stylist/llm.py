"""Claude gateway for the stylist: structured-JSON calls with one failure type.

Design rules
  * Only this module imports the Anthropic SDK. Every other step depends on the
    small ``StructuredLlm`` protocol, so the pipeline runs (and is tested) offline.
  * Every call returns JSON constrained by a JSON Schema (``output_config.format``);
    callers re-validate with Pydantic — the model is never trusted blindly.
  * Any failure (timeout, rate limit, refusal, truncation, bad JSON …) raises
    ``LlmError``. The pipeline catches it and uses its deterministic fallback, so a
    model problem degrades a reply instead of breaking it.

Model tiers (configured, see backend.app.config):
  fast       LLM_MODEL_FAST       routing + profile extraction  (default claude-haiku-5-5)
  reasoning  LLM_MODEL_REASONING  the stylist's reply           (default claude-sonnet-5-5)
"""

import json
import logging
from functools import lru_cache
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Protocol

logger = logging.getLogger("noir.stylist.llm")

Tier = Literal["fast", "reasoning"]

# Models that accept the server-side refusal fallback ("default" routing) on the Claude API.
_FALLBACK_CAPABLE = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LlmError(RuntimeError):
    """The model could not produce a usable answer. ``reason`` is a short machine code."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


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


@dataclass
class LlmUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    request_ids: List[str] = field(default_factory=list)


class ClaudeGateway:
    """StructuredLlm backed by the official Anthropic SDK."""

    def __init__(self, *, fast_model: str, reasoning_model: str, timeout_sec: float, api_key: Optional[str] = None):
        import anthropic  # imported lazily: offline mode never needs the SDK

        self._anthropic = anthropic
        # api_key=None lets the SDK resolve credentials itself (env var or `ant auth` profile).
        self._client = anthropic.Anthropic(api_key=api_key or None, timeout=timeout_sec, max_retries=2)
        self._models: Dict[str, str] = {"fast": fast_model, "reasoning": reasoning_model}
        self.usage = LlmUsage()

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
        system: List[Dict[str, Any]] = [{"type": "text", "text": block} for block in system_blocks]
        # Stable instructions + live catalogue come first; cache up to the last system block.
        system[-1]["cache_control"] = {"type": "ephemeral"}
        params: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}, "effort": effort},
        }
        anthropic = self._anthropic
        try:
            if model in _FALLBACK_CAPABLE:
                # If a safety classifier declines, the API retries on a fallback model in the same call.
                response = self._client.beta.messages.create(**params, betas=[_FALLBACK_BETA], fallbacks="default")
            else:
                response = self._client.messages.create(**params)
        except anthropic.APITimeoutError as exc:
            raise LlmError("timeout", str(exc)) from exc
        except anthropic.RateLimitError as exc:
            raise LlmError("rate_limited", str(exc)) from exc
        except anthropic.AuthenticationError as exc:
            raise LlmError("auth", "Anthropic credentials missing or invalid") from exc
        except anthropic.BadRequestError as exc:
            raise LlmError("bad_request", str(exc)) from exc
        except anthropic.APIStatusError as exc:
            raise LlmError(f"api_{exc.status_code}", str(exc)) from exc
        except anthropic.APIConnectionError as exc:
            raise LlmError("connection", str(exc)) from exc

        self._record_usage(response)
        if response.stop_reason == "refusal":
            raise LlmError("refusal", str(getattr(response, "stop_details", "")))
        if response.stop_reason == "max_tokens":
            raise LlmError("max_tokens", f"{model} hit max_tokens={max_tokens}")
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

    def _record_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        self.usage.calls += 1
        if usage is not None:
            self.usage.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
            self.usage.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
            self.usage.cache_read_tokens += int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        request_id = getattr(response, "_request_id", None)
        if request_id:
            self.usage.request_ids.append(request_id)


@lru_cache(maxsize=1)
def build_llm() -> Optional[StructuredLlm]:
    """Live Claude gateway when enabled in settings, else None (offline deterministic brain).

    Cached per process so the SDK's HTTP connection pool is reused across turns.
    """
    from backend.app.config import get_settings

    settings = get_settings()
    if not settings.use_live_llm or settings.llm_provider != "anthropic":
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
