"""The local Claude Code provider: JSON tool protocol, transcript rendering, production refusal.

No CLI is started here — `_run` is replaced, so these tests are fast and free.
"""

import unittest
from unittest import mock

from agents.llm import gateway as gateway_module
from agents.llm.claude_code import ClaudeCodeGateway, _extract_json, render_transcript
from agents.llm.gateway import LlmError


def gateway_with(replies):
    with mock.patch("agents.llm.claude_code.find_claude_cli", return_value="claude.exe"):
        gw = ClaudeCodeGateway(fast_model="claude-haiku-5-5", reasoning_model="claude-sonnet-5-5", timeout_sec=5)
    gw._run = mock.Mock(side_effect=list(replies))
    return gw


class TestClaudeCodeProvider(unittest.TestCase):
    def test_tool_calls_become_an_llm_turn(self) -> None:
        gw = gateway_with(['```json\n{"tool_calls": [{"name": "search_products", "input": {"query": "linen"}},'
                           ' {"name": "get_store_policies", "input": {"topic": "returns"}}]}\n```'])
        turn = gw.converse(system_blocks=["rules"], tools=[{"name": "search_products", "description": "d", "input_schema": {}}],
                           messages=[{"role": "user", "content": "linen?"}], max_tokens=100)
        self.assertEqual(turn.stop_reason, "tool_use")
        self.assertEqual([u.name for u in turn.tool_uses], ["search_products", "get_store_policies"])
        self.assertEqual(turn.content[0]["type"], "tool_use")
        self.assertTrue(turn.model.startswith("claude-code:"))
        system = gw._run.call_args.args[1]
        self.assertIn("TOOL PROTOCOL", system)
        self.assertIn("search_products", system)

    def test_unusable_output_raises_llm_error_so_the_runtime_falls_back(self) -> None:
        for bad in ("Sure! Here are some shirts.", '{"tool_calls": []}', '{"answer": "hi"}'):
            gw = gateway_with([bad])
            with self.assertRaises(LlmError):
                gw.converse(system_blocks=["r"], tools=[], messages=[{"role": "user", "content": "x"}], max_tokens=10)

    def test_generate_json_tolerates_prose_around_the_object(self) -> None:
        gw = gateway_with(['Here you go: {"ok": true} hope that helps'])
        self.assertEqual(gw.generate_json(tier="fast", system_blocks=["s"], user="u", schema={}, max_tokens=10), {"ok": True})
        self.assertEqual(_extract_json('{"a": 1}'), {"a": 1})

    def test_transcript_names_each_tool_result(self) -> None:
        text = render_transcript([
            {"role": "user", "content": [{"type": "text", "text": "find linen"}]},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "search_products", "input": {"query": "linen"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": '{"returned": 1}', "is_error": False}]},
        ])
        self.assertIn("SHOPPER: find linen", text)
        self.assertIn('ASSISTANT CALLED search_products: {"query": "linen"}', text)
        self.assertIn('RESULT OF search_products: {"returned": 1}', text)

    def test_refused_in_production_and_switchable_by_settings_only(self) -> None:
        def settings(env, provider):
            return mock.Mock(use_live_llm=True, llm_provider=provider, app_env=env, llm_model_fast="h",
                             llm_model_reasoning="s", llm_timeout_sec=5, claude_cli_path="", anthropic_api_key="")

        for env, expect_none in (("production", True), ("PROD", True), ("development", False)):
            gateway_module.build_llm.cache_clear()
            with mock.patch("backend.app.config.get_settings", return_value=settings(env, "claude_code")), \
                 mock.patch("agents.llm.claude_code.find_claude_cli", return_value="claude.exe"):
                llm = gateway_module.build_llm()
            self.assertEqual(llm is None, expect_none, env)
        gateway_module.build_llm.cache_clear()


if __name__ == "__main__":
    unittest.main()
