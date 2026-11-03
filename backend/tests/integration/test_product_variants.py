"""Per-size variants: each size has its own SKU and price, end to end.

Seed prices for PRD-001 (Tailored Belgian Linen Shirt, style PRD-001-BLK):
    S 2399 · M 2499 · L 2599 · XL 2699
The GST slab threshold is ₹2,500, so S/M are taxed at 5% and L/XL at 18% —
sizes of one product can land in different slabs, which is why price must
live on the variant.
"""
import os
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import get_db, set_sync_engine
from backend.app.main import app
from backend.app.models import Product
from backend.app.services.variant_service import style_code
from backend.scripts.seed_demo import seed_database

CUSTOMER = {"Authorization": "Bearer demo_CUS-002"}
ADMIN = {"Authorization": "Bearer admin_root"}


class TestProductVariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.engine = create_engine(
            f"sqlite:///{os.path.join(cls.tmp_dir.name, 'variants.db')}",
            connect_args={"check_same_thread": False},
        )
        set_sync_engine(cls.engine, "sqlite_test")
        seed_database(cls.engine)
        SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

        def override_get_db():
            db = SessionLocal()
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

    def setUp(self) -> None:
        self.assertEqual(self.client.post("/api/cart/clear", headers=CUSTOMER).status_code, 200)

    # -- helpers --------------------------------------------------------------
    def _add(self, product_id: str, size: str, quantity: int = 1):
        return self.client.post(
            "/api/cart/add",
            json={"product_id": product_id, "size": size, "quantity": quantity},
            headers=CUSTOMER,
        )

    def _line(self, cart: dict, size: str) -> dict:
        return next(i for i in cart["items"] if i["size"] == size)

    # -- catalog --------------------------------------------------------------
    def test_catalog_exposes_per_size_prices_and_from_price(self) -> None:
        prod = self.client.get("/api/products/PRD-001", headers=CUSTOMER).json()
        prices = {v["size"]: float(v["mrp_inr"]) for v in prod["variants"]}
        self.assertEqual(prices, {"S": 2399.0, "M": 2499.0, "L": 2599.0, "XL": 2699.0})
        self.assertEqual({v["sku"] for v in prod["variants"]},
                         {"PRD-001-BLK-S", "PRD-001-BLK-M", "PRD-001-BLK-L", "PRD-001-BLK-XL"})
        self.assertEqual(prod["sku"], "PRD-001-BLK")  # style code, not a size SKU
        self.assertEqual(float(prod["mrp_inr"]), 2399.0)  # "from" price
        self.assertEqual((float(prod["price_range"]["min"]), float(prod["price_range"]["max"])), (2399.0, 2699.0))
        self.assertEqual(prod["sizes_available"], ["S", "M", "L", "XL"])

    # -- cart pricing ---------------------------------------------------------
    def test_each_size_is_priced_and_taxed_on_its_own(self) -> None:
        self.assertEqual(self._add("PRD-001", "M").status_code, 200)
        cart = self._add("PRD-001", "L").json()

        m, l = self._line(cart, "M"), self._line(cart, "L")
        self.assertEqual((m["sku"], float(m["unit_mrp_inr"]), float(m["gst_rate_pct"])), ("PRD-001-BLK-M", 2499.0, 5.0))
        self.assertEqual((l["sku"], float(l["unit_mrp_inr"]), float(l["gst_rate_pct"])), ("PRD-001-BLK-L", 2599.0, 18.0))
        self.assertEqual(float(cart["subtotal_mrp_inr"]), 2499.0 + 2599.0)

    def test_size_is_normalised(self) -> None:
        cart = self._add("PRD-001", " xl ").json()
        self.assertEqual(self._line(cart, "XL")["sku"], "PRD-001-BLK-XL")

    def test_variant_sku_identifies_the_size(self) -> None:
        # A size SKU decides the size even if a different `size` is sent.
        cart = self._add("PRD-001-BLK-XL", "S").json()
        line = cart["items"][0]
        self.assertEqual((line["size"], float(line["unit_mrp_inr"])), ("XL", 2699.0))

    def test_unknown_size_is_rejected_with_available_sizes(self) -> None:
        res = self._add("PRD-001", "XXXL")
        self.assertEqual(res.status_code, 422)
        body = res.json()
        self.assertEqual(body["code"], "size_unavailable")
        self.assertEqual(body["details"]["available_sizes"], ["S", "M", "L", "XL"])

    # -- orders ---------------------------------------------------------------
    def test_order_snapshots_variant_sku_and_price(self) -> None:
        self._add("PRD-001", "S")
        self._add("PRD-001", "XL")
        res = self.client.post("/api/orders", json={"payment_method": "upi"}, headers=CUSTOMER)
        self.assertIn(res.status_code, (200, 201), res.text)
        items = {i["size"]: i for i in res.json()["items"]}
        self.assertEqual((items["S"]["sku"], float(items["S"]["unit_mrp_inr"])), ("PRD-001-BLK-S", 2399.0))
        self.assertEqual((items["XL"]["sku"], float(items["XL"]["unit_mrp_inr"])), ("PRD-001-BLK-XL", 2699.0))
        self.assertEqual(float(res.json()["grand_total_inr"]), 2399.0 + 2699.0)

    # -- admin ----------------------------------------------------------------
    def test_admin_reprices_one_size_and_from_price_follows(self) -> None:
        res = self.client.put("/api/products/PRD-004/variants/XS", json={"mrp_inr": 1599}, headers=ADMIN)
        self.assertEqual(res.status_code, 200, res.text)
        prod = res.json()
        self.assertEqual(float(prod["mrp_inr"]), 1599.0)  # new lowest price
        self.assertEqual(float(next(v for v in prod["variants"] if v["size"] == "XS")["mrp_inr"]), 1599.0)

        cart = self._add("PRD-004", "XS").json()
        self.assertEqual(float(cart["items"][0]["unit_mrp_inr"]), 1599.0)

    def test_customers_cannot_reprice(self) -> None:
        res = self.client.put("/api/products/PRD-004/variants/S", json={"mrp_inr": 1}, headers=CUSTOMER)
        self.assertEqual(res.status_code, 403)

    def test_retired_size_cannot_be_bought_but_cart_still_loads(self) -> None:
        self._add("PRD-002", "XL")
        retire = self.client.put("/api/products/PRD-002/variants/XL", json={"is_active": False}, headers=ADMIN)
        self.assertEqual(retire.status_code, 200, retire.text)
        self.assertNotIn("XL", retire.json()["sizes_available"])

        cart = self.client.get("/api/cart", headers=CUSTOMER).json()
        self.assertEqual(cart["items"], [])
        self.assertEqual(cart["unavailable_items"][0]["size"], "XL")
        self.assertEqual(self._add("PRD-002", "XL").status_code, 422)

        # Restore for other tests
        self.client.put("/api/products/PRD-002/variants/XL", json={"is_active": True}, headers=ADMIN)

    def test_last_size_cannot_be_retired(self) -> None:
        for size in ("M", "L"):
            self.client.put(f"/api/products/PRD-002/variants/{size}", json={"is_active": False}, headers=ADMIN)
        res = self.client.put("/api/products/PRD-002/variants/XL", json={"is_active": False}, headers=ADMIN)
        self.assertEqual(res.status_code, 422)
        for size in ("M", "L"):
            self.client.put(f"/api/products/PRD-002/variants/{size}", json={"is_active": True}, headers=ADMIN)


class TestStyleCode(unittest.TestCase):
    """Legacy products stored one size's SKU on the product; the style code strips it."""

    def _product(self, sku: str, sizes):
        return Product(product_id="PRD-X", sku=sku, sizes_available=sizes)

    def test_strips_trailing_size(self) -> None:
        self.assertEqual(style_code(self._product("PRD-002-CHR-L", ["M", "L", "XL"])), "PRD-002-CHR")
        self.assertEqual(style_code(self._product("PRD-005-NVY-8Y", ["4Y", "8Y"])), "PRD-005-NVY")

    def test_keeps_size_free_codes(self) -> None:
        self.assertEqual(style_code(self._product("PRD-002-CHR", ["M"])), "PRD-002-CHR")


if __name__ == "__main__":
    unittest.main()
