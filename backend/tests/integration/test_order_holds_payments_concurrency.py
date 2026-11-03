from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.config import get_settings
from backend.app.database import get_db, set_sync_engine
from backend.app.main import app
from backend.app.models import Inventory, Order
from backend.app.utils.hmac_auth import sign_payload
from backend.scripts.seed_demo import seed_database


class TestOrderHoldsPaymentsConcurrency(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_noir_holds.db")
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        set_sync_engine(self.engine, "sqlite_test")
        seed_database(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.secret = get_settings().webhook_secret

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.tmp_dir.cleanup()

    def _headers(self, token: str = "demo_cust_001", extra: dict | None = None) -> dict:
        hdrs = {"Authorization": f"Bearer {token}"}
        if extra:
            hdrs.update(extra)
        return hdrs

    def _send_webhook(self, payload: dict, secret: str | None = None, prefix_sha256: bool = True):
        raw_body = json.dumps(payload)
        sig = sign_payload(raw_body, secret or self.secret)
        header_val = f"sha256={sig}" if prefix_sha256 else sig
        return self.client.post(
            "/api/payments/webhook",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Signature": header_val},
        )

    def _set_stock(self, product_id: str, available: int, reserved: int = 0) -> None:
        with self.SessionLocal() as db:
            inv = db.scalar(select(Inventory).where(Inventory.product_id == product_id))
            assert inv is not None
            inv.quantity_available = available
            inv.quantity_reserved = reserved
            db.commit()

    def _get_stock(self, product_id: str) -> tuple[int, int]:
        with self.SessionLocal() as db:
            inv = db.scalar(select(Inventory).where(Inventory.product_id == product_id))
            assert inv is not None
            return int(inv.quantity_available), int(inv.quantity_reserved)

    def test_01_validation_and_duplicate_line_merging(self) -> None:
        res_empty = self.client.post(
            "/api/orders/hold",
            headers=self._headers(),
            json={"items": []},
        )
        self.assertEqual(res_empty.status_code, 400)
        self.assertEqual(res_empty.json()["error"]["code"], "validation_error")

        res_dup_exceed = self.client.post(
            "/api/orders/hold",
            headers=self._headers(),
            json={
                "items": [
                    {"product_id": "PRD-001", "size": "M", "quantity": 60},
                    {"product_id": "PRD-001", "size": "M", "quantity": 60},
                ]
            },
        )
        self.assertEqual(res_dup_exceed.status_code, 400)
        self.assertIn("exceeds 99", res_dup_exceed.json()["error"]["message"])

        avail_before, _ = self._get_stock("PRD-001")
        res_dup_valid = self.client.post(
            "/api/orders/hold",
            headers=self._headers(),
            json={
                "items": [
                    {"product_id": "PRD-001", "size": "M", "quantity": 1},
                    {"product_id": "PRD-001", "size": "M", "quantity": 2},
                ]
            },
        )
        self.assertEqual(res_dup_valid.status_code, 201)
        body = res_dup_valid.json()
        self.assertEqual(body["status"], "pending")
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["quantity"], 3)
        self.assertGreater(body["expires_in_seconds"], 0)
        self.assertIn(body["locker_number"], range(1, 25))
        self.assertEqual(len(body["pickup_code"]), 4)

        avail_after, res_after = self._get_stock("PRD-001")
        self.assertEqual(avail_after, avail_before - 3)
        self.assertEqual(res_after, 3)

    def test_02_multi_item_shortage_rolls_back_all_and_reports_shortages(self) -> None:
        self._set_stock("PRD-005", 1)
        p1_before, _ = self._get_stock("PRD-001")

        res = self.client.post(
            "/api/orders/hold",
            headers=self._headers(),
            json={
                "items": [
                    {"product_id": "PRD-001", "size": "M", "quantity": 1},
                    {"product_id": "PRD-005", "size": "L", "quantity": 5},
                ]
            },
        )
        self.assertEqual(res.status_code, 409)
        err = res.json()["error"]
        self.assertEqual(err["code"], "insufficient_stock")
        shortages = err["details"]["shortages"]
        self.assertEqual(len(shortages), 1)
        self.assertEqual(shortages[0]["product_id"], "PRD-005")
        self.assertEqual(shortages[0]["requested"], 5)
        self.assertEqual(shortages[0]["available"], 1)

        p1_after, _ = self._get_stock("PRD-001")
        self.assertEqual(p1_after, p1_before)

    def test_03_ten_concurrent_buyers_for_last_two_units(self) -> None:
        self._set_stock("PRD-005", 2)

        def attempt_buy(idx: int) -> int:
            with TestClient(app) as local_client:
                resp = local_client.post(
                    "/api/orders/hold",
                    headers=self._headers("demo_cust_001"),
                    json={"items": [{"product_id": "PRD-005", "size": "M", "quantity": 1}]},
                )
                return resp.status_code

        with ThreadPoolExecutor(max_workers=10) as pool:
            statuses = list(pool.map(attempt_buy, range(10)))

        self.assertEqual(statuses.count(201), 2)
        self.assertEqual(statuses.count(409), 8)
        avail, reserved = self._get_stock("PRD-005")
        self.assertEqual(avail, 0)
        self.assertEqual(reserved, 2)

    def test_04_hold_cancel_idempotency_and_expiry_sweeper(self) -> None:
        avail_before, _ = self._get_stock("PRD-002")
        hold_res = self.client.post(
            "/api/orders/hold",
            headers=self._headers(),
            json={"items": [{"product_id": "PRD-002", "size": "M", "quantity": 2}]},
        )
        self.assertEqual(hold_res.status_code, 201)
        order_id = hold_res.json()["order_id"]

        c1 = self.client.post(f"/api/orders/{order_id}/cancel", headers=self._headers())
        self.assertEqual(c1.status_code, 200)
        self.assertEqual(c1.json()["status"], "cancelled")

        c2 = self.client.post(f"/api/orders/{order_id}/cancel", headers=self._headers())
        self.assertEqual(c2.status_code, 200)
        self.assertEqual(c2.json()["status"], "cancelled")

        avail_after, res_after = self._get_stock("PRD-002")
        self.assertEqual(avail_after, avail_before)
        self.assertEqual(res_after, 0)

        hold2 = self.client.post(
            "/api/orders/hold",
            headers=self._headers(),
            json={"items": [{"product_id": "PRD-002", "size": "M", "quantity": 1}]},
        )
        oid2 = hold2.json()["order_id"]
        with self.SessionLocal() as db:
            ord_row = db.scalar(select(Order).where(Order.order_id == oid2))
            assert ord_row is not None
            ord_row.hold_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
            db.commit()

        sweep_res = self.client.post("/api/orders/sweep-expired")
        self.assertEqual(sweep_res.status_code, 200)
        self.assertIn(oid2, sweep_res.json()["expired_order_ids"])

        cancel_expired = self.client.post(f"/api/orders/{oid2}/cancel", headers=self._headers())
        self.assertEqual(cancel_expired.status_code, 409)
        self.assertEqual(cancel_expired.json()["error"]["code"], "not_cancellable")

    def test_05_product_order_exact_idempotency_key(self) -> None:
        avail_before, _ = self._get_stock("PRD-003")
        payload = {
            "items": [{"product_id": "PRD-003", "size": "L", "quantity": 1}],
            "request_key": "auto",
        }
        r1 = self.client.post("/api/orders", headers=self._headers(), json=payload)
        self.assertEqual(r1.status_code, 201)
        r2 = self.client.post("/api/orders", headers=self._headers(), json=payload)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r1.json()["order_id"], r2.json()["order_id"])

        avail_after, _ = self._get_stock("PRD-003")
        self.assertEqual(avail_after, avail_before - 1)

        hdr_key = "idem-header-prd-003-test"
        h1 = self.client.post(
            "/api/orders/hold",
            headers=self._headers(extra={"Idempotency-Key": hdr_key}),
            json={"items": [{"product_id": "PRD-003", "size": "M", "quantity": 1}]},
        )
        h2 = self.client.post(
            "/api/orders/hold",
            headers=self._headers(extra={"Idempotency-Key": hdr_key}),
            json={"items": [{"product_id": "PRD-003", "size": "M", "quantity": 1}]},
        )
        self.assertEqual(h1.status_code, 201)
        self.assertEqual(h2.status_code, 201)
        self.assertEqual(h1.json()["order_id"], h2.json()["order_id"])

    def test_06_webhook_hmac_verification_and_payment_state_machine(self) -> None:
        hold = self.client.post(
            "/api/orders/hold",
            headers=self._headers(),
            json={"items": [{"product_id": "PRD-001", "size": "M", "quantity": 1}]},
        ).json()
        oid = hold["order_id"]
        total_paise = hold["total_paise"]

        no_sig = self.client.post(
            "/api/payments/webhook",
            json={"eventId": "evt_1", "orderId": oid, "amountPaise": total_paise, "status": "captured"},
        )
        self.assertEqual(no_sig.status_code, 401)

        bad_sig = self._send_webhook(
            {"eventId": "evt_1", "orderId": oid, "amountPaise": total_paise, "status": "captured"},
            secret="wrong-secret",
        )
        self.assertEqual(bad_sig.status_code, 401)

        neg_amt = self._send_webhook(
            {"eventId": "evt_neg", "orderId": oid, "amountPaise": -100, "status": "captured"},
        )
        self.assertEqual(neg_amt.status_code, 400)

        ok_res = self._send_webhook(
            {"event_id": "evt_ok_1", "order_id": oid, "amount_paise": total_paise, "status": "captured"},
            prefix_sha256=False,
        )
        self.assertEqual(ok_res.status_code, 200)
        self.assertFalse(ok_res.json()["duplicate"])
        self.assertEqual(ok_res.json()["outcome"], "paid")
        self.assertEqual(ok_res.json()["order"]["status"], "paid")

        dup_res = self._send_webhook(
            {"eventId": "evt_ok_1", "orderId": oid, "amountPaise": total_paise, "status": "captured"},
        )
        self.assertEqual(dup_res.status_code, 200)
        self.assertTrue(dup_res.json()["duplicate"])

        claim1 = self.client.post(f"/api/orders/{oid}/pickup-claim", headers=self._headers())
        self.assertEqual(claim1.status_code, 200)
        self.assertEqual(claim1.json()["status"], "picked_up")
        claim2 = self.client.post(f"/api/orders/{oid}/pickup-claim", headers=self._headers())
        self.assertEqual(claim2.status_code, 409)
        self.assertEqual(claim2.json()["error"]["code"], "already_claimed")

    def test_07_webhook_edge_cases_mismatch_cancel_and_late_payment(self) -> None:
        hold_mm = self.client.post(
            "/api/orders/hold",
            headers=self._headers(),
            json={"items": [{"product_id": "PRD-004", "size": "S", "quantity": 1}]},
        ).json()
        res_mm = self._send_webhook(
            {
                "eventId": "evt_mismatch_1",
                "orderId": hold_mm["order_id"],
                "amountPaise": hold_mm["total_paise"] - 500,
                "status": "captured",
            }
        )
        self.assertEqual(res_mm.status_code, 200)
        self.assertEqual(res_mm.json()["outcome"], "needs_review")
        self.assertEqual(res_mm.json()["order"]["review_reason"], "amount_mismatch")

        hold_can = self.client.post(
            "/api/orders/hold",
            headers=self._headers(),
            json={"items": [{"product_id": "PRD-004", "size": "S", "quantity": 1}]},
        ).json()
        self.client.post(f"/api/orders/{hold_can['order_id']}/cancel", headers=self._headers())
        res_after_can = self._send_webhook(
            {
                "eventId": "evt_after_cancel_1",
                "orderId": hold_can["order_id"],
                "amountPaise": hold_can["total_paise"],
                "status": "captured",
            }
        )
        self.assertEqual(res_after_can.status_code, 200)
        self.assertEqual(res_after_can.json()["outcome"], "needs_review")
        self.assertEqual(res_after_can.json()["order"]["review_reason"], "payment_after_cancel")
        self.assertTrue(res_after_can.json()["order"]["refund_flag"])

        self._set_stock("PRD-005", 1)
        hold_late = self.client.post(
            "/api/orders/hold",
            headers=self._headers(),
            json={"items": [{"product_id": "PRD-005", "size": "M", "quantity": 1}]},
        ).json()
        with self.SessionLocal() as db:
            ord_row = db.scalar(select(Order).where(Order.order_id == hold_late["order_id"]))
            assert ord_row is not None
            ord_row.hold_expires_at = datetime.now(timezone.utc) - timedelta(seconds=15)
            db.commit()
        self.client.post("/api/orders/sweep-expired")

        other_buyer = self.client.post(
            "/api/orders/hold",
            headers=self._headers("demo_cust_002"),
            json={"items": [{"product_id": "PRD-005", "size": "M", "quantity": 1}]},
        )
        self.assertEqual(other_buyer.status_code, 201)

        res_late_gone = self._send_webhook(
            {
                "eventId": "evt_late_gone_1",
                "orderId": hold_late["order_id"],
                "amountPaise": hold_late["total_paise"],
                "status": "captured",
            }
        )
        self.assertEqual(res_late_gone.status_code, 200)
        self.assertEqual(res_late_gone.json()["outcome"], "needs_review")
        self.assertEqual(res_late_gone.json()["order"]["review_reason"], "late_payment_stock_gone")
        self.assertTrue(res_late_gone.json()["order"]["refund_flag"])


if __name__ == "__main__":
    unittest.main()
