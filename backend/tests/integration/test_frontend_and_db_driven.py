import os
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import PROJECT_ROOT
from backend.app.database import get_db, set_sync_engine
from backend.app.main import app
from backend.scripts.seed_demo import seed_database


class TestFrontendAndDbDrivenArchitecture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp_dir.name, "test_noir_ui.db")
        cls.engine = create_engine(
            f"sqlite:///{cls.db_path}",
            connect_args={"check_same_thread": False},
        )
        set_sync_engine(cls.engine, "sqlite_ui_test")
        seed_database(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tmp_dir.cleanup()

    def test_01_storefront_and_design_system_assets_served(self) -> None:
        res_html = self.client.get("/storefront/")
        self.assertEqual(res_html.status_code, 200)
        self.assertIn("noir-app", res_html.text)

        res_tokens = self.client.get("/packages/ui/tokens.css")
        self.assertEqual(res_tokens.status_code, 200)
        self.assertIn("--primitive-stone-100", res_tokens.text)
        self.assertIn('[data-theme="dark"]', res_tokens.text)
        self.assertIn("--card-radius", res_tokens.text)
        self.assertIn("--font-scale", res_tokens.text)
        self.assertIn("--bp-xs", res_tokens.text)
        self.assertIn("--bp-2xl", res_tokens.text)
        self.assertIn("prefers-reduced-motion: reduce", res_tokens.text)
        self.assertIn(":focus-visible", res_tokens.text)

        res_theme = self.client.get("/packages/ui/theme.js")
        self.assertEqual(res_theme.status_code, 200)
        self.assertIn("renderIcon", res_theme.text)
        self.assertIn("applyTheme", res_theme.text)
        self.assertIn("getContrastRatio", res_theme.text)

        res_styles = self.client.get("/storefront/styles.css")
        self.assertEqual(res_styles.status_code, 200)
        self.assertIn("@container hero", res_styles.text)
        self.assertIn("@container catalog", res_styles.text)
        self.assertIn("@container card", res_styles.text)
        self.assertIn("@container kpis", res_styles.text)
        self.assertIn("100dvh", res_styles.text)
        self.assertIn("mobile-bottom-nav", res_styles.text)
        self.assertIn("sheet-grabber", res_styles.text)
        self.assertIn("responsive-cards-mobile", res_styles.text)
        self.assertIn("scroll-snap-type: x mandatory", res_styles.text)
        self.assertNotIn("phone-device", res_styles.text)

        res_app = self.client.get("/storefront/app.js")
        self.assertEqual(res_app.status_code, 200)
        self.assertIn("skip-link", res_app.text)
        self.assertIn('aria-live="polite"', res_app.text)
        self.assertIn("aria-invalid", res_app.text)

        res_states = self.client.get("/packages/ui/states.js")
        self.assertEqual(res_states.status_code, 200)
        for required_state in (
            "empty",
            "loading",
            "error",
            "offline",
            "slow_network",
            "no_results",
            "permission_denied",
            "session_expired",
            "form_validation",
            "success",
            "pending_approval",
        ):
            self.assertIn(required_state, res_states.text)

    def test_02_zero_static_fallback_catalog_in_api_client(self) -> None:
        client_js = (PROJECT_ROOT / "frontend" / "packages" / "api" / "client.js").read_text(encoding="utf-8")
        self.assertNotIn("FALLBACK_CATALOG", client_js)
        self.assertIn("/api/products/search", client_js)
        self.assertIn("/api/config/policies", client_js)
        self.assertIn("/api/agents/chat", client_js)

    def test_03_ratings_and_recommendations_are_database_driven(self) -> None:
        prod = self.client.get("/api/products/PRD-001").json()
        self.assertIn("average_rating", prod)
        self.assertIn("review_count", prod)
        self.assertGreaterEqual(prod["review_count"], 1)
        self.assertTrue(len(prod.get("images", [])) >= 1)
        self.assertTrue(prod["images"][0].startswith("https://"))
        self.assertEqual(prod["accent_tag"], "100% European Flax Linen")
        self.assertTrue(len(prod.get("reviews", [])) >= 1)

        # Submit a new review via API and verify DB persistence
        rev_res = self.client.post(
            "/api/products/PRD-001/reviews",
            headers={"Authorization": "Bearer demo_CUS-002"},
            json={"rating": 5, "fit_feedback": "true_to_size", "comment": "Impeccable linen drape and stitching."},
        )
        self.assertIn(rev_res.status_code, (200, 201))
        prod_after = self.client.get("/api/products/PRD-001").json()
        self.assertEqual(prod_after["review_count"], prod["review_count"] + 1)

        recs = self.client.get("/api/products/PRD-001/recommendations").json()
        self.assertGreaterEqual(len(recs), 1)
        self.assertEqual(recs[0]["product_id"], "PRD-002")
        self.assertEqual(recs[0]["relation_type"], "complete_the_look")
        self.assertGreater(recs[0]["recommendation_score"], 0.8)

    def test_04_nextjs_app_router_storefront_structure(self) -> None:
        sf_dir = PROJECT_ROOT / "frontend" / "apps" / "storefront"
        self.assertTrue((sf_dir / "package.json").exists())
        self.assertTrue((sf_dir / "next.config.mjs").exists())
        self.assertTrue((sf_dir / "src" / "app" / "layout.jsx").exists())
        self.assertTrue((sf_dir / "src" / "app" / "page.jsx").exists())
        self.assertTrue((sf_dir / "src" / "app" / "orders" / "page.jsx").exists())
        self.assertTrue((sf_dir / "src" / "app" / "policies" / "page.jsx").exists())
        self.assertTrue((sf_dir / "src" / "app" / "admin" / "page.jsx").exists())

        comp_text = (sf_dir / "src" / "components" / "NoirAtelierNextApp.jsx").read_text(encoding="utf-8")
        self.assertIn("@noir/api/client.js", comp_text)
        self.assertIn("@noir/ui/theme.js", comp_text)
        self.assertIn("@noir/ui/states.js", comp_text)
        self.assertIn("react_steps", comp_text)
        self.assertNotIn("const ACTORS =", comp_text)

        theme_text = (PROJECT_ROOT / "frontend" / "packages" / "ui" / "theme.js").read_text(encoding="utf-8")
        self.assertNotIn("EDITORIAL_ARTWORK_BY_SKU", theme_text)

        app_js_text = (sf_dir / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("const ACTORS =", app_js_text)

    def test_05_config_policies_endpoint_serves_all_ui_entities_from_db(self) -> None:
        cfg = self.client.get("/api/config/policies").json()
        self.assertIn("business_config", cfg)
        self.assertIn("storefront_ui", cfg["business_config"])
        self.assertEqual(cfg["business_config"]["storefront_ui"]["hero_title"], "The New Edit")
        self.assertGreaterEqual(len(cfg["business_config"]["storefront_ui"]["ai_quick_prompts"]), 3)
        self.assertGreaterEqual(len(cfg.get("payment_methods", [])), 3)
        self.assertGreaterEqual(len(cfg.get("coupons", [])), 2)
        self.assertGreaterEqual(len(cfg.get("shipping_zones", [])), 2)
        self.assertGreaterEqual(len(cfg.get("actors", [])), 4)


if __name__ == "__main__":
    unittest.main()
