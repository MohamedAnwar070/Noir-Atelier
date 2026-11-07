"""LOCAL DEVELOPMENT ONLY: run the assistant on the Claude Code CLI (`claude -p`).

Switch with one line in .env — no code changes:
    LLM_PROVIDER=claude_code     # local: your Claude Code login, no API credits
    LLM_PROVIDER=anthropic       # production: Anthropic API (supported for products)

Why development only
  * A Claude Code subscription is for its owner's own use, not for serving a public shop.
  * Every call starts a CLI process (slower), and the CLI has no native tool calling:
    tools are described in the prompt and the model answers in JSON, which this
    adapter parses into the same ``LlmTurn`` the API gateway returns. The runtime's
    grounding check still verifies every reply.
  * build_llm() refuses this provider when APP_ENV=production.

Safety
  The CLI runs as a pure text model: built-in tools disabled (`--tools ""`), no MCP
  servers (`--strict-mcp-config`), no user/project settings (`--setting-sources ""`),
  no saved session, a temp working directory, and the prompt over stdin. Customer
  text therefore cannot make it read files or run commands.
"""

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .gateway import LlmError, LlmTurn, LlmUsage, Tier, ToolUse

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def find_claude_cli(configured: Optional[str] = None) -> Optional[str]:
    """CLAUDE_CLI_PATH if set, else `claude` on PATH, else the binary bundled with the IDE extension."""
    if configured and os.path.isfile(configured):
        return configured
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    home = Path.home()
    patterns = [
        str(home / ext / "extensions" / "anthropic.claude-code-*" / "resources" / "native-binary" / name)
        for ext in (".vscode", ".antigravity-ide", ".cursor")
        for name in ("claude.exe", "claude")
    ]
    found = sorted((p for pattern in patterns for p in glob.glob(pattern)), reverse=True)
    return found[0] if found else None


def _extract_json(text: str) -> Any:
    """The model's JSON answer, tolerating code fences or a sentence around it."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise LlmError("invalid_json", f"could not parse a JSON object from: {text[:200]!r}")


class ClaudeCodeGateway:
    """StructuredLlm + ToolUsingLlm backed by the local Claude Code CLI."""

    def __init__(self, *, fast_model: str, reasoning_model: str, timeout_sec: float, cli_path: Optional[str] = None):
        self.binary = find_claude_cli(cli_path)
        if not self.binary:
            raise LlmError("unavailable", "Claude Code CLI not found (install it or set CLAUDE_CLI_PATH)")
        self._models: Dict[str, str] = {"fast": fast_model, "reasoning": reasoning_model}
        self.timeout_sec = timeout_sec
        self.usage = LlmUsage()

    # ------------------------------------------------------------------ transport

    def _run(self, model: str, system: str, prompt: str) -> str:
        cmd = [
            self.binary, "-p",
            "--model", model,
            "--tools", "",
            "--strict-mcp-config",
            "--setting-sources", "",
            "--no-session-persistence",
            "--output-format", "text",
            "--system-prompt", system,
        ]
        try:
            proc = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                timeout=self.timeout_sec, cwd=tempfile.gettempdir(),
            )
        except subprocess.TimeoutExpired as exc:
            raise LlmError("timeout", f"claude -p exceeded {self.timeout_sec}s") from exc
        except OSError as exc:
            raise LlmError("unavailable", str(exc)) from exc
        self.usage.calls += 1
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[:300]
            reason = "auth" if "login" in detail.lower() or "auth" in detail.lower() else "cli_error"
            raise LlmError(reason, detail)
        out = (proc.stdout or "").strip()
        if not out:
            raise LlmError("no_text", "claude -p returned nothing")
        return out

    # ------------------------------------------------------------------ JSON calls (stylist)

    def generate_json(self, *, tier: Tier, system_blocks: List[str], user: str, schema: Dict[str, Any],
                      max_tokens: int, effort: str = "low") -> Dict[str, Any]:
        system = "\n\n".join(system_blocks) + (
            "\n\nAnswer with ONLY one JSON object (no prose, no code fences) that validates against this "
            f"JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"
        )
        data = _extract_json(self._run(self._models[tier], system, user))
        if not isinstance(data, dict):
            raise LlmError("invalid_json", "expected a JSON object")
        return data

    # ------------------------------------------------------------------ tool-use calls (assistant)

    def converse(self, *, system_blocks: List[str], tools: List[Dict[str, Any]], messages: List[Dict[str, Any]],
                 max_tokens: int, effort: str = "low", tier: Tier = "reasoning") -> LlmTurn:
        model = self._models[tier]
        catalog = [{"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]} for t in tools]
        system = "\n\n".join(system_blocks) + (
            "\n\nTOOL PROTOCOL (this replaces native tool calling):\n"
            "Answer with ONLY one JSON object, no prose and no code fences:\n"
            '  {"tool_calls": [{"name": "<tool name>", "input": {<arguments matching its input_schema>}}]}\n'
            "Call several independent tools in one answer when useful. Send your final answer to the shopper "
            "by calling reply_to_customer, alone. Available tools:\n"
            + json.dumps(catalog, ensure_ascii=False)
        )
        data = _extract_json(self._run(model, system, render_transcript(messages)))
        calls = data.get("tool_calls") if isinstance(data, dict) else None
        if not isinstance(calls, list) or not calls:
            raise LlmError("invalid_json", "expected a non-empty tool_calls list")
        uses = [
            ToolUse(f"cc_{uuid.uuid4().hex[:12]}", str(c.get("name")), c.get("input") if isinstance(c.get("input"), dict) else {})
            for c in calls if isinstance(c, dict) and c.get("name")
        ]
        if not uses:
            raise LlmError("invalid_json", "tool_calls had no named calls")
        return LlmTurn(
            stop_reason="tool_use",
            content=[{"type": "tool_use", "id": u.id, "name": u.name, "input": u.input} for u in uses],
            tool_uses=uses,
            text="",
            model=f"claude-code:{model}",
        )


def render_transcript(messages: List[Dict[str, Any]]) -> str:
    """API-style messages -> a readable transcript (tool calls and results included)."""
    names: Dict[str, str] = {}
    lines: List[str] = []
    for message in messages:
        content = message["content"]
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
        for block in blocks:
            kind = block.get("type")
            if kind == "text":
                speaker = "SHOPPER" if message["role"] == "user" else "ASSISTANT"
                lines.append(f"{speaker}: {block['text']}")
            elif kind == "tool_use":
                names[block["id"]] = block["name"]
                lines.append(f"ASSISTANT CALLED {block['name']}: {json.dumps(block.get('input', {}), ensure_ascii=False)}")
            elif kind == "tool_result":
                label = "ERROR FROM" if block.get("is_error") else "RESULT OF"
                lines.append(f"{label} {names.get(block['tool_use_id'], 'tool')}: {block.get('content')}")
    lines.append("Respond now with the JSON object only.")
    return "\n".join(lines)
