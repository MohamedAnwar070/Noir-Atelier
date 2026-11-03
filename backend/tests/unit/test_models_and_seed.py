from decimal import Decimal
import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    AgentPermission,
    Base,
    BusinessConfig,
    Category,
    Color,
    Customer,
    Department,
    Inventory,
    Material,
    OrderStatus,
    Policy,
    Product,
    ProductMaterial,
    RefundStatus,
    ReturnReason,
    SearchSynonym,
)
from backend.scripts.seed_demo import seed_database


class TestModelsAndSeed(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")

    def test_41_tables_registered_and_all_foreign_keys_indexed(self) -> None:
        tables = set(Base.metadata.tables.keys())
        self.assertEqual(len(tables), 41)
        for required in (
            "customers",
            "customer_addresses",
            "customer_preferences",
            "customer_vectors",
            "departments",
            "categories",
            "colors",
            "materials",
            "products",
            "product_materials",
            "product_variants",
            "product_images",
            "search_synonyms",
            "inventory",
            "product_vectors",
            "product_reviews",
            "recommendations",
            "cart",
            "coupons",
            "order_statuses",
            "orders",
            "order_items",
            "coupon_usage",
            "payment_methods",
            "payments",
            "invoices",
            "shipping_zones",
            "shipments",
            "return_reasons",
            "returns",
            "refund_statuses",
            "refunds",
            "support_tickets",
            "audit_log",
            "compliance_flags",
            "fraud_flags",
            "business_config",
            "policies",
            "agent_permissions",
            "agent_sessions",
            "idempotency_keys",
        ):
            self.assertIn(required, tables)

        # Schema designer invariant: every FK column must be covered by PK, unique, or leading index
        unindexed_fks = []
        for tname, table in Base.metadata.tables.items():
            pk_cols = [c.name for c in table.primary_key.columns]
            indexed_leading = set()
            if pk_cols:
                indexed_leading.add(pk_cols[0])
                indexed_leading.add(tuple(pk_cols))
            for idx in table.indexes:
                cols = [c.name for c in idx.columns]
                if cols:
                    indexed_leading.add(cols[0])
                    indexed_leading.add(tuple(cols))
            for c in table.columns:
                if c.unique or c.index:
                    indexed_leading.add(c.name)
            for fk in table.foreign_keys:
                col_name = fk.parent.name
                if col_name not in indexed_leading:
                    unindexed_fks.append(f"{tname}.{col_name}")

        self.assertEqual(unindexed_fks, [], f"Unindexed FK columns found: {unindexed_fks}")

    def test_seed_premium_garments_and_configs(self) -> None:
        res = seed_database(self.engine)
        self.assertEqual(res["status"], "seeded")

        idempotent_res = seed_database(self.engine)
        self.assertEqual(idempotent_res["status"], "already_seeded")

        with Session(self.engine) as session:
            depts = set(session.scalars(select(Department.code)).all())
            self.assertEqual(depts, {"MEN", "WOMEN", "KIDS"})

            categories = session.scalars(select(Category)).all()
            self.assertEqual(len(categories), 7)
            slug_map = {c.slug: c for c in categories}
            self.assertIn("tops", slug_map)
            self.assertIn("shirt", slug_map)
            self.assertIn("t-shirt", slug_map)
            self.assertEqual(slug_map["shirt"].parent_id, slug_map["tops"].category_id)
            self.assertEqual(slug_map["t-shirt"].parent_id, slug_map["tops"].category_id)

            colors = session.scalars(select(Color)).all()
            self.assertGreaterEqual(len(colors), 5)

            materials = session.scalars(select(Material)).all()
            self.assertGreaterEqual(len(materials), 5)

            synonyms = session.scalars(select(SearchSynonym)).all()
            self.assertGreaterEqual(len(synonyms), 20)

            self.assertGreaterEqual(len(session.scalars(select(OrderStatus)).all()), 11)
            self.assertEqual(len(session.scalars(select(RefundStatus)).all()), 5)
            self.assertGreaterEqual(len(session.scalars(select(ReturnReason)).all()), 5)

            products = session.scalars(select(Product)).all()
            self.assertEqual(len(products), 5)
            for p in products:
                self.assertTrue(p.hsn_code.startswith(("61", "62")))
                self.assertTrue(p.security_tag_required)
                self.assertGreater(p.mrp_inr, Decimal("0"))
                self.assertIn(p.department, depts)
                self.assertIsNotNone(p.category_id)
                self.assertIsNotNone(p.color_id)
                self.assertTrue(p.materials)
                comp_sum = sum(pm.percentage for pm in p.materials)
                self.assertEqual(comp_sum, 100)
                # Every size is a variant with its own SKU; the product price is the lowest one.
                self.assertTrue(p.variants)
                self.assertEqual(p.mrp_inr, min(v.mrp_inr for v in p.variants))
                self.assertEqual(p.sizes_available, [v.size for v in p.variants])
                self.assertTrue(all(v.sku == f"{p.sku}-{v.size}" for v in p.variants))

            total_stock = session.scalar(select(func.sum(Inventory.quantity_available)))
            self.assertEqual(total_stock, 170)

            customers = session.scalars(select(Customer)).all()
            self.assertEqual(len(customers), 2)

            refund_cfg = session.scalar(
                select(BusinessConfig).where(BusinessConfig.config_key == "returns_and_refunds")
            )
            self.assertIsNotNone(refund_cfg)
            self.assertTrue(refund_cfg.config_value["require_security_tag_intact"])
            self.assertEqual(refund_cfg.config_value["tiers"]["tier_1_auto_refund_max_inr"], 5000)
            self.assertEqual(refund_cfg.config_value["tiers"]["tier_2_manager_approval_max_inr"], 25000)

            perms = session.scalars(select(AgentPermission)).all()
            self.assertEqual(len(perms), 9)

            policies = session.scalars(select(Policy)).all()
            self.assertEqual(len(policies), 4)

    def test_postgresql_for_update_queries_have_no_outer_joins(self) -> None:
        """PostgreSQL rejects `FOR UPDATE` on the nullable side of a LEFT OUTER JOIN.
        Ensure all row-locking queries compile cleanly under the PostgreSQL dialect
        without outer-joining reference tables.
        """
        from sqlalchemy.dialects import postgresql
        from backend.app.models.order import Order

        locked_queries = [
            select(Product).where(Product.product_id.in_(["PRD-001", "PRD-004"])).order_by(Product.product_id.asc()).with_for_update(),
            select(Inventory).where(Inventory.product_id.in_(["PRD-001", "PRD-004"])).order_by(Inventory.product_id.asc()).with_for_update(),
            select(Order).where(Order.order_id == "ORD-1001").with_for_update(),
        ]
        for stmt in locked_queries:
            sql = str(stmt.compile(dialect=postgresql.dialect()))
            self.assertNotIn("OUTER JOIN", sql.upper(), f"Unexpected OUTER JOIN in FOR UPDATE SQL: {sql}")
            self.assertIn("FOR UPDATE", sql.upper())


if __name__ == "__main__":
    unittest.main()
