import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents.client import PlatformApiClient
from agents.main import NoirAtelierMultiAgentOrchestrator
from agents.schemas.state import AgentRequest
from agents.stylist import StylistPipeline
from agents.stylist.contracts import (
    Draft,
    Plan,
    PlanAction,
    ProductFact,
    ProfileUpdate,
    StyleProfile,
    Verdict,
    WorkerResults,
)
from agents.stylist.critic import review
from agents.stylist.money import amounts_in, format_inr
from agents.stylist.planner import plan_turn
from agents.stylist.profile_ops import merge
from backend.app.database import get_db, set_sync_engine
from backend.app.main import app
from backend.scripts.seed_demo import seed_database


class TestStylistPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(cls.tmp_dir.name) / "stylist_test.db"
        cls.engine = create_engine(
            f"sqlite:///{db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        set_sync_engine(cls.engine, "sqlite_stylist_test")
        seed_database(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.test_client = TestClient(app)
        cls.api_client = PlatformApiClient(in_process_client=cls.test_client)
        cls.orchestrator = NoirAtelierMultiAgentOrchestrator(client=cls.api_client)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        cls.engine.dispose()
        set_sync_engine(None)
        cls.tmp_dir.cleanup()

    def setUp(self) -> None:
        self.pipeline = StylistPipeline(
            client=self.api_client,
            delegate=self.orchestrator.invoke,
            llm=None,  # Deterministic offline rule-based mode
        )

    def test_01_currency_and_budget_parsing(self) -> None:
        self.assertEqual(amounts_in("under ₹4,000"), [4000.0])
        self.assertEqual(amounts_in("budget is ₹15,000 and max INR 25,000"), [15000.0, 25000.0])
        self.assertEqual(amounts_in("no price mentioned"), [])
        self.assertEqual(format_inr(150000.0), "₹1,50,000")
        self.assertEqual(format_inr(2399.5), "₹2,399.50")

    def test_02_profile_merging_across_turns(self) -> None:
        # Turn 1: wedding in calm colours with 25k budget
        up1 = ProfileUpdate(
            occasion="wedding",
            recipient="sister",
            palettes=["muted"],
            budget_max_inr=25000.0,
        )
        p1 = merge(StyleProfile(), up1)
        self.assertEqual(p1.occasion, "wedding")
        self.assertEqual(p1.recipient, "sister")
        self.assertEqual(p1.budget_max_inr, 25000.0)
        self.assertIn("muted", p1.palettes)

        # Turn 2: refinement without resetting memory ("darker, no polyester")
        up2 = ProfileUpdate(
            palettes=["dark"],
        )
        up2.avoid.materials.append("polyester")
        p2 = merge(p1, up2)

        # Retains occasion and recipient from Turn 1
        self.assertEqual(p2.occasion, "wedding")
        self.assertEqual(p2.recipient, "sister")
        self.assertEqual(p2.budget_max_inr, 25000.0)
        # Includes new palette and avoidance
        self.assertIn("dark", p2.palettes)
        self.assertIn("polyester", p2.avoid.materials)

    def test_03_critic_rejects_hallucinations_and_overbudget(self) -> None:
        fact = ProductFact(
            product_id="PRD-001",
            name="Cashmere Overcoat",
            department="Men",
            category="Outerwear",
            color="Noir Black",
            materials=["Cashmere"],
            price_min=25000.0,
            price_max=25000.0,
            stock=5,
            sizes=["M", "L"],
            gst_rate_pct=12,
        )
        results = WorkerResults(
            products=[fact],
            total_matches=1,
            display_items={"PRD-001": {"product_id": "PRD-001", "name": "Cashmere Overcoat"}},
        )
        profile = StyleProfile(budget_max_inr=30000.0)
        pricing = {"free_shipping_threshold_inr": 1999.0, "default_shipping_fee_inr": 0.0}

        # 1. Valid draft passes
        draft_ok = Draft(
            reply="I recommend our Cashmere Overcoat (PRD-001) for ₹25,000.",
            product_ids=["PRD-001"],
            source="template",
        )
        v_ok = review(draft_ok, results, profile, pricing)
        self.assertTrue(v_ok.passed)

        # 2. Fabricated product ID fails
        draft_hallucinated = Draft(
            reply="I recommend our Silk Kimono (PRD-999) for ₹12,000.",
            product_ids=["PRD-999"],
            source="template",
        )
        v_hallucinated = review(draft_hallucinated, results, profile, pricing)
        self.assertFalse(v_hallucinated.passed)
        self.assertTrue(any("PRD-999" in p for p in v_hallucinated.problems))

        # 3. Over-budget recommendation fails
        tight_profile = StyleProfile(budget_max_inr=20000.0)
        v_overbudget = review(draft_ok, results, tight_profile, pricing)
        self.assertFalse(v_overbudget.passed)
        self.assertTrue(any("budget" in p.lower() for p in v_overbudget.problems))

    def test_04_alternatives_vs_attribute_refinement(self) -> None:
        profile = StyleProfile(occasion="wedding", budget_max_inr=50000.0)
        prev_ids = ["PRD-001", "PRD-002"]

        # User wants alternatives: exclude_previous should be True
        plan_alt = plan_turn(
            profile=profile,
            update=ProfileUpdate(),
            last_shown_ids=prev_ids,
            message="Show me something else, other options",
        )
        self.assertEqual(plan_alt.action, PlanAction.REFINE)
        self.assertTrue(plan_alt.exclude_previous)

        # User just refines attribute ("in black"): exclude_previous should be False
        update_refine = ProfileUpdate(colors=["black"])
        plan_refine = plan_turn(
            profile=profile,
            update=update_refine,
            last_shown_ids=prev_ids,
            message="Show it in black",
        )
        self.assertEqual(plan_refine.action, PlanAction.REFINE)
        self.assertFalse(plan_refine.exclude_previous)

    def test_05_stylist_handles_live_request_with_grounded_products(self) -> None:
        req = AgentRequest(
            message="Show me Himalayan cashmere garments under ₹1,00,000",
            session_id="stylist-test-sess-001",
        )
        res = self.pipeline.handle(req)
        self.assertEqual(res.routed_agent, "stylist_agent")
        self.assertEqual(res.service_account, "svc-stylist")
        self.assertIn("orchestrator_workers", res.active_patterns)
        self.assertIn("evaluator_optimizer", res.active_patterns)
        # All returned products must have valid IDs from database
        products = res.data.get("products", [])
        self.assertGreater(len(products), 0)
        for p in products:
            self.assertTrue(p["product_id"].startswith("PRD-"))
            price = p.get("min_price") or p.get("mrp_inr") or p.get("price") or 0.0
            self.assertLessEqual(float(price), 100000.0)

    def test_06_stylist_delegates_non_shopping_intents(self) -> None:
        # Orders / Returns should be delegated to specialist agent
        order_req = AgentRequest(
            message="Where is my order ORD-2026-001?",
            session_id="stylist-test-sess-002",
        )
        order_res = self.pipeline.handle(order_req)
        self.assertEqual(order_res.routed_agent, "order_agent")

        # Returns policy
        ret_req = AgentRequest(
            message="What is the 7-day security seal return policy?",
            session_id="stylist-test-sess-003",
        )
        ret_res = self.pipeline.handle(ret_req)
        self.assertEqual(ret_res.routed_agent, "config_agent")

    def test_07_profile_persistence_endpoint_lifecycle(self) -> None:
        session_id = "stylist-sess-integration-99"
        # Writes must come from the stylist service account
        agent_headers = {"Authorization": "Bearer svc-stylist", "x-on-behalf-of": "CUS-001"}
        customer_headers = {"Authorization": "Bearer demo_CUS-001"}

        # 1. Put profile via stylist agent
        put_res = self.test_client.put(
            f"/api/agents/sessions/{session_id}/profile",
            json={
                "profile": {
                    "occasion": "evening",
                    "recipient": "self",
                    "palettes": ["dark"],
                    "budget_max_inr": 85000,
                    "avoid": {"materials": ["silk"]},
                }
            },
            headers=agent_headers,
        )
        self.assertEqual(put_res.status_code, 200)

        # 2. Get profile via customer
        get_res = self.test_client.get(
            f"/api/agents/sessions/{session_id}/profile",
            headers=customer_headers,
        )
        self.assertEqual(get_res.status_code, 200)
        prof = get_res.json()["profile"]
        self.assertEqual(prof["occasion"], "evening")
        self.assertEqual(float(prof["budget_max_inr"]), 85000.0)
        self.assertIn("silk", prof["avoid"]["materials"])

        # 3. Clear profile via customer
        del_res = self.test_client.delete(
            f"/api/agents/sessions/{session_id}/profile",
            headers=customer_headers,
        )
        self.assertEqual(del_res.status_code, 200)

        # 4. Verify cleared
        get_after = self.test_client.get(
            f"/api/agents/sessions/{session_id}/profile",
            headers=customer_headers,
        )
        self.assertEqual(get_after.status_code, 200)
        cleared_prof = get_after.json()["profile"]
        self.assertIsNone(cleared_prof.get("occasion"))
        self.assertIsNone(cleared_prof.get("budget_max_inr"))
        self.assertEqual(get_after.json().get("turns"), 0)


if __name__ == "__main__":
    unittest.main()
