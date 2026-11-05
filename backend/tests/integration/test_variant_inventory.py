"""Per-size stock + stock ledger, end to end through the HTTP API.

Regression for the 2026-11-05 audit: stock was tracked per product, so a sold-out
size could still be bought (2 x L twice with only 2 L in stock).
"""

import os
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.database import get_db, set_sync_engine
from backend.app.main import app
from backend.app.models import InventoryMovement, ProductVariant
from backend.scripts.check_inventory_invariants import find_problems
from backend.scripts.seed_demo import seed_database

CUSTOMER = {"Authorization": "Bearer demo_CUS-001"}
ADMIN = {"Authorization": "Bearer admin_manager"}


class TestVariantInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.engine = create_engine(
            f"sqlite:///{os.path.join(cls.tmp_dir.name, 'variant_inventory.db')}",
            connect_args={"check_same_thread": False},
        )
        set_sync_engine(cls.engine, "sqlite_variant_inventory_test")
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
        set_sync_engine(None)
        cls.engine.dispose()
        cls.tmp_dir.cleanup()

    def tearDown(self) -> None:
        # Every test must leave the ledger summing exactly to the live levels.
        self.assertEqual(find_problems(self.engine), [])

    # ------------------------------------------------------------------ helpers

    def _by_size(self, product_id: str) -> dict:
        return self.client.get(f"/api/products/{product_id}").json()["stock_by_size"]

    def _order(self, product_id: str, size: str, qty: int, **extra):
        return self.client.post(
            "/api/orders",
            json={
                "customer_id": "CUS-001",
                "items": [{"product_id": product_id, "size": size, "quantity": qty}],
                "payment_method": "upi",
                **extra,
            },
            headers=CUSTOMER,
        )

    def _movements(self, product_id: str) -> list:
        res = self.client.get(f"/api/inventory/{product_id}/movements", headers=ADMIN)
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    # ------------------------------------------------------------------ tests

    def test_01_payload_exposes_live_stock_per_size(self) -> None:
        p = self.client.get("/api/products/PRD-003").json()
        self.assertEqual(p["stock_by_size"], {"XS": 3, "S": 5, "M": 5, "L": 2})
        self.assertEqual(p["stock"], 15)
        self.assertNotIn("size_breakdown", p)
        by_variant = {v["size"]: (v["stock"], v["in_stock"]) for v in p["variants"]}
        self.assertEqual(by_variant["L"], (2, True))

    def test_02_sold_out_size_cannot_be_sold_even_with_other_sizes_in_stock(self) -> None:
        first = self._order("PRD-003", "L", 2)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(self._by_size("PRD-003")["L"], 0)

        second = self._order("PRD-003", "L", 2)
        self.assertEqual(second.status_code, 409)
        body = second.json()
        self.assertEqual(body["code"], "insufficient_stock")
        self.assertEqual(body["details"]["shortages"][0]["size"], "L")
        self.assertEqual(body["details"]["shortages"][0]["available"], 0)

        # Other sizes are untouched and still sellable.
        self.assertEqual(self._by_size("PRD-003")["M"], 5)
        self.assertEqual(self._order("PRD-003", "M", 1).status_code, 201)

        # Cart refuses the sold-out size too.
        cart = self.client.post(
            "/api/cart/add", json={"product_id": "PRD-003", "size": "L", "quantity": 1, "customer_id": "CUS-001"},
            headers=CUSTOMER,
        )
        self.assertEqual(cart.status_code, 422)
        self.assertEqual(cart.json()["details"]["size"], "L")

    def test_03_cancel_restocks_the_exact_size_with_a_ledger_trail(self) -> None:
        before = self._by_size("PRD-004")
        order = self._order("PRD-004", "XL", 2).json()
        self.assertEqual(self._by_size("PRD-004")["XL"], before["XL"] - 2)

        res = self.client.post(f"/api/orders/{order['order_id']}/cancel", json={"reason": "changed mind"}, headers=CUSTOMER)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(self._by_size("PRD-004"), before)

        trail = [(m["movement_type"], m["size"], m["delta_available"]) for m in self._movements("PRD-004")
                 if m["reference_id"] == order["order_id"]]
        self.assertIn(("sale", "XL", -2), trail)
        self.assertIn(("cancel_restock", "XL", 2), trail)

    def test_04_hold_reserves_per_size_and_expiry_releases_it(self) -> None:
        before = self._by_size("PRD-002")
        hold = self.client.post(
            "/api/orders/hold",
            json={"customer_id": "CUS-001", "items": [{"product_id": "PRD-002", "size": "XL", "quantity": 1}],
                  "hold_seconds": 0},
            headers=CUSTOMER,
        )
        self.assertEqual(hold.status_code, 201, hold.text)
        inv = {r["product_id"]: r for r in self.client.get("/api/inventory/list", headers=ADMIN).json()}
        xl = next(s for s in inv["PRD-002"]["sizes"] if s["size"] == "XL")
        self.assertEqual(xl["quantity_reserved"], 1)

        sweep = self.client.post("/api/orders/sweep-expired", headers=ADMIN)
        self.assertEqual(sweep.status_code, 200, sweep.text)
        self.assertEqual(self._by_size("PRD-002"), before)
        types = {m["movement_type"] for m in self._movements("PRD-002") if m["reference_id"] == hold.json()["order_id"]}
        self.assertEqual(types, {"hold", "hold_release"})

    def test_05_return_refund_restocks_the_sold_size(self) -> None:
        before = self._by_size("PRD-001")["S"]
        order = self._order("PRD-001", "S", 1).json()
        ret = self.client.post(
            "/api/returns",
            json={"order_id": order["order_id"], "reason_category": "size_mismatch",
                  "customer_notes": "Too small", "tag_intact": True, "qc_passed": True},
            headers={"Authorization": "Bearer svc-returns"},
        )
        self.assertEqual(ret.status_code, 201, ret.text)
        self.assertEqual(ret.json()["status"], "completed")
        self.assertEqual(self._by_size("PRD-001")["S"], before)
        self.assertIn("return_restock", {m["movement_type"] for m in self._movements("PRD-001")})

    def test_06_admin_sets_levels_and_receives_units_per_size(self) -> None:
        put = self.client.put("/api/inventory/PRD-005", json={"sizes": {"4Y": 11, "12Y": 0}, "reason": "cycle count"}, headers=ADMIN)
        self.assertEqual(put.status_code, 200, put.text)
        self.assertEqual(put.json()["stock_by_size"]["4Y"], 11)
        self.assertEqual(put.json()["stock_by_size"]["12Y"], 0)

        restock = self.client.post(
            "/api/inventory/restock", json={"product_id": "PRD-005", "size": "12Y", "quantity": 4}, headers=ADMIN
        )
        self.assertEqual(restock.status_code, 200, restock.text)
        self.assertEqual(self._by_size("PRD-005")["12Y"], 4)

        kinds = [(m["movement_type"], m["size"]) for m in self._movements("PRD-005")[:3]]
        self.assertIn(("restock", "12Y"), kinds)
        self.assertIn(("adjustment", "4Y"), kinds)

        # Validation: unknown size, negative level, customer access.
        self.assertEqual(self.client.put("/api/inventory/PRD-005", json={"sizes": {"XXL": 1}}, headers=ADMIN).status_code, 422)
        self.assertEqual(self.client.put("/api/inventory/PRD-005", json={"sizes": {"4Y": -1}}, headers=ADMIN).status_code, 422)
        self.assertEqual(self.client.put("/api/inventory/PRD-005", json={"sizes": {"4Y": 1}}, headers=CUSTOMER).status_code, 403)
        self.assertEqual(self.client.get("/api/inventory/PRD-005/movements", headers=CUSTOMER).status_code, 403)

    def test_07_raw_reserve_endpoint_is_gone(self) -> None:
        res = self.client.post("/api/inventory/reserve", json={"product_id": "PRD-001", "quantity": 1}, headers=ADMIN)
        self.assertIn(res.status_code, (404, 405))

    def test_08_in_stock_search_requires_the_same_size_to_be_in_budget_and_in_stock(self) -> None:
        # PRD-004 sizes are priced differently; make every size except the most expensive one sold out.
        p = self.client.get("/api/products/PRD-004").json()
        prices = {v["size"]: float(v["mrp_inr"]) for v in p["variants"]}
        dearest = max(prices, key=prices.get)
        self.client.put(
            "/api/inventory/PRD-004",
            json={"sizes": {s: (3 if s == dearest else 0) for s in prices}, "reason": "test setup"},
            headers=ADMIN,
        )
        cheap_cap = min(prices.values())
        res = self.client.get(
            "/api/catalog/search", params={"in_stock_only": True, "max_price": cheap_cap, "limit": 50}
        ).json()
        ids = [i["product_id"] for i in res["items"]]
        self.assertGreater(prices[dearest], cheap_cap, "fixture needs per-size prices")
        self.assertNotIn("PRD-004", ids)
        # Without the budget it is still in stock (via its dearest size).
        res_all = self.client.get("/api/catalog/search", params={"in_stock_only": True, "limit": 50}).json()
        self.assertIn("PRD-004", [i["product_id"] for i in res_all["items"]])

    def test_09_new_product_opening_stock_per_size(self) -> None:
        res = self.client.post(
            "/api/products",
            json={
                "sku": "NA-TEST-STOCK",
                "name": "Test Stock Shirt",
                "description": "Opening stock per size test garment.",
                "category_id": "CAT-11",
                "department": "MEN",
                "mrp_inr": 2999,
                "hsn_code": "6205",
                "color": "Ivory",
                "sizes_available": ["S", "M", "L"],
                "fit_guide": "Regular fit.",
                "fabric_and_care": "Cotton. Machine wash.",
                "initial_stock": 10,
            },
            headers=ADMIN,
        )
        self.assertEqual(res.status_code, 201, res.text)
        pid = res.json()["product_id"]
        # 10 split exactly across 3 sizes, nothing invented or lost.
        self.assertEqual(self._by_size(pid), {"S": 4, "M": 3, "L": 3})
        with self.SessionLocal() as db:
            n = db.scalar(
                select(InventoryMovement.movement_id)
                .join(ProductVariant, ProductVariant.variant_id == InventoryMovement.variant_id)
                .where(ProductVariant.product_id == pid, InventoryMovement.movement_type == "opening_balance")
                .limit(1)
            )
        self.assertIsNotNone(n)


if __name__ == "__main__":
    unittest.main()
