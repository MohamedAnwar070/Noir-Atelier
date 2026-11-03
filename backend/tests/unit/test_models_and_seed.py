from decimal import Decimal
import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    AgentPermission,
    Base,
    BusinessConfig,
    Category,
    Customer,
    Inventory,
    Policy,
    Product,
)
from backend.scripts.seed_demo import seed_database


class TestModelsAndSeed(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")

    def test_33_tables_registered(self) -> None:
        tables = set(Base.metadata.tables.keys())
        self.assertEqual(len(tables), 33)
        for required in (
            "customers",
            "customer_addresses",
            "customer_preferences",
            "customer_vectors",
            "categories",
            "products",
            "product_variants",
            "product_images",
            "inventory",
            "product_vectors",
            "product_reviews",
            "recommendations",
            "cart",
            "coupons",
            "orders",
            "order_items",
            "coupon_usage",
            "payment_methods",
            "payments",
            "invoices",
            "shipping_zones",
            "shipments",
            "returns",
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

    def test_seed_premium_garments_and_configs(self) -> None:
        res = seed_database(self.engine)
        self.assertEqual(res["status"], "seeded")

        idempotent_res = seed_database(self.engine)
        self.assertEqual(idempotent_res["status"], "already_seeded")

        with Session(self.engine) as session:
            depts = set(session.scalars(select(Category.department)).all())
            self.assertEqual(depts, {"MEN", "WOMEN", "KIDS"})

            products = session.scalars(select(Product)).all()
            self.assertEqual(len(products), 5)
            for p in products:
                self.assertTrue(p.hsn_code.startswith(("61", "62")))
                self.assertTrue(p.security_tag_required)
                self.assertGreater(p.mrp_inr, Decimal("0"))
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


if __name__ == "__main__":
    unittest.main()
