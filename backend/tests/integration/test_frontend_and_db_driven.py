import os
import tempfile
import unittest
from pathlib import Path

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
        self.assertIn("--font-scale", res_tokens.text)
        self.assertIn("--bp-xs", res_tokens.text)
        self.assertIn("--bp-2xl", res_tokens.text)

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

        recs = self.client.get("/api/products/PRD-001/recommendations").json()
        self.assertGreaterEqual(len(recs), 1)
        self.assertEqual(recs[0]["product_id"], "PRD-002")


if __name__ == "__main__":
    unittest.main()
