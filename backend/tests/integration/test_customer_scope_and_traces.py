"""Customer-scoped agents may only touch the records of the shopper they act for;
internal assistant traces and the full agent registry are staff-only."""

import os
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import get_db, set_sync_engine
from backend.app.main import app
from backend.scripts.seed_demo import seed_database


def agent(account: str, shopper: str = None) -> dict:
    headers = {"Authorization": f"Bearer {account}"}
    if shopper:
        headers["X-On-Behalf-Of"] = shopper
    return headers


CUS1 = {"Authorization": "Bearer demo_CUS-001"}
MANAGER = {"Authorization": "Bearer admin_manager"}
FINANCE = {"Authorization": "Bearer admin_finance"}


class TestCustomerScopeAndTraces(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.engine = create_engine(f"sqlite:///{os.path.join(cls.tmp.name, 'scope.db')}",
                                   connect_args={"check_same_thread": False})
        set_sync_engine(cls.engine, "sqlite_scope_test")
        seed_database(cls.engine)
        Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

        def override_get_db():
            db = Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
        cls.order_id = cls.client.post(
            "/api/orders",
            json={"customer_id": "CUS-001", "items": [{"product_id": "PRD-001", "size": "M", "quantity": 1}]},
            headers=CUS1,
        ).json()["order_id"]

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        set_sync_engine(None)
        cls.engine.dispose()
        cls.tmp.cleanup()

    def test_01_assistant_reads_only_the_shopper_it_acts_for(self) -> None:
        get = self.client.get
        self.assertEqual(get(f"/api/orders/{self.order_id}", headers=agent("svc-assistant", "CUS-001")).status_code, 200)
        self.assertEqual(get(f"/api/orders/{self.order_id}", headers=agent("svc-assistant", "CUS-002")).status_code, 403)
        self.assertEqual(get(f"/api/orders/{self.order_id}", headers=agent("svc-assistant")).status_code, 403)

        own = get("/api/orders", headers=agent("svc-assistant", "CUS-001"))
        self.assertEqual(own.status_code, 200)
        self.assertTrue(all(o["customer_id"] == "CUS-001" for o in own.json()))
        self.assertEqual(get("/api/orders", params={"customer_id": "CUS-002"},
                             headers=agent("svc-assistant", "CUS-001")).status_code, 403)
        self.assertEqual(get("/api/orders", headers=agent("svc-assistant")).status_code, 403)

    def test_02_assistant_cannot_reach_write_or_staff_endpoints(self) -> None:
        body = {"product_id": "PRD-001", "size": "M", "quantity": 1}
        self.assertEqual(self.client.post("/api/cart/add", json=body, headers=agent("svc-assistant", "CUS-001")).status_code, 403)
        self.assertEqual(self.client.get("/api/inventory/list", headers=agent("svc-assistant", "CUS-001")).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/agents/traces", headers=agent("svc-assistant", "CUS-001")).status_code, 403)

    def test_03_operations_agents_keep_their_access(self) -> None:
        # Not customer-scoped: back-office agents still work without a shopper.
        self.assertEqual(self.client.get(f"/api/orders/{self.order_id}", headers=agent("svc-order")).status_code, 200)
        # ...but never for a different shopper than the one they claim to act for.
        self.assertEqual(self.client.get(f"/api/orders/{self.order_id}", headers=agent("svc-order", "CUS-002")).status_code, 403)

    def test_04_session_profiles_are_bound_to_their_shopper(self) -> None:
        path = "/api/agents/sessions/SES-SCOPETEST01/profile"
        saved = self.client.put(path, json={"profile": {"sizes": ["M"]}}, headers=agent("svc-assistant", "CUS-001"))
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(self.client.get(path, headers=agent("svc-assistant", "CUS-002")).status_code, 403)
        self.assertEqual(self.client.put(path, json={"profile": {"sizes": ["L"]}},
                                         headers=agent("svc-assistant", "CUS-002")).status_code, 403)

    def test_05_traces_and_full_registry_are_staff_only(self) -> None:
        self.client.post("/api/agents/chat", json={"message": "linen shirt", "session_id": "SES-SCOPETEST02"})
        self.assertEqual(self.client.get("/api/admin/agents/traces", headers=MANAGER).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/agents/traces", headers=CUS1).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/agents/traces", headers=FINANCE).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/agents/traces").status_code, 401)

        public = self.client.get("/api/agents/registry").json()
        self.assertTrue(all(set(item) == {"agent_name", "persona"} for item in public))
        full = self.client.get("/api/admin/agents/registry", headers=MANAGER)
        self.assertEqual(full.status_code, 200)
        self.assertIn("system_prompt", full.json()[0])
        self.assertEqual(self.client.get("/api/admin/agents/registry", headers=CUS1).status_code, 403)

    def test_06_guest_trace_is_recorded_without_customer_and_session_ids_are_never_shared(self) -> None:
        first = self.client.post("/api/agents/chat", json={"message": "silk dress"}).json()
        second = self.client.post("/api/agents/chat", json={"message": "silk dress"}).json()
        # No session id sent: each gets its own (the old shared default is never reused).
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertNotEqual(first["session_id"], "SES-1001")
        trace = self.client.get(f"/api/admin/agents/traces/{first['reference_id']}", headers=MANAGER).json()
        self.assertIsNone(trace["customer_id"])
        self.assertEqual(trace["runtime"], "offline")
        # A customer_id in the body never grants identity.
        spoof = self.client.post("/api/agents/chat", json={"message": "my orders", "customer_id": "CUS-001"}).json()
        spoof_trace = self.client.get(f"/api/admin/agents/traces/{spoof['reference_id']}", headers=MANAGER).json()
        self.assertIsNone(spoof_trace["customer_id"])


if __name__ == "__main__":
    unittest.main()
