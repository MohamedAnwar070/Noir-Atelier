"""End-to-end integration tests for database-driven catalogue metadata,
multi-facet natural-language SQL search, admin vocabulary CRUD, and
reference status/reason FK enforcement.
"""
import os
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import get_db, set_sync_engine
from backend.app.main import app
from backend.scripts.seed_demo import seed_database


class TestCatalogSearchAndReferenceData(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp_dir.name, "test_catalog_ref.db")
        cls.engine = create_engine(
            f"sqlite:///{cls.db_path}",
            connect_args={"check_same_thread": False},
        )
        set_sync_engine(cls.engine, "sqlite_catalog_test")
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

    def test_01_catalog_meta_serves_complete_db_reference_tables(self) -> None:
        res = self.client.get("/api/catalog/meta")
        self.assertEqual(res.status_code, 200)
        meta = res.json()

        dept_codes = [d["code"] for d in meta["departments"]]
        self.assertEqual(dept_codes, ["MEN", "WOMEN", "KIDS"])

        cat_slugs = {c["slug"] for c in meta["categories"]}
        self.assertTrue({"tops", "shirt", "t-shirt", "outerwear", "overshirt", "dress", "knitwear"}.issubset(cat_slugs))
        tops = next(c for c in meta["categories"] if c["slug"] == "tops")
        # Subtree count for Tops includes Shirts (PRD-001) + T-Shirts (PRD-004)
        self.assertEqual(tops["product_count"], 2)

        color_families = {c["family"] for c in meta["color_families"]}
        self.assertEqual(color_families, {"black", "white", "grey", "blue"})

        material_families = {m["family"] for m in meta["material_families"]}
        self.assertEqual(material_families, {"linen", "wool", "silk", "cotton", "polyamide"})

        tier_ids = [t["id"] for t in meta["price_tiers"]]
        self.assertEqual(tier_ids, ["ALL", "ESSENTIAL", "SIGNATURE", "ATELIER"])

        self.assertGreaterEqual(len(meta["order_statuses"]), 11)
        self.assertEqual(len(meta["refund_statuses"]), 5)
        self.assertGreaterEqual(len(meta["return_reasons"]), 5)
        self.assertEqual(len(meta["fit_feedback_options"]), 3)

    def test_02_multi_facet_natural_language_sql_search(self) -> None:
        # 1. Multi-facet query where no single product satisfies all facets:
        #    PRD-004 is a Cotton Tee under ₹2,000, but it is Women / Ivory — NOT Men / Black!
        no_match = self.client.get("/api/catalog/search", params={"q": "black cotton tees for men under ₹2,000"}).json()
        self.assertEqual(no_match["total"], 0)
        self.assertEqual(no_match["items"], [])
        self.assertEqual(no_match["interpretation"]["max_price"], 2000.0)
        dims = {r["dimension"]: r["value"] for r in no_match["interpretation"]["recognized"]}
        self.assertEqual(dims["color"], "black")
        self.assertEqual(dims["material"], "cotton")
        self.assertEqual(dims["product_type"], "t-shirt")
        self.assertEqual(dims["department"], "MEN")

        # 2. Exact multi-facet match: "ivory cotton tee" -> PRD-004
        ivory_tee = self.client.get("/api/catalog/search", params={"q": "ivory cotton tee"}).json()
        self.assertEqual([p["product_id"] for p in ivory_tee["items"]], ["PRD-004"])
        self.assertFalse(ivory_tee["interpretation"]["relaxed"])

        # 3. Department + Material + Type + Budget: "men linen shirt under ₹3,000" -> PRD-001
        men_shirt = self.client.get("/api/catalog/search", params={"q": "men linen shirt under ₹3,000"}).json()
        self.assertEqual([p["product_id"] for p in men_shirt["items"]], ["PRD-001"])

        # 4. Synonym resolution: "merino sweater" -> wool + knitwear -> PRD-005
        knit = self.client.get("/api/catalog/search", params={"q": "merino sweater"}).json()
        self.assertEqual([p["product_id"] for p in knit["items"]], ["PRD-005"])

        # 5. Hierarchical category subtree filter: category=tops -> PRD-001 (shirt) + PRD-004 (t-shirt)
        tops = self.client.get("/api/catalog/search", params={"category": "tops", "sort": "price_asc"}).json()
        self.assertEqual([p["product_id"] for p in tops["items"]], ["PRD-004", "PRD-001"])

        # 6. Unknown adjective with structured facets relaxes text filter cleanly
        relaxed = self.client.get("/api/catalog/search", params={"q": "breezy linen shirt"}).json()
        self.assertEqual([p["product_id"] for p in relaxed["items"]], ["PRD-001"])
        self.assertTrue(relaxed["interpretation"]["relaxed"])

        # 7. Unknown standalone term without structured facets does NOT return whole catalogue
        unknown = self.client.get("/api/catalog/search", params={"q": "denim"}).json()
        self.assertEqual(unknown["total"], 0)
        self.assertEqual(unknown["items"], [])
        self.assertFalse(unknown["interpretation"]["relaxed"])

    def test_03_admin_vocabulary_crud_updates_search_live(self) -> None:
        # Customer cannot mutate vocabulary
        forbidden = self.client.post(
            "/api/admin/catalog/synonyms",
            json={"term": "kurta", "dimension": "product_type", "value": "shirt"},
            headers=self._headers("demo_CUS-001"),
        )
        self.assertEqual(forbidden.status_code, 403)

        # Invalid target rejected with 422
        bad_target = self.client.post(
            "/api/admin/catalog/synonyms",
            json={"term": "kurta", "dimension": "product_type", "value": "nonexistent_slug"},
            headers=self._headers("admin_manager"),
        )
        self.assertEqual(bad_target.status_code, 422)
        self.assertEqual(bad_target.json()["code"], "invalid_synonym_target")

        # Before adding synonym, "kurta" yields 0 results
        before = self.client.get("/api/catalog/search", params={"q": "kurta"}).json()
        self.assertEqual(before["total"], 0)

        # Admin adds "kurta" -> product_type:shirt
        created_res = self.client.post(
            "/api/admin/catalog/synonyms",
            json={"term": "kurta", "dimension": "product_type", "value": "shirt"},
            headers=self._headers("admin_manager"),
        )
        self.assertEqual(created_res.status_code, 201)
        syn_id = created_res.json()["synonym_id"]

        # Immediately searchable without code changes!
        after = self.client.get("/api/catalog/search", params={"q": "linen kurta"}).json()
        self.assertEqual([p["product_id"] for p in after["items"]], ["PRD-001"])

        # Delete synonym restores original search behaviour
        del_res = self.client.delete(
            f"/api/admin/catalog/synonyms/{syn_id}",
            headers=self._headers("admin_manager"),
        )
        self.assertEqual(del_res.status_code, 200)
        restored = self.client.get("/api/catalog/search", params={"q": "kurta"}).json()
        self.assertEqual(restored["total"], 0)

        # Admin adds new palette colour & fiber and meta reflects them immediately
        col_res = self.client.post(
            "/api/admin/catalog/colors",
            json={"name": "Forest Sage", "family": "green", "hex_code": "#3B4D3B"},
            headers=self._headers("admin_manager"),
        )
        self.assertEqual(col_res.status_code, 201)
        mat_res = self.client.post(
            "/api/admin/catalog/materials",
            json={"name": "Himalayan Cashmere", "family": "cashmere", "hsn_default": "61"},
            headers=self._headers("admin_manager"),
        )
        self.assertEqual(mat_res.status_code, 201)

        meta_after = self.client.get("/api/catalog/meta").json()
        self.assertIn("green", {c["family"] for c in meta_after["color_families"]})
        self.assertIn("cashmere", {m["family"] for m in meta_after["material_families"]})

    def test_03b_every_synonym_dimension_is_served_and_validated(self) -> None:
        """Meta serves every dimension with its valid targets; each one round-trips.

        Regression: occasion/palette used to fall through to the material lookup.
        """
        from backend.app.models.catalog import SYNONYM_DIMENSIONS

        meta = self.client.get("/api/catalog/meta").json()
        dims = {d["code"]: d for d in meta["synonym_dimensions"]}
        self.assertEqual(list(dims), list(SYNONYM_DIMENSIONS))

        for code in ("occasion", "palette"):
            self.assertTrue(dims[code]["options"], f"{code} has no targets")
            target = dims[code]["options"][0]["value"]
            ok = self.client.post(
                "/api/admin/catalog/synonyms",
                json={"term": f"test {code} term", "dimension": code, "value": target},
                headers=self._headers("admin_manager"),
            )
            self.assertEqual(ok.status_code, 201, ok.text)
            self.assertEqual(ok.json()["value"], target)

            # A material family is not a valid occasion/palette target
            wrong = self.client.post(
                "/api/admin/catalog/synonyms",
                json={"term": f"bad {code} term", "dimension": code, "value": "linen"},
                headers=self._headers("admin_manager"),
            )
            self.assertEqual(wrong.status_code, 422)
            self.assertEqual(wrong.json()["code"], "invalid_synonym_target")

            self.client.delete(
                f"/api/admin/catalog/synonyms/{ok.json()['synonym_id']}",
                headers=self._headers("admin_manager"),
            )

    def test_04_db_driven_return_reasons_and_status_metadata(self) -> None:
        order = self.client.post(
            "/api/orders",
            json={
                "customer_id": "CUS-001",
                "items": [{"product_id": "PRD-001", "size": "M", "quantity": 1}],
                "payment_method": "upi",
            },
            headers=self._headers("demo_CUS-001"),
        ).json()
        self.assertEqual(order["status_label"], "Confirmed")
        self.assertTrue(order["can_cancel"])
        self.assertFalse(order["can_return"])

        # Invalid return reason code is rejected against DB return_reasons table
        bad_ret = self.client.post(
            "/api/returns",
            json={
                "order_id": order["order_id"],
                "reason_category": "size_fit_invalid_hardcoded",
                "customer_notes": "Wrong code",
                "tag_intact": True,
            },
            headers=self._headers("demo_CUS-001"),
        )
        self.assertEqual(bad_ret.status_code, 422)
        self.assertEqual(bad_ret.json()["code"], "invalid_return_reason")
        self.assertIn("size_mismatch", bad_ret.json()["details"]["available_reasons"])

        # Valid defect reason automatically sets defect handling from DB `return_reasons.is_defect_claim`
        good_ret = self.client.post(
            "/api/returns",
            json={
                "order_id": order["order_id"],
                "reason_category": "fabric_defect",
                "customer_notes": "Small weave pull on cuff",
                "tag_intact": True,
                "qc_passed": True,
            },
            headers=self._headers("demo_CUS-001"),
        )
        self.assertEqual(good_ret.status_code, 201)
        refunds = self.client.get("/api/refunds", headers=self._headers("admin_manager")).json()
        matching = next(r for r in refunds if r["refund_id"] == good_ret.json()["refund_id"])
        self.assertEqual(matching["status_label"], "Refunded")
        self.assertFalse(matching["awaiting_approval"])


if __name__ == "__main__":
    unittest.main()
