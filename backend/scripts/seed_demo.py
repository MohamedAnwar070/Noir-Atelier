from decimal import Decimal
from pathlib import Path
import sys
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.models import (
    AgentPermission,
    Base,
    BusinessConfig,
    Category,
    Color,
    Coupon,
    Customer,
    CustomerAddress,
    CustomerPreference,
    Inventory,
    Material,
    PaymentMethod,
    Policy,
    Product,
    ProductImage,
    ProductMaterial,
    ProductReview,
    Recommendation,
    ShippingZone,
)
from backend.app.storage.object_store import LocalObjectStore
from backend.app.reference_data import CATEGORIES, FIT_FEEDBACK_OPTIONS, ensure_reference_data
from backend.app.services.variant_service import set_variant_prices


def seed_database(engine: Optional[Engine] = None) -> dict:
    if engine is None:
        settings = get_settings()
        engine = create_engine(settings.database_sync_url)

    Base.metadata.create_all(bind=engine)
    object_store = LocalObjectStore()

    with Session(engine) as session:
        # Vocabulary (departments, taxonomy, colours, materials, synonyms, statuses)
        # is shared with migration 0003 — one definition in app/reference_data.py.
        ensure_reference_data(session)
        session.commit()

        if session.get(Product, "PRD-001") is not None:
            return {"status": "already_seeded"}

        color_ids = {c.name: c.color_id for c in session.scalars(select(Color))}
        material_ids = {m.name: m.material_id for m in session.scalars(select(Material))}

        products_spec = [
            {
                "product_id": "PRD-001",
                "sku": "PRD-001-BLK",
                "name": "Tailored Belgian Linen Shirt",
                "description": "Noir Atelier signature relaxed-tailored shirt crafted from 100% European flax linen.",
                "category_id": "CAT-11",  # product type
                "materials": [("Belgian Linen", 100)],
                "department": "MEN",
                "hsn_code": "6205",
                "color": "Noir Black",
                # Per-size prices: each size is its own SKU ("PRD-001-BLK-<SIZE>") and price.
                "variant_prices": {"S": Decimal("2399.00"), "M": Decimal("2499.00"), "L": Decimal("2599.00"), "XL": Decimal("2699.00")},
                "fit_guide": "Tailored regular fit through chest and shoulders. True to size.",
                "fabric_and_care": "100% Belgian Linen (185 GSM). Cold gentle wash, hang dry in shade.",
                "final_sale": False,
                "stock": 40,
                "size_breakdown": {"S": 8, "M": 14, "L": 12, "XL": 6},
                "image_filename": "product.jpg",
                "remote_image_url": "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?auto=format&fit=crop&w=1200&q=85",
                "accent_tag": "100% European Flax Linen",
            },
            {
                "product_id": "PRD-002",
                "sku": "PRD-002-CHR",
                "name": "Structured Merino-Wool Overshirt",
                "description": "Architectural double-faced merino wool-blend overshirt with horn buttons.",
                "category_id": "CAT-21",  # product type
                "materials": [("Merino Wool", 80), ("Recycled Polyamide", 20)],
                "department": "MEN",
                "hsn_code": "6201",
                "color": "Charcoal",
                # Per-size prices: each size is its own SKU ("PRD-002-CHR-<SIZE>") and price.
                "variant_prices": {"M": Decimal("6499.00"), "L": Decimal("6699.00"), "XL": Decimal("6899.00")},
                "fit_guide": "Structured boxy outerwear cut. Designed to layer over fine knitwear.",
                "fabric_and_care": "80% Australian Merino Wool, 20% Recycled Polyamide. Dry clean only.",
                "final_sale": False,
                "stock": 20,
                "size_breakdown": {"M": 7, "L": 8, "XL": 5},
                "image_filename": "product.jpg",
                "remote_image_url": "https://images.unsplash.com/photo-1544022613-e87ca75a784a?auto=format&fit=crop&w=1200&q=85",
                "accent_tag": "Double-Faced Merino Wool",
            },
            {
                "product_id": "PRD-003",
                "sku": "PRD-003-NOI",
                "name": "Silk-Crepe Draped Midi Dress",
                "description": "Fluid bias-cut midi dress in heavyweight mulberry silk crepe de chine.",
                "category_id": "CAT-40",  # product type
                "materials": [("Mulberry Silk", 100)],
                "department": "WOMEN",
                "hsn_code": "6204",
                "color": "Obsidian",
                # Per-size prices: each size is its own SKU ("PRD-003-NOI-<SIZE>") and price.
                "variant_prices": {"XS": Decimal("7799.00"), "S": Decimal("7999.00"), "M": Decimal("7999.00"), "L": Decimal("8299.00")},
                "fit_guide": "Bias cut contours naturally to the silhouette. True to atelier sizing.",
                "fabric_and_care": "100% Mulberry Silk Crepe (22 Momme). Specialist dry clean only.",
                "final_sale": False,
                "stock": 15,
                "size_breakdown": {"XS": 3, "S": 5, "M": 5, "L": 2},
                "image_filename": "product.jpg",
                "remote_image_url": "https://images.unsplash.com/photo-1539008835657-9e8e9680c956?auto=format&fit=crop&w=1200&q=85",
                "accent_tag": "22-Momme Mulberry Silk",
            },
            {
                "product_id": "PRD-004",
                "sku": "PRD-004-IVR",
                "name": "Minimalist Pima Cotton Tee",
                "description": "High-twist Peruvian Pima cotton jersey tee with rib-bound neckline.",
                "category_id": "CAT-12",  # product type
                "materials": [("Pima Cotton", 100)],
                "department": "WOMEN",
                "hsn_code": "6109",
                "color": "Ivory",
                # Per-size prices: each size is its own SKU ("PRD-004-IVR-<SIZE>") and price.
                "variant_prices": {"XS": Decimal("1799.00"), "S": Decimal("1899.00"), "M": Decimal("1899.00"), "L": Decimal("1999.00"), "XL": Decimal("2099.00")},
                "fit_guide": "Clean straight silhouette. Take your normal size.",
                "fabric_and_care": "100% Organic Peruvian Pima Cotton (220 GSM). Machine wash cold, dry flat.",
                "final_sale": False,
                "stock": 60,
                "size_breakdown": {"XS": 10, "S": 15, "M": 18, "L": 12, "XL": 5},
                "image_filename": "product.jpg",
                "remote_image_url": "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=1200&q=85",
                "accent_tag": "220 GSM Peruvian Pima",
            },
            {
                "product_id": "PRD-005",
                "sku": "PRD-005-NVY",
                "name": "Kids Organic Merino Crewneck",
                "description": "Ultra-soft itch-free superfine merino knit pullover for children.",
                "category_id": "CAT-30",  # product type
                "materials": [("Merino Wool", 100)],
                "department": "KIDS",
                "hsn_code": "6110",
                "color": "Midnight Navy",
                # Per-size prices: each size is its own SKU ("PRD-005-NVY-<SIZE>") and price.
                "variant_prices": {"4Y": Decimal("1899.00"), "6Y": Decimal("1999.00"), "8Y": Decimal("2199.00"), "10Y": Decimal("2299.00"), "12Y": Decimal("2399.00")},
                "fit_guide": "Comfort kids cut with ribbed cuffs for room to grow.",
                "fabric_and_care": "100% Extra-Fine ZQ Merino Wool. Gentle wool cycle 30C, dry flat.",
                "final_sale": False,
                "stock": 35,
                "size_breakdown": {"4Y": 6, "6Y": 8, "8Y": 9, "10Y": 7, "12Y": 5},
                "image_filename": "product.jpg",
                "remote_image_url": "https://images.unsplash.com/photo-1519238263530-99bdd11df2ea?auto=format&fit=crop&w=1200&q=85",
                "accent_tag": "Superfine ZQ Merino Knit",
            },
        ]

        for p in products_spec:
            img_filename = p.get("image_filename", "product.jpg")
            img_rel_key = f"products/{p['product_id']}/{img_filename}"
            img_target = object_store.root / img_rel_key
            if not img_target.exists() and "remote_image_url" in p:
                try:
                    import httpx
                    resp = httpx.get(p["remote_image_url"], timeout=10.0, follow_redirects=True)
                    if resp.status_code == 200:
                        object_store.put_bytes("products", p["product_id"], img_filename, resp.content)
                except Exception:
                    pass

            image_url = p.get("image_url") or f"/media/{img_rel_key}"

            prod = Product(
                product_id=p["product_id"],
                sku=p["sku"],
                name=p["name"],
                description=p["description"],
                category_id=p["category_id"],
                department=p["department"],
                mrp_inr=min(p["variant_prices"].values()),  # re-derived by set_variant_prices
                hsn_code=p["hsn_code"],
                color_id=color_ids[p["color"]],
                sizes_available=list(p["variant_prices"]),
                fit_guide=p["fit_guide"],
                fabric_and_care=p["fabric_and_care"],
                final_sale=p["final_sale"],
                security_tag_required=True,
            )
            session.add(prod)
            session.flush()
            set_variant_prices(session, prod, p["variant_prices"])
            for material, pct in p["materials"]:
                session.add(ProductMaterial(product_id=prod.product_id, material_id=material_ids[material], percentage=pct))
            session.add(
                ProductImage(
                    product_id=p["product_id"],
                    url=image_url,
                    alt_text=p["accent_tag"],
                    display_order=1,
                )
            )
            session.add(
                Inventory(
                    product_id=p["product_id"],
                    quantity_available=p["stock"],
                    quantity_reserved=0,
                    quantity_damaged=0,
                    size_breakdown=p["size_breakdown"],
                    low_stock_threshold=5,
                )
            )
            object_store.put_json(
                "products",
                p["product_id"],
                "meta.json",
                {
                    "product_id": p["product_id"],
                    "sku": p["sku"],
                    "name": p["name"],
                    "department": p["department"],
                    "variants": [
                        {"size": v.size, "sku": v.sku, "mrp_inr": str(v.mrp_inr)} for v in prod.variants
                    ],
                    "hsn_code": p["hsn_code"],
                    "image_url": image_url,
                    "accent_tag": p["accent_tag"],
                },
            )

        customers = [
            Customer(
                customer_id="CUS-001",
                name="Arjun Kumar",
                email="arjun@noir.test",
                phone="+91-9999000001",
                loyalty_tier="VIP_GOLD",
            ),
            Customer(
                customer_id="CUS-002",
                name="Priya Sharma",
                email="priya@noir.test",
                phone="+91-9999000002",
                loyalty_tier="STANDARD",
            ),
        ]
        session.add_all(customers)
        session.flush()

        addresses = [
            CustomerAddress(
                address_id="ADR-001",
                customer_id="CUS-001",
                label="Home",
                street="14 Cathedral Road, Gopalapuram",
                city="Chennai",
                state="Tamil Nadu",
                pin_code="600086",
                is_primary=True,
            ),
            CustomerAddress(
                address_id="ADR-002",
                customer_id="CUS-002",
                label="Work",
                street="88 Lavelle Road",
                city="Bengaluru",
                state="Karnataka",
                pin_code="560001",
                is_primary=True,
            ),
        ]
        session.add_all(addresses)

        session.add_all(
            [
                ProductReview(
                    product_id="PRD-001",
                    customer_id="CUS-001",
                    rating=5,
                    fit_feedback="true_to_size",
                    comment="Exceptional European flax linen drape and breathable weave.",
                ),
                ProductReview(
                    product_id="PRD-002",
                    customer_id="CUS-001",
                    rating=5,
                    fit_feedback="true_to_size",
                    comment="Architectural tailoring with horn buttons.",
                ),
                ProductReview(
                    product_id="PRD-003",
                    customer_id="CUS-002",
                    rating=5,
                    fit_feedback="true_to_size",
                    comment="22-Momme mulberry silk crepe feels extraordinary.",
                ),
                ProductReview(
                    product_id="PRD-004",
                    customer_id="CUS-002",
                    rating=5,
                    fit_feedback="true_to_size",
                    comment="Crisp Peruvian Pima cotton jersey.",
                ),
                ProductReview(
                    product_id="PRD-005",
                    customer_id="CUS-001",
                    rating=5,
                    fit_feedback="true_to_size",
                    comment="Superfine itch-free ZQ merino knit for kids.",
                ),
                Recommendation(
                    source_product_id="PRD-001",
                    recommended_product_id="PRD-002",
                    relation_type="complete_the_look",
                    score=Decimal("0.9600"),
                ),
                Recommendation(
                    source_product_id="PRD-002",
                    recommended_product_id="PRD-001",
                    relation_type="complete_the_look",
                    score=Decimal("0.9500"),
                ),
                Recommendation(
                    source_product_id="PRD-003",
                    recommended_product_id="PRD-004",
                    relation_type="complete_the_look",
                    score=Decimal("0.9400"),
                ),
                Recommendation(
                    source_product_id="PRD-004",
                    recommended_product_id="PRD-003",
                    relation_type="complete_the_look",
                    score=Decimal("0.9300"),
                ),
                Recommendation(
                    source_product_id="PRD-005",
                    recommended_product_id="PRD-001",
                    relation_type="family_matching_edit",
                    score=Decimal("0.9100"),
                ),
            ]
        )

        session.add_all(
            [
                CustomerPreference(
                    customer_id="CUS-001",
                    preferred_department="MEN",
                    preferred_sizes={"top": "M", "outerwear": "L"},
                    referral_code="NOIR-ARJUN",
                ),
                CustomerPreference(
                    customer_id="CUS-002",
                    preferred_department="WOMEN",
                    preferred_sizes={"dress": "S", "top": "M"},
                    referral_code="NOIR-PRIYA",
                ),
            ]
        )

        configs = [
            BusinessConfig(
                config_key="store",
                config_value={
                    "name": "Noir Atelier",
                    "domain": "premium_garments_only",
                    "departments": ["MEN", "WOMEN", "KIDS"],
                    "currency": "INR",
                    "timezone": "Asia/Kolkata",
                    "grievance_officer": "Meera Krishnan (grievance@noir.test)",
                },
            ),
            BusinessConfig(
                config_key="storefront_ui",
                config_value={
                    "hero_eyebrow": "Tailored luxury garments",
                    "hero_title": "The New Edit",
                    "hero_subtitle": "Belgian linen shirts, mulberry silk dresses and superfine merino knitwear, tailored in India for Men, Women and Kids.",
                    "hero_image_url": "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=1200&q=85",
                    "hero_image_alt": "Noir Atelier Editorial Collection",
                    "ai_quick_prompts": [
                        {"label": "Linen for men under \u20b93,000", "prompt": "Show me Men's garments under INR 3000", "audience": "customer"},
                        {"label": "Women's silk and cotton", "prompt": "Show me Women's garments", "audience": "customer"},
                        {"label": "Returns and delivery info", "prompt": "What are the return policy rules and GST slabs?", "audience": "customer"},
                        {"label": "Sales report", "prompt": "Show GMV and order analytics report", "audience": "staff"},
                    ],
                },
            ),
            BusinessConfig(
                config_key="tax",
                config_value={
                    "mrp_inclusive": True,
                    "mock_gstin": "33MOCKA1234Z1Z5",
                    "origin_state": "Tamil Nadu",
                    "origin_state_code": "33",
                    "hsn_chapters": ["61", "62"],
                    "garment_slab_threshold_inr": 2500,
                    "rate_upto_threshold": 0.05,
                    "rate_above_threshold": 0.18,
                },
            ),
            BusinessConfig(
                config_key="shipping",
                config_value={
                    "free_shipping_threshold_inr": 1999,
                    "default_shipping_fee_inr": 99,
                    "cod_allowed": False,
                    "signature_required_above_inr": 5000,
                },
            ),
            BusinessConfig(
                config_key="returns_and_refunds",
                config_value={
                    "return_window_days": 7,
                    "window_starts_from": "delivered_date",
                    "require_security_tag_intact": True,
                    "require_warehouse_qc_pass": True,
                    "tiers": {
                        "tier_0_pre_ship_cancel_max_inr": 50000,
                        "tier_1_auto_refund_max_inr": 5000,
                        "tier_2_manager_approval_max_inr": 25000,
                        "tier_3_dual_approval_max_inr": 50000,
                    },
                },
            ),
            BusinessConfig(
                config_key="catalog",
                config_value={
                    "luxury_tier_min_inr": 7000,
                    "fit_feedback_options": list(FIT_FEEDBACK_OPTIONS),
                },
            ),
        ]
        session.add_all(configs)

        session.add_all(
            [
                Coupon(
                    code="ATELIER10",
                    discount_type="percent",
                    discount_value=Decimal("10.00"),
                    min_order_value_inr=Decimal("2000.00"),
                    max_discount_inr=Decimal("1000.00"),
                ),
                Coupon(
                    code="SUMMER20",
                    discount_type="percent",
                    discount_value=Decimal("5.00"),
                    min_order_value_inr=Decimal("1500.00"),
                    max_discount_inr=Decimal("750.00"),
                ),
            ]
        )

        session.add_all(
            [
                PaymentMethod(
                    method_id="upi",
                    name="UPI (Instant · Up to ₹1,00,000)",
                    min_order_inr=Decimal("1.00"),
                    max_order_inr=Decimal("100000.00"),
                ),
                PaymentMethod(
                    method_id="card",
                    name="Credit / Debit Card",
                    min_order_inr=Decimal("1.00"),
                    max_order_inr=Decimal("1500000.00"),
                ),
                PaymentMethod(
                    method_id="bank_transfer",
                    name="IMPS / RTGS / NEFT Private Wire",
                    min_order_inr=Decimal("1.00"),
                    max_order_inr=Decimal("5000000.00"),
                ),
                PaymentMethod(
                    method_id="emi",
                    name="No-Cost Atelier EMI",
                    min_order_inr=Decimal("5000.00"),
                    max_order_inr=Decimal("500000.00"),
                ),
            ]
        )

        session.add_all(
            [
                ShippingZone(
                    zone_id="ZON-MET",
                    name="Metro Express",
                    pin_prefixes=["600", "560", "400", "110", "500", "700"],
                    base_fee_inr=Decimal("99.00"),
                    estimated_days=2,
                ),
                ShippingZone(
                    zone_id="ZON-TR2",
                    name="Tier-2 Cities",
                    pin_prefixes=["641", "620", "625", "411", "380", "302"],
                    base_fee_inr=Decimal("149.00"),
                    estimated_days=3,
                ),
            ]
        )

        session.add_all(
            [
                Policy(
                    policy_id="POL-RET-01",
                    topic="returns",
                    title="7-Day Atelier Return & Physical QC Policy",
                    rule_text=(
                        "Full-price Noir Atelier garments (Men, Women, Kids) may be returned within 7 calendar days "
                        "of the confirmed delivery date. Garments must be unworn, unwashed, and pass warehouse QC with "
                        "the Noir Atelier security ribbon and tags intact."
                    ),
                    return_window_days=7,
                ),
                Policy(
                    policy_id="POL-RET-02",
                    topic="final_sale",
                    title="Archive & Final Sale Policy",
                    rule_text=(
                        "Garments marked Final Sale are strictly non-returnable and non-refundable for change of mind."
                    ),
                    return_window_days=0,
                ),
                Policy(
                    policy_id="POL-VIP-01",
                    topic="vip_loyalty",
                    title="VIP Gold Extended Return Privilege",
                    rule_text=(
                        "VIP_GOLD members receive a 14-day return window on standard garments; Final Sale conflicts "
                        "are routed to a Store Manager (Tier 2) for review."
                    ),
                    return_window_days=14,
                ),
                Policy(
                    policy_id="POL-CAN-01",
                    topic="cancellations",
                    title="Pre-Shipment Order Cancellation (Tier 0)",
                    rule_text=(
                        "Orders in confirmed or processing state prior to courier dispatch can be cancelled immediately "
                        "for a full refund."
                    ),
                ),
            ]
        )

        permissions = [
            AgentPermission(
                agent_type="catalog_agent",
                service_account="svc-catalog",
                resource_type="products",
                action="read",
                allowed_endpoints=[
                    "/api/products/search",
                    "/api/products/{id}",
                    "/api/products/{id}/recommendations",
                    "/api/categories",
                    "/api/catalog/meta",
                    "/api/catalog/search",
                ],
            ),
            AgentPermission(
                agent_type="cart_agent",
                service_account="svc-cart",
                resource_type="cart",
                action="write",
                allowed_endpoints=["/api/cart/add", "/api/cart/remove/{item_id}", "/api/cart", "/api/cart/clear", "/api/coupons/validate", "/api/orders/calculate"],
            ),
            AgentPermission(
                agent_type="order_agent",
                service_account="svc-order",
                resource_type="orders",
                action="write",
                allowed_endpoints=[
                    "/api/orders",
                    "/api/orders/hold",
                    "/api/orders/sweep-expired",
                    "/api/orders/{id}",
                    "/api/orders/{id}/cancel",
                    "/api/orders/{id}/pickup-claim",
                    "/api/payments/initiate",
                    "/api/payments/webhook",
                    "/api/payments/demo/{id}",
                ],
                max_value_inr=50000,
            ),
            AgentPermission(
                agent_type="fulfillment_agent",
                service_account="svc-fulfillment",
                resource_type="shipments",
                action="write",
                allowed_endpoints=["/api/shipments/{id}", "/api/shipments/schedule", "/api/inventory/reserve"],
            ),
            AgentPermission(
                agent_type="support_agent",
                service_account="svc-support",
                resource_type="support_tickets",
                action="write",
                allowed_endpoints=["/api/orders/{id}", "/api/refunds", "/api/returns", "/api/support/escalate"],
            ),
            AgentPermission(
                agent_type="returns_agent",
                service_account="svc-returns",
                resource_type="returns",
                action="write",
                allowed_endpoints=["/api/returns", "/api/returns/{id}", "/api/refunds/{id}/approve", "/api/refunds/{id}/process", "/api/inventory/restock"],
                max_value_inr=5000,
            ),
            AgentPermission(
                agent_type="inventory_agent",
                service_account="svc-inventory",
                resource_type="inventory",
                action="write",
                allowed_endpoints=["/api/inventory/list", "/api/inventory/{id}", "/api/products/{id}/discontinue"],
            ),
            AgentPermission(
                agent_type="analytics_agent",
                service_account="svc-analytics",
                resource_type="analytics",
                action="read",
                allowed_endpoints=["/api/orders/analytics", "/api/customers/analytics", "/api/products/analytics"],
            ),
            AgentPermission(
                agent_type="config_agent",
                service_account="svc-config",
                resource_type="business_config",
                action="admin",
                allowed_endpoints=["/api/config/policies", "/api/admin/config/policies", "/api/audit/log"],
            ),
        ]
        session.add_all(permissions)
        session.commit()

        return {
            "status": "seeded",
            "categories": len(CATEGORIES),
            "products": len(products_spec),
            "customers": len(customers),
            "agent_permissions": len(permissions),
        }


if __name__ == "__main__":
    force_reset = "--reset" in sys.argv
    settings = get_settings()
    engine = create_engine(settings.database_sync_url)
    if force_reset:
        Base.metadata.drop_all(bind=engine)
    result = seed_database(engine)
    print("Database seed result:", result)
