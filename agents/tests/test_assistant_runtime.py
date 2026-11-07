"""Shopping-assistant runtime: the LLM path, driven by a scripted fake model.

The fake model replaces only the provider call; everything else is real — tools hit
the FastAPI backend in-process through the permission gate on a seeded SQLite copy.
"""

import json
import os
import tempfile
import unittest
from itertools import count
from typing import Any, Dict, List
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents.assistant import AssistantRuntime, ChatContext, ConversationTurn
from agents.client import PlatformApiClient
from agents.gateway import AGENT_ENDPOINT_WHITELIST
from agents.llm import LlmError, LlmTurn, ToolUse
from agents.schemas.state import AgentRole
from backend.app.database import get_db, set_sync_engine
from backend.app.main import app
from backend.app.reference_data import ASSISTANT_AGENT_PERMISSION, STYLIST_AGENT_PERMISSION
from backend.scripts.seed_demo import seed_database

_ids = count(1)
ADMIN = {"Authorization": "Bearer admin_manager"}


def tool_turn(*calls: tuple) -> LlmTurn:
    uses = [ToolUse(f"toolu_{next(_ids)}", name, args) for name, args in calls]
    return LlmTurn(
        stop_reason="tool_use",
        content=[{"type": "tool_use", "id": u.id, "name": u.name, "input": u.input} for u in uses],
        tool_uses=uses,
        text="",
        model="fake-model",
        usage={"input_tokens": 100, "output_tokens": 20},
    )


def reply_turn(message: str, product_ids: List[str] = (), intent: str = "product_search") -> LlmTurn:
    return tool_turn(("reply_to_customer", {
        "message": message, "product_ids": list(product_ids), "follow_up_prompts": ["Show me more like this"],
        "intent": intent, "plan_note": "searched then answered",
    }))


def text_turn(text: str) -> LlmTurn:
    return LlmTurn("end_turn", [{"type": "text", "text": text}], [], text, "fake-model")


class FakeLlm:
    """Plays a script. Each step is an LlmTurn or a function(messages) -> LlmTurn."""

    def __init__(self, steps: List[Any]):
        self.steps = list(steps)
        self.calls: List[Dict[str, Any]] = []

    def converse(self, *, system_blocks, tools, messages, max_tokens, effort="low", tier="reasoning") -> LlmTurn:
        self.calls.append({"tools": [t["name"] for t in tools], "messages": json.loads(json.dumps(messages)),
                           "system": system_blocks})
        if not self.steps:
            raise AssertionError("FakeLlm ran out of script")
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step(messages) if callable(step) else step


def last_tool_results(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    content = messages[-1]["content"]
    return [json.loads(b["content"]) | {"_is_error": b.get("is_error")} for b in content if b.get("type") == "tool_result"]


class TestAssistantRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.engine = create_engine(f"sqlite:///{os.path.join(cls.tmp.name, 'assistant.db')}",
                                   connect_args={"check_same_thread": False})
        set_sync_engine(cls.engine, "sqlite_assistant_test")
        seed_database(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.http = TestClient(app)
        cls.client = PlatformApiClient(in_process_client=cls.http)
        cls.prd001 = cls.http.get("/api/products/PRD-001").json()

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        set_sync_engine(None)
        cls.engine.dispose()
        cls.tmp.cleanup()

    def runtime(self, llm, **kw) -> AssistantRuntime:
        return AssistantRuntime(self.client, llm, persona="Noir Concierge", **kw)

    def ctx(self, customer_id=None, history=()) -> ChatContext:
        return ChatContext(trace_id=f"TRC-TEST{next(_ids):04d}", session_id=f"SES-TEST{next(_ids):06d}",
                           customer_id=customer_id, history=list(history))

    def low_price(self, product) -> float:
        return min(float(v["mrp_inr"]) for v in product["variants"])

    # ------------------------------------------------------------------ happy path

    def test_01_searches_then_answers_with_grounded_cards(self) -> None:
        price = self.low_price(self.prd001)
        llm = FakeLlm([
            tool_turn(("search_products", {"query": "linen shirt"})),
            lambda m: reply_turn(f"The Tailored linen shirt is from ₹{price:,.0f}.",
                                 [last_tool_results(m)[0]["products"][0]["product_id"]]),
        ])
        result = self.runtime(llm).handle("I need a linen shirt", self.ctx())
        self.assertEqual([p["product_id"] for p in result.reply.products], ["PRD-001"])
        self.assertEqual(result.trace.status, "answered")
        self.assertEqual(result.trace.intent, "product_search")
        self.assertTrue(result.trace.evaluation.passed)
        self.assertEqual(result.trace.evaluation.attempts, 1)
        self.assertEqual([c.name for c in result.trace.tool_calls], ["search_products"])
        self.assertEqual(result.trace.tool_calls[0].status, "ok")
        self.assertEqual(result.trace.usage["model_calls"], 2)
        # Cards are catalogue payloads (code-built), not model text.
        self.assertIn("stock_by_size", result.reply.products[0])
        # The vocabulary block was sent and the system prompt is stable.
        self.assertIn("Catalogue vocabulary", llm.calls[0]["system"][1])

    def test_02_plain_text_answer_is_verified_too(self) -> None:
        llm = FakeLlm([text_turn("Hello! What are you shopping for today?")])
        result = self.runtime(llm).handle("hi", self.ctx())
        self.assertEqual(result.trace.status, "answered")
        self.assertEqual(result.reply.products, [])

    # ------------------------------------------------------------------ evaluate: rewrite + template

    def test_03_invented_price_is_rejected_then_rewritten(self) -> None:
        price = self.low_price(self.prd001)
        llm = FakeLlm([
            tool_turn(("search_products", {"query": "linen shirt"})),
            reply_turn("It costs ₹999 today.", ["PRD-001"]),
            reply_turn(f"It is from ₹{price:,.0f}.", ["PRD-001"]),
        ])
        result = self.runtime(llm).handle("linen shirt price?", self.ctx())
        self.assertEqual(result.trace.status, "answered")
        self.assertEqual(result.trace.evaluation.attempts, 2)
        self.assertTrue(any("999" in p for p in result.trace.evaluation.problems))
        feedback = llm.calls[2]["messages"][-1]["content"][0]
        self.assertTrue(feedback["is_error"])
        self.assertIn("could not be verified", feedback["content"])
        self.assertNotIn("999", result.reply.reply)

    def test_04_two_failed_drafts_fall_back_to_a_verified_template(self) -> None:
        llm = FakeLlm([
            tool_turn(("search_products", {"query": "linen shirt"})),
            reply_turn("Only ₹1 for you!", ["PRD-001"]),
            reply_turn("Fine, ₹2 then.", ["PRD-001"]),
        ])
        result = self.runtime(llm).handle("linen shirt", self.ctx())
        self.assertEqual(result.trace.status, "fallback")
        self.assertTrue(result.trace.evaluation.template_used)
        self.assertEqual([p["product_id"] for p in result.reply.products], ["PRD-001"])
        self.assertNotIn("₹1 ", result.reply.reply)
        self.assertIn("Tailored", result.reply.reply)

    def test_05_invented_product_and_internal_details_are_rejected(self) -> None:
        llm = FakeLlm([
            reply_turn("I ran search_products and found PRD-999 for you.", ["PRD-999"]),
            reply_turn("Could you tell me which garment you have in mind?", []),
        ])
        result = self.runtime(llm).handle("something nice", self.ctx())
        problems = " ".join(result.trace.evaluation.problems)
        self.assertIn("PRD-999", problems)
        self.assertIn("internal", problems)
        self.assertEqual(result.trace.status, "answered")
        self.assertEqual(result.reply.products, [])

    def test_06_sold_out_in_the_shoppers_size_is_never_recommended(self) -> None:
        self.http.put("/api/inventory/PRD-003", json={"sizes": {"L": 0}, "reason": "test"}, headers=ADMIN)
        llm = FakeLlm([
            tool_turn(("search_products", {"query": "dress", "size": "L"}), ("get_product", {"product_id": "PRD-003"})),
            reply_turn("This dress is lovely.", ["PRD-003"]),
            reply_turn("That one is sold out in L; shall I look for similar pieces?", []),
        ])
        result = self.runtime(llm).handle("a dress in size L", self.ctx())
        self.assertTrue(any("sold out" in p for p in result.trace.evaluation.problems))
        self.assertEqual(result.reply.products, [])

    # ------------------------------------------------------------------ failure & limits

    def test_07_model_outage_degrades_to_search_reply(self) -> None:
        llm = FakeLlm([LlmError("timeout", "simulated")])
        result = self.runtime(llm).handle("linen shirt for summer", self.ctx())
        self.assertEqual(result.trace.status, "fallback")
        self.assertIn("llm:timeout", result.trace.errors)
        self.assertEqual([p["product_id"] for p in result.reply.products], ["PRD-001"])

    def test_08_tool_budget_is_enforced(self) -> None:
        many = [("search_products", {"query": q}) for q in ("shirt", "dress", "linen", "silk", "kids")]
        llm = FakeLlm([tool_turn(*many), reply_turn("Here is a summary of what I found.", [])])
        result = self.runtime(llm, max_tool_calls=3).handle("show me everything", self.ctx())
        statuses = [c.status for c in result.trace.tool_calls]
        self.assertEqual(statuses.count("ok"), 3)
        self.assertEqual(statuses.count("budget"), 2)

    def test_09_deadline_ends_the_turn_safely(self) -> None:
        ticks = iter([0.0, 0.0, 100.0, 100.0, 100.0, 100.0, 100.0])
        llm = FakeLlm([tool_turn(("search_products", {"query": "shirt"})), reply_turn("never sent", [])])
        result = self.runtime(llm, deadline_sec=5, clock=lambda: next(ticks, 100.0)).handle("shirt", self.ctx())
        self.assertIn("budget:deadline", result.trace.errors)
        self.assertEqual(result.trace.status, "fallback")

    def test_10_invalid_tool_input_is_returned_to_the_model(self) -> None:
        llm = FakeLlm([
            tool_turn(("search_products", {"colors": ["sparkly-unicorn"]})),
            lambda m: reply_turn("Which colour family would you like?", []) if last_tool_results(m)[0]["_is_error"] else None,
        ])
        result = self.runtime(llm).handle("sparkly unicorn shirt", self.ctx())
        self.assertEqual(result.trace.tool_calls[0].status, "invalid")
        self.assertIn("Valid values", result.trace.tool_calls[0].error)

    # ------------------------------------------------------------------ security & scope

    def test_11_guests_never_get_order_tools(self) -> None:
        guest, shopper = FakeLlm([text_turn("Hi!")]), FakeLlm([text_turn("Hi!")])
        self.runtime(guest).handle("hello", self.ctx())
        self.runtime(shopper).handle("hello", self.ctx(customer_id="CUS-001"))
        self.assertNotIn("get_order", guest.calls[0]["tools"])
        self.assertIn("get_order", shopper.calls[0]["tools"])

    def test_12_a_shopper_cannot_read_another_shoppers_order(self) -> None:
        order = self.http.post(
            "/api/orders", json={"customer_id": "CUS-001", "items": [{"product_id": "PRD-001", "size": "M", "quantity": 1}]},
            headers={"Authorization": "Bearer demo_CUS-001"},
        ).json()
        llm = FakeLlm([
            tool_turn(("get_order", {"order_id": order["order_id"]})),
            reply_turn("I can only look up your own orders.", [], intent="order_status"),
        ])
        result = self.runtime(llm).handle(f"status of {order['order_id']}?", self.ctx(customer_id="CUS-002"))
        call = result.trace.tool_calls[0]
        self.assertEqual((call.status, call.http_status), ("denied", 403))

        # The owner gets their order, and the pickup code never reaches the model.
        owner = FakeLlm([tool_turn(("get_order", {"order_id": order["order_id"]})),
                         lambda m: reply_turn(f"Your order {order['order_id']} is confirmed.", [], intent="order_status")])
        mine = self.runtime(owner).handle("my order?", self.ctx(customer_id="CUS-001"))
        self.assertEqual(mine.trace.status, "answered")
        self.assertNotIn("pickup_code", json.dumps(owner.calls[1]["messages"]))

    def test_13_history_is_sent_as_plain_text(self) -> None:
        llm = FakeLlm([text_turn("Sure — which colour?")])
        history = [ConversationTurn("user", "I like linen"), ConversationTurn("assistant", "Lovely choice.", ["PRD-001"])]
        self.runtime(llm).handle("something similar", self.ctx(history=history))
        first = llm.calls[0]["messages"]
        self.assertEqual(first[0], {"role": "user", "content": "I like linen"})
        self.assertIn("PRD-001", first[1]["content"])

    def test_14_client_and_server_permission_lists_are_identical(self) -> None:
        for role, grant in ((AgentRole.ASSISTANT.value, ASSISTANT_AGENT_PERMISSION),
                            (AgentRole.STYLIST.value, STYLIST_AGENT_PERMISSION)):
            client_paths = {path for _, path in AGENT_ENDPOINT_WHITELIST[role]}
            self.assertEqual(client_paths, set(grant["allowed_endpoints"]), role)
            self.assertTrue(grant["customer_scoped"])
        self.assertTrue(all(m == "GET" or "profile" in p for m, p in AGENT_ENDPOINT_WHITELIST[AgentRole.ASSISTANT.value]))

    # ------------------------------------------------------------------ the HTTP endpoint

    def test_15_chat_endpoint_returns_only_shopper_fields_and_logs_internally(self) -> None:
        price = self.low_price(self.prd001)
        llm = FakeLlm([
            tool_turn(("search_products", {"query": "linen shirt"})),
            reply_turn(f"From ₹{price:,.0f}.", ["PRD-001"]),
            text_turn("Happy to help with sizing too."),
        ])
        with mock.patch("backend.app.api.agents.build_llm", return_value=llm):
            res = self.http.post("/api/agents/chat", json={"message": "linen shirt", "session_id": "SES-HTTPTEST01"},
                                 headers={"Authorization": "Bearer demo_CUS-001"})
            second = self.http.post("/api/agents/chat", json={"message": "and sizing?", "session_id": "SES-HTTPTEST01"},
                                    headers={"Authorization": "Bearer demo_CUS-001"})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(set(body), {"reference_id", "session_id", "status", "persona", "reply", "products",
                                     "follow_up_prompts", "action_feedback", "stylist_mode", "stylist_notes",
                                     "total_mrp_inr"})
        for leaked in ("tool", "trace", "react", "svc-", "plan_note", "intent"):
            self.assertNotIn(leaked, json.dumps({k: v for k, v in body.items() if k != "products"}).lower())

        # Second turn saw the first as history.
        self.assertEqual(second.status_code, 200)
        self.assertEqual(llm.calls[-1]["messages"][0]["content"], "linen shirt")

        trace = self.http.get(f"/api/admin/agents/traces/{body['reference_id']}", headers=ADMIN).json()
        self.assertEqual(trace["status"], "answered")
        self.assertEqual(trace["customer_id"], "CUS-001")
        self.assertEqual(trace["tool_calls"][0]["name"], "search_products")
        self.assertEqual(trace["intent"], "product_search")
        denied = self.http.get(f"/api/admin/agents/traces/{body['reference_id']}",
                               headers={"Authorization": "Bearer demo_CUS-001"})
        self.assertEqual(denied.status_code, 403)

    def test_17_stream_sends_progress_then_the_verified_reply(self) -> None:
        price = self.low_price(self.prd001)
        llm = FakeLlm([
            tool_turn(("search_products", {"query": "linen shirt"})),
            reply_turn(f"From ₹{price:,.0f}.", ["PRD-001"]),
        ])
        with mock.patch("backend.app.api.agents.build_llm", return_value=llm):
            res = self.http.post("/api/agents/chat/stream", json={"message": "linen shirt", "session_id": "SES-STREAMTEST1"},
                                 headers={"Authorization": "Bearer demo_CUS-001"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.headers["content-type"].startswith("text/event-stream"))
        events = []
        for block in res.text.split("\n\n"):
            lines = dict(line.split(": ", 1) for line in block.splitlines() if line and not line.startswith(":"))
            if "event" in lines:
                events.append((lines["event"], json.loads(lines["data"])))
        kinds = [e for e, _ in events]
        self.assertEqual(kinds[-1], "reply")
        labels = [d["label"] for e, d in events if e == "status"]
        self.assertEqual(labels, ["Understanding your request…", "Searching the collection…", "Checking the details…"])
        self.assertFalse(any("_" in label for label in labels))  # never a tool name
        reply = events[-1][1]
        self.assertEqual([p["product_id"] for p in reply["products"]], ["PRD-001"])
        self.assertNotIn("tool_calls", reply)

    def test_16_another_shoppers_session_history_is_never_loaded(self) -> None:
        llm = FakeLlm([text_turn("Hi!"), text_turn("Hello!")])
        with mock.patch("backend.app.api.agents.build_llm", return_value=llm):
            self.http.post("/api/agents/chat", json={"message": "my secret note", "session_id": "SES-SHAREDX01"},
                           headers={"Authorization": "Bearer demo_CUS-001"})
            self.http.post("/api/agents/chat", json={"message": "hi", "session_id": "SES-SHAREDX01"},
                           headers={"Authorization": "Bearer demo_CUS-002"})
        self.assertNotIn("my secret note", json.dumps(llm.calls[-1]["messages"]))


if __name__ == "__main__":
    unittest.main()
