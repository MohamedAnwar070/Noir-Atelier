"""Verify the assistant's LLM configuration with one tiny live call.

Usage (repo root):  python -m agents.llm.check
Prints which settings and credential source are in effect, then calls the fast
model once (a few tokens). Exit code 0 = live model reachable, 1 = not.
"""

import os
import sys
from pathlib import Path


def _credential_source() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "ANTHROPIC_API_KEY (environment / .env)"
    if os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "ANTHROPIC_AUTH_TOKEN (environment / .env)"
    config_dir = Path(os.environ.get("ANTHROPIC_CONFIG_DIR") or (
        Path(os.environ.get("APPDATA", "")) / "Anthropic" if os.name == "nt" else Path.home() / ".config" / "anthropic"
    ))
    profile = os.environ.get("ANTHROPIC_PROFILE") or "default"
    if (config_dir / "credentials" / f"{profile}.json").exists():
        return f"ant CLI profile '{profile}' ({config_dir})"
    return "none found - run `ant auth login` (or set ANTHROPIC_API_KEY)"


def main() -> int:
    from backend.app.config import get_settings
    from agents.llm.gateway import ClaudeGateway, LlmError

    s = get_settings()
    print(f"provider:          {s.llm_provider}")
    print(f"USE_LIVE_LLM:      {s.use_live_llm}")
    print(f"AGENT_RUNTIME:     {s.agent_runtime}")
    print(f"models:            reasoning={s.llm_model_reasoning}  fast={s.llm_model_fast}")
    if s.llm_provider == "anthropic":
        print(f"credentials:       {_credential_source()}")
    if s.llm_provider not in ("anthropic", "claude_code"):
        print("[FAIL] LLM_PROVIDER must be anthropic (production) or claude_code (local development)")
        return 1
    if s.llm_provider == "claude_code" and s.app_env.strip().lower() in ("production", "prod"):
        print("[FAIL] LLM_PROVIDER=claude_code is refused when APP_ENV=production")
        return 1
    try:
        if s.llm_provider == "claude_code":
            from agents.llm.claude_code import ClaudeCodeGateway, find_claude_cli

            print(f"claude CLI:        {find_claude_cli(s.claude_cli_path or None) or 'not found'}  (local development only)")
            llm = ClaudeCodeGateway(fast_model=s.llm_model_fast, reasoning_model=s.llm_model_reasoning,
                                    timeout_sec=float(s.llm_timeout_sec), cli_path=s.claude_cli_path or None)
        else:
            llm = ClaudeGateway(fast_model=s.llm_model_fast, reasoning_model=s.llm_model_reasoning,
                                timeout_sec=float(s.llm_timeout_sec), api_key=s.anthropic_api_key or None)
        data = llm.generate_json(
            tier="fast",
            system_blocks=["Health check. Reply with the JSON requested."],
            user='Return {"ok": true}.',
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"],
                    "additionalProperties": False},
            max_tokens=256,
        )
    except LlmError as exc:
        hint = {
            "auth": "sign in with `ant auth login` or set ANTHROPIC_API_KEY, then restart the backend",
            "billing": "add API credits at https://platform.claude.com (Plans & Billing) for this organization",
        }.get(exc.reason, str(exc)[:300])
        print(f"[FAIL] live call failed: {exc.reason} - {hint}")
        return 1
    except Exception as exc:  # e.g. no credentials at all
        print(f"[FAIL] could not create the client: {exc}")
        return 1
    print(f"[OK] live model reachable ({s.llm_model_fast}) - request id {llm.usage.request_ids[-1] if getattr(llm.usage, 'request_ids', None) else 'n/a'}; ok={data.get('ok')}")
    if not s.use_live_llm:
        print("  note: USE_LIVE_LLM is off, so the storefront still uses the offline reply. Set USE_LIVE_LLM=1 and restart.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
