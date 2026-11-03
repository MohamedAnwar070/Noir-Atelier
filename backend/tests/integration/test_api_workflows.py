import os
import tempfile
import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base, get_db, set_sync_engine
from backend.app.main import app
from backend.app.models import Shipment
from backend.scripts.seed_demo import seed_database


class TestSharedApiWorkflows(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp_dir.name, "test_noir_api.db")
        cls.engine = create_engine(
            f"sqlite:///{cls.db_path}",
            connect_args={"check_same_thread": False},
        )
        set_sync_engine(cls.engine, "sqlite_test")
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

    def _headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_01_health_and_catalog_parity_between_ui_and_agent(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["app"], "Noir Atelier")

        categories = self.client.get("/api/categories")
        self.assertEqual(categories.status_code, 200)
        cat_slugs = {c["slug"] for c in categories.json()}
        self.assertEqual(cat_slugs, {"tops", "shirt", "t-shirt", "outerwear", "overshirt", "dress", "knitwear"})

        ui_meta = self.client.get("/api/catalog/meta", headers=self._headers("demo_CUS-001"))
        agent_meta = self.client.get("/api/catalog/meta", headers=self._headers("svc-catalog"))
        self.assertEqual(ui_meta.status_code, 200)
        self.assertEqual(agent_meta.status_code, 200)
        self.assertEqual(ui_meta.json(), agent_meta.json())

        ui_search = self.client.get(
            "/api/products/search?department=MEN&max_price=3000",
            headers=self._headers("demo_CUS-001"),
        )
        agent_search = self.client.get(
            "/api/products/search?department=MEN&max_price=3000",
            headers=self._headers("svc-catalog"),
        )
        self.assertEqual(ui_search.status_code, 200)
        self.assertEqual(agent_search.status_code, 200)
        self.assertEqual(ui_search.json(), agent_search.json())
        self.assertTrue(any(p["product_id"] == "PRD-001" for p in ui_search.json()))

        inv_list = self.client.get("/api/inventory/list", headers=self._headers("svc-inventory"))
        self.assertEqual(inv_list.status_code, 200)
        self.assertEqual(len(inv_list.json()), 5)

    def test_02_cart_coupon_and_gst_slab_calculation(self) -> None:
        clear = self.client.post("/api/cart/clear", headers=self._headers("demo_CUS-002"))
        self.assertEqual(clear.status_code, 200)

        add_res = self.client.post(
            "/api/cart/add",
            json={"product_id": "PRD-001", "size": "M", "quantity": 1},
            headers=self._headers("demo_CUS-002"),
        )
        self.assertEqual(add_res.status_code, 200)
        cart = add_res.json()
        self.assertEqual(float(cart["subtotal_mrp_inr"]), 2499.0)
        self.assertEqual(float(cart["shipping_fee_inr"]), 0.0)
        self.assertTrue(cart["free_shipping_applied"])
        self.assertEqual(float(cart["items"][0]["gst_rate_pct"]), 5.0)

        coupon_res = self.client.post(
            "/api/coupons/validate",
            json={"code": "ATELIER10", "cart_total_inr": 2499.0},
            headers=self._headers("demo_CUS-002"),
        )
        self.assertEqual(coupon_res.status_code, 200)
        self.assertTrue(coupon_res.json()["valid"])
        self.assertAlmostEqual(float(coupon_res.json()["discount_inr"]), 249.9, places=2)

    def test_03_order_creation_invoice_and_shipment_fulfillment(self) -> None:
        order_res = self.client.post(
            "/api/orders",
            json={
                "customer_id": "CUS-002",
                "items": [{"product_id": "PRD-001", "size": "M", "quantity": 1}],
                "coupon_code": "ATELIER10",
                "payment_method": "upi",
            },
            headers=self._headers("demo_CUS-002"),
        )
        self.assertEqual(order_res.status_code, 201)
        order = order_res.json()
        order_id = order["order_id"]
        self.assertEqual(order["status"], "confirmed")
        self.assertEqual(order["payment_status"], "confirmed")
        self.assertIsNotNone(order["invoice_id"])

        inv_res = self.client.get(
            f"/api/invoices/{order['invoice_id']}",
            headers=self._headers("demo_CUS-002"),
        )
        self.assertEqual(inv_res.status_code, 200)
        self.assertEqual(inv_res.json()["order_id"], order_id)

        ship_res = self.client.post(
            "/api/shipments/schedule",
            json={"order_id": order_id, "carrier": "Noir Express"},
            headers=self._headers("svc-fulfillment"),
        )
        self.assertEqual(ship_res.status_code, 200)
        shipment = ship_res.json()
        self.assertEqual(shipment["status"], "shipped")
        self.assertIsNotNone(shipment["tracking_number"])

    def test_04_agent_rbac_and_customer_isolation(self) -> None:
        forbidden_agent = self.client.post(
            "/api/orders",
            json={
                "customer_id": "CUS-001",
                "items": [{"product_id": "PRD-001", "size": "M", "quantity": 1}],
            },
            headers=self._headers("svc-catalog"),
        )
        self.assertEqual(forbidden_agent.status_code, 403)

        order_c1 = self.client.post(
            "/api/orders",
            json={
                "customer_id": "CUS-001",
                "items": [{"product_id": "PRD-004", "size": "M", "quantity": 1}],
            },
            headers=self._headers("demo_CUS-001"),
        ).json()

        forbidden_customer = self.client.get(
            f"/api/orders/{order_c1['order_id']}",
            headers=self._headers("demo_CUS-002"),
        )
        self.assertEqual(forbidden_customer.status_code, 403)

    def test_05_four_tier_premium_garment_return_and_refund_matrix(self) -> None:
        # Tier 0: Pre-shipment order cancellation auto-refunds
        order_t0 = self.client.post(
            "/api/orders",
            json={
                "customer_id": "CUS-001",
                "items": [{"product_id": "PRD-001", "size": "L", "quantity": 1}],
            },
            headers=self._headers("svc-order"),
        ).json()
        cancel_res = self.client.post(
            f"/api/orders/{order_t0['order_id']}/cancel",
            json={"reason": "Changed mind before dispatch"},
            headers=self._headers("svc-order"),
        )
        self.assertEqual(cancel_res.status_code, 200)
        self.assertEqual(cancel_res.json()["status"], "cancelled")

        # Tier 1: <= ₹5,000 standard garment (PRD-001 at ₹2,499) with tag_intact=True & qc_passed=True -> Auto-approved
        order_t1 = self.client.post(
            "/api/orders",
            json={
                "customer_id": "CUS-001",
                "items": [{"product_id": "PRD-001", "size": "M", "quantity": 1}],
            },
            headers=self._headers("demo_CUS-001"),
        ).json()

        ret_t1 = self.client.post(
            "/api/returns",
            json={
                "order_id": order_t1["order_id"],
                "reason_category": "size_mismatch",
                "customer_notes": "Slightly tight across shoulders",
                "tag_intact": True,
                "qc_passed": True,
            },
            headers=self._headers("svc-returns"),
        )
        self.assertEqual(ret_t1.status_code, 201)
        t1_data = ret_t1.json()
        self.assertEqual(t1_data["approval_tier"], 1)
        self.assertEqual(t1_data["status"], "completed")
        self.assertEqual(t1_data["refund_status"], "processed")

        # Tier 2: ₹5,001 - ₹25,000 luxury garment (PRD-003 at ₹7,999) -> Escalates to Store Manager
        order_t2 = self.client.post(
            "/api/orders",
            json={
                "customer_id": "CUS-001",
                "items": [{"product_id": "PRD-003", "size": "S", "quantity": 1}],
            },
            headers=self._headers("demo_CUS-001"),
        ).json()

        ret_t2 = self.client.post(
            "/api/returns",
            json={
                "order_id": order_t2["order_id"],
                "reason_category": "style_preference",
                "customer_notes": "Draping differs from expectation",
                "tag_intact": True,
                "qc_passed": True,
            },
            headers=self._headers("svc-returns"),
        )
        self.assertEqual(ret_t2.status_code, 201)
        t2_data = ret_t2.json()
        self.assertEqual(t2_data["approval_tier"], 2)
        self.assertEqual(t2_data["status"], "pending_approval")
        self.assertIsNotNone(t2_data["escalation_ticket_id"])

        # Agent cannot approve Tier 2 refund
        agent_approve = self.client.post(
            f"/api/refunds/{t2_data['refund_id']}/approve",
            json={"reason": "Attempted by agent"},
            headers=self._headers("svc-returns"),
        )
        self.assertEqual(agent_approve.status_code, 403)

        # Store Manager approves Tier 2 refund
        mgr_approve = self.client.post(
            f"/api/refunds/{t2_data['refund_id']}/approve",
            json={"reason": "Approved after silk ribbon verification"},
            headers=self._headers("admin_manager"),
        )
        self.assertEqual(mgr_approve.status_code, 200)
        self.assertEqual(mgr_approve.json()["status"], "approved")

        # Process approved refund
        proc_res = self.client.post(
            f"/api/refunds/{t2_data['refund_id']}/process",
            headers=self._headers("svc-returns"),
        )
        self.assertEqual(proc_res.status_code, 200)
        self.assertEqual(proc_res.json()["status"], "processed")

        # Tier 3: > ₹25,000 order (4x PRD-003 = ₹31,996) -> Requires Dual Approval (Manager + Finance Admin)
        order_t3 = self.client.post(
            "/api/orders",
            json={
                "customer_id": "CUS-001",
                "items": [{"product_id": "PRD-003", "size": "S", "quantity": 4}],
            },
            headers=self._headers("demo_CUS-001"),
        ).json()

        ret_t3 = self.client.post(
            "/api/returns",
            json={
                "order_id": order_t3["order_id"],
                "reason_category": "size_mismatch",
                "customer_notes": "Bespoke group order sizing change",
                "tag_intact": True,
                "qc_passed": True,
            },
            headers=self._headers("svc-returns"),
        )
        self.assertEqual(ret_t3.status_code, 201)
        t3_data = ret_t3.json()
        self.assertEqual(t3_data["approval_tier"], 3)

        first_approval = self.client.post(
            f"/api/refunds/{t3_data['refund_id']}/approve",
            json={"reason": "Manager first sign-off"},
            headers=self._headers("admin_manager"),
        )
        self.assertEqual(first_approval.status_code, 200)
        self.assertEqual(first_approval.json()["status"], "awaiting_secondary_approval")

        # Same admin cannot self-approve second stage (segregation of duties)
        duplicate_approval = self.client.post(
            f"/api/refunds/{t3_data['refund_id']}/approve",
            json={"reason": "Manager trying second sign-off"},
            headers=self._headers("admin_manager"),
        )
        self.assertEqual(duplicate_approval.status_code, 403)

        # Finance Admin completes dual approval
        second_approval = self.client.post(
            f"/api/refunds/{t3_data['refund_id']}/approve",
            json={"reason": "Finance Admin second sign-off"},
            headers=self._headers("admin_finance"),
        )
        self.assertEqual(second_approval.status_code, 200)
        self.assertEqual(second_approval.json()["status"], "approved")

    def test_06_analytics_admin_dashboard_and_audit_log(self) -> None:
        ord_analytics = self.client.get(
            "/api/orders/analytics",
            headers=self._headers("svc-analytics"),
        )
        self.assertEqual(ord_analytics.status_code, 200)
        self.assertGreaterEqual(ord_analytics.json()["total_orders"], 1)

        cus_analytics = self.client.get(
            "/api/customers/analytics",
            headers=self._headers("svc-analytics"),
        )
        self.assertEqual(cus_analytics.status_code, 200)
        self.assertEqual(cus_analytics.json()["total_customers"], 2)

        dashboard = self.client.get(
            "/api/admin/dashboard",
            headers=self._headers("admin_manager"),
        )
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("orders", dashboard.json())
        self.assertIn("customers", dashboard.json())

        audit_res = self.client.get(
            "/api/audit/log?limit=25",
            headers=self._headers("admin_manager"),
        )
        self.assertEqual(audit_res.status_code, 200)
        self.assertGreater(len(audit_res.json()), 0)


if __name__ == "__main__":
    unittest.main()
