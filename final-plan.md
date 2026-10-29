# Noir Atelier — Final Execution Plan (`final-plan.md`)

**Brand:** Noir Atelier Apparel Co. (Indian D2C Contemporary Fashion)  
**Architecture Standard:** Multi-Agent Retail System (FastAPI + PostgreSQL 16 + Redis + Qdrant + Local Object Storage)  
**Status:** Execution Blueprint (Ready for Phase-by-Phase Build)

---

## 1. Current State Audit ("What Is Now There") & Existing Whitelist

### 1.1 What Currently Exists in the Repository
The repository currently contains a working **Phase 0 Customer Support Agent Prototype** built with Python, SQLite, and a deterministic + LLM hybrid loop:

| Component | Current File(s) | What Exists Today |
|---|---|---|
| **Core Support Agent** | `src/agent.py`, `src/llm_agent.py` | Single `CustomerSupportAgent` handling product lookup, policy Q&A, order status, returns/cancellations, and human escalation. |
| **LLM Backends** | `src/llm_backends.py` | OpenAI API (`gpt-4o-mini`), Claude Code CLI (`claude -p`), and deterministic fallback (`hybrid`). |
| **Data Store** | `src/data_store.py`, `data/noir_atelier.db` | Local SQLite database seeded from `data/*.json` (5 products in USD, 5 customers, 6 orders, 6 policies). |
| **Input & Output Guardrails** | `src/guardrails.py` | Prompt injection regex blocker, unsafe action blocker, PII leak scrubber, 3-strike verification lockout. |
| **Evaluation & Failure Suite** | `tests/`, `evals/` | 26 unit/adversarial tests + 16 repeatable evaluation cases (`100%` pass rate). |
| **CLI Runner** | `cli.py` | Interactive terminal chat (`/verify`, `/orders`, `/products`, `/policies`, `/fail`) and `--demo` walkthrough. |

### 1.2 Current Whitelist (`ToolPolicyGate` in `src/llm_agent.py`)
Currently, the system enforces a strict **5-tool whitelist** (`ALLOWED_TOOLS`) and deterministic parameter gate:

```python
ALLOWED_TOOLS = (
    "lookup_products",           # Read-only catalog search
    "lookup_policies",           # Read-only store policy lookup
    "get_order_status",          # Requires verified (order_id + customer_email) from user message
    "process_return_or_cancel",  # Requires explicit 'return'/'cancel' intent + verified ownership + max 1/turn
    "escalate_to_human",         # Max 1 escalation ticket per turn
)
```
**Current Whitelist Rules Enforced in Code:**
1. **Tool Name Whitelist:** Any tool outside `ALLOWED_TOOLS` is rejected before execution.
2. **Identity Parameter Whitelist (`CustomerFacts`):** The LLM cannot invent or guess an `order_id`, `customer_email`, or `request_key`—the exact string must appear in the customer's message or verified session.
3. **Mutation Intent Whitelist:** `process_return_or_cancel` is blocked unless the user explicitly asked to return, refund, or cancel (exchange requests are blocked from auto-refunding and forced to escalate).
4. **Rate/Turn Cap Whitelist:** Max `1` mutation and `1` escalation per turn; max `6` reasoning steps per turn; max `3` failed verification attempts before session lockout.
5. **PII Output Whitelist:** Outbound replies are scrubbed of any email, phone number, or street address not belonging to `verified_emails`.

---

## 2. Gap Analysis: Current Repo vs. Full Noir Atelier Architecture Plan

| Dimension | Current State (Repo Today) | Target State (Noir Atelier Architecture Plan) | The Gap to Fulfill |
|---|---|---|---|
| **Agent Network** | **1 Agent** (`CustomerSupportAgent`) with 5 tools | **9 Specialized Agents** (`Catalog`, `Shopping`, `Order`, `Payment`, `Fulfillment`, `Returns`, `Support`, `Compliance`, `Admin`) + **Intent Router** | Build 8 new domain agents + central `AgentOrchestrator` with per-agent tool whitelists and inter-agent handoffs. |
| **Transactional DB** | **SQLite** (`data/noir_atelier.db`) | **PostgreSQL 16+** (ACID transactions, JSONB, connection pooling, migrations) | Replace SQLite with PostgreSQL 16+ schema covering carts, payments, shipments, GST invoices, audit logs, and DPDP consent. |
| **Vector Search** | None (SQL `LIKE` keyword matching only) | **Qdrant Vector DB** (hybrid semantic search + metadata payload filtering) | Add Qdrant service, embedding pipeline, and `search_by_style` / `get_recommendations` tools for `CatalogAgent`. |
| **Cache & State** | In-memory Python dicts (`self.history`) | **Redis** (sessions, live cart state, inventory cache, rate limits) | Add Redis store with TTL management (`30m` cart, `24h` session/catalog cache, auth lockout counters). |
| **Full-Text Search** | Basic substring matching | **PostgreSQL FTS (`tsvector` + `GIN`) now** → **Elasticsearch later** (>10K products) | Implement PostgreSQL full-text search + synonym dictionary (`tee` → `t-shirt`, `kurta` → `tunic`) with clean search adapter interface for future Elasticsearch swap. |
| **Object Storage** | None | **Local Structured Object Storage (`storage/`)** with short, human-readable IDs | Create local object store manager for product media, GST invoices, bank transfer receipts, and return damage photos. |
| **Localization & Tax** | USD (`$`), no tax logic | **INR (`₹`)**, Indian PIN serviceability, **5% Clothing GST (HSN)**, ₹1,999 free shipping rule, No COD | Migrate seed catalog & pricing to INR (`₹`), add GST calculator, PIN code validator, and India compliance rules (DPDP Act 2023, Consumer Protection Act). |
| **API & Audit Layer** | CLI-only (`cli.py`), in-memory turn trace | **FastAPI Service** + **Immutable JSON Audit Log** (`trace_id` across every hop) | Build FastAPI endpoints (`/chat`, `/cart`, `/checkout`, `/orders`, `/admin`) and structured JSON + PostgreSQL audit logging. |

---

## 3. Technology Stack We Follow (Confirmed Execution Decisions)

We follow the lean, high-performance **Phase 1–2 Production Stack** designed for Indian retail scale, with zero unnecessary bloat:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   Presentation / Client Layer                           │
│        CLI + FastAPI REST / SSE Endpoints (Next.js Ready)               │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────┐
│             Agent Orchestration & Security Layer (FastAPI)              │
│   [Input Guardrails] -> [Intent Classifier] -> [Per-Agent Whitelist]    │
│   ├─ 1. Catalog Agent      ├─ 4. Payment Agent    ├─ 7. Support Agent   │
│   ├─ 2. Shopping Agent     ├─ 5. Fulfillment Agent├─ 8. Compliance Agent│
│   └─ 3. Order Agent        └─ 6. Returns Agent    └─ 9. Admin Agent     │
└───────┬───────────────────┬────────────────────┬────────────────────┬───┘
        │                   │                    │                    │
        ▼                   ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ PostgreSQL 16 │   │     Redis     │    │    Qdrant     │    │ Local Object  │
│  Transactional│   │ Cache & State │    │   Vector DB   │    │    Storage    │
│  + FTS Search │   │  Sessions,    │    │   Semantic    │    │  ./storage/   │
│  Orders, Tax, │   │  Cart (30m),  │    │ Style Search  │    │  Short IDs    │
│  Users, Audit │   │  Locks, Stock │    │ + Filters     │    │  (PRD/ORD/..) │
└───────────────┘   └───────────────┘    └───────────────┘    └───────────────┘
```

### Stack Decisions Summary
1. **Transactional Database → PostgreSQL 16+**: Single source of truth for customers, products, inventory, orders, payments, shipments, returns, policies, and immutable audit logs.
2. **Vector Database → Qdrant**: Self-hosted via Docker (`qdrant/qdrant`). Powers `search_by_style` (*"minimalist black office shirt under ₹1,500"*) combining dense embeddings with payload filters (`price <= 1500`, `color = black`, `in_stock = true`).
3. **Cache & Ephemeral State → Redis 7+**: Stores active shopping carts (`TTL: 30m`), customer sessions (`TTL: 24h`), hot product/inventory cache (`TTL: 24h`), and verification lockout counters.
4. **Full-Text Search → PostgreSQL FTS Now (Elasticsearch Deferred)**: Uses PostgreSQL `tsvector` + `GIN` indexes + Indian fashion synonym dictionary in Phase 1–3. Abstracted behind `SearchProvider` so Elasticsearch drops in seamlessly when catalog exceeds 10,000 SKUs.
5. **Object Storage → Local Structured Filesystem (`./storage/`)**: Clean folder hierarchy indexed by short, human-readable IDs (no long UUIDs), with an S3/MinIO-compatible path convention.
6. **Why No MongoDB in Core Transactions**: Order, inventory, payment, and refund state require strict multi-table ACID transactions provided by PostgreSQL 16, while flexible schemas (product attributes, policy rules, agent traces) use PostgreSQL `JSONB` columns with GIN indexing.

---

## 4. Short Human-Readable ID Standard & Local Object Storage Layout

To keep the system transparent for customers, support agents, and developers, **every entity and folder uses short, deterministic, human-readable IDs (6–10 characters max)**—never 36-character UUIDs.

### 4.1 Short ID Naming Standard

| Entity | Prefix | Format | Example | Max Length | Where Used |
|---|---|---|---|---|---|
| **Product** | `PRD` | `PRD-XXX` | `PRD-001` | 7 chars | DB, Qdrant point metadata, `storage/products/PRD-001/` |
| **Product Variant** | `SKU` | `PRD-XXX-CLR-SZ` | `PRD-001-BLK-M` | 13 chars | Inventory, Cart, Order Items |
| **Customer** | `CUS` | `CUS-XXX` | `CUS-101` | 7 chars | DB, Redis session, `storage/customers/CUS-101/` |
| **Shopping Cart** | `CRT` | `CRT-XXX` | `CRT-101` | 7 chars | Redis key `cart:CUS-101` |
| **Order** | `ORD` | `ORD-XXXX` | `ORD-1001` | 8 chars | DB, Invoices, `storage/orders/ORD-1001/` |
| **Invoice** | `INV` | `INV-XXXX` | `INV-1001` | 8 chars | GST Tax Invoice PDF (`INV-1001.pdf`) |
| **Payment** | `PAY` | `PAY-XXXX` | `PAY-5001` | 8 chars | Payment gateway & bank transfer receipts |
| **Refund** | `REF` | `REF-XXXX` | `REF-8801` | 8 chars | Refund confirmation & ledger |
| **Shipment / AWB** | `SHP` | `SHP-XXXX` | `SHP-3001` | 8 chars | Courier AWB label & proof of delivery |
| **Return / Exchange** | `RET` | `RET-XXXX` | `RET-8802` | 8 chars | RMA folder (`storage/returns/RET-8802/`) |
| **Support Ticket** | `TKT` | `TKT-XXXX` | `TKT-4001` | 8 chars | Support inquiries |
| **Escalation** | `ESC` | `ESC-XXXX` | `ESC-9001` | 8 chars | Human specialist handoffs |
| **Policy** | `POL` | `POL-CAT-XX` | `POL-RET-01` | 10 chars | Store & compliance policies |
| **Idempotency Key** | `REQ` | `REQ-ORD-XXXX-ACT` | `REQ-ORD-1001-RET` | 16 chars | Duplicate request protection |

### 4.2 Local Object Storage Directory Hierarchy (`./storage/`)
All binary assets, generated invoices, receipts, and attachments live under `./storage/` organized by entity type and short ID:

```text
storage/
├── products/
│   ├── PRD-001/                      # Classic Cotton T-Shirt
│   │   ├── main.jpg                  # Primary storefront image
│   │   ├── back.jpg                  # Secondary angle
│   │   ├── size-chart.png            # Visual fit guide
│   │   └── meta.json                 # Local asset manifest
│   ├── PRD-002/                      # Metro Fleece Zip Hoodie
│   └── PRD-003/                      # Archive Distressed Denim Jacket
│
├── orders/
│   ├── ORD-1001/
│   │   ├── INV-1001.json             # Structured GST Invoice (HSN + 5% CGST/SGST/IGST)
│   │   ├── INV-1001.txt              # Printable human-readable tax invoice
│   │   └── SHP-3001-label.txt        # Courier shipping label & AWB summary
│   └── ORD-1002/
│
├── payments/
│   └── PAY-5001/
│       └── receipt-ORD-1001.json     # Tokenized UPI / Bank transfer verification receipt
│
├── returns/
│   └── RET-8802/
│       ├── defect-photo-1.jpg        # Customer uploaded damage/defect evidence
│       └── inspection-note.json      # Warehouse QA inspection report
│
├── support/
│   └── ESC-9001/
│       └── transcript-ORD-1001.json  # Escalation context snapshot for human specialist
│
└── compliance/
    └── POL-RET-01/
        └── approval-cert.json        # Compliance Agent publication sign-off record
```

---

## 5. Multi-Agent Network & Per-Agent Whitelist Matrix

Instead of a single global tool list, the `ToolPolicyGate` enforces **Role-Based Agent Whitelists (RBAC)**. Each agent can only invoke its whitelisted tools and can only read/write its designated database tables.

| # | Agent | Read Scope | Write Scope | Whitelisted Tools (`ALLOWED_TOOLS` per Agent) | Mandatory Gate & Escalation Rules |
|---|---|---|---|---|---|
| **1** | **Catalog Agent** (`catalog_agent`) | `products`, `inventory`, Qdrant `products_vec` | *None (Strictly Read-Only)* | `search_products`, `get_product_details`, `get_inventory`, `get_recommendations`, `search_by_style` | Cannot modify prices, stock, or carts. Escalates sourcing/sustainability claims to `ComplianceAgent`. |
| **2** | **Shopping Agent** (`shopping_agent`) | `products`, `inventory`, `coupons`, `shipping_rules` | Redis `cart:*`, `wishlists` | `add_to_cart`, `remove_from_cart`, `apply_coupon`, `calculate_total`, `get_shipping_estimate`, `validate_cart` | Blocks out-of-stock adds. Enforces 5% clothing GST and free shipping on `>= ₹1,999` (else `₹99`). |
| **3** | **Order Agent** (`order_agent`) | Redis `cart:*`, `customers`, `orders`, `pin_codes` | `orders`, `order_items` | `create_order`, `get_payment_methods`, `initiate_payment`, `confirm_order`, `get_order_status` | **No COD allowed.** Validates serviceable Indian PIN code. Blocks duplicate order within 5 mins. |
| **4** | **Payment Agent** (`payment_agent`) | `orders`, `payments`, `customers` | `payments`, `refunds` | `process_payment`, `verify_payment`, `process_refund`, `get_payment_status`, `detect_fraud` | Never stores raw card/UPI credentials. 30-min payment timeout releases stock. Flags high-value new-user orders. |
| **5** | **Fulfillment Agent** (`fulfillment_agent`) | `orders`, `shipments`, `pin_codes` | `shipments`, `orders.status` | `create_shipment`, `get_tracking`, `get_delivery_estimate`, `mark_delivered`, `handle_failed_delivery` | Requires delivery signature for orders `> ₹5,000`. Max 1 redelivery attempt before return-to-origin. |
| **6** | **Returns Agent** (`returns_agent`) | `orders`, `returns`, `policies`, `inventory` | `returns`, `idempotency_ledger` | `create_return_request`, `assess_return_eligibility`, `approve_exchange`, `approve_refund`, `escalate_to_legal_remedy` | Standard: 7-day window, unworn with tags. **Legal Remedy Override:** Defective/damaged items eligible regardless of window. Conflict (`VIP_GOLD` + `Final Sale`) -> escalate. |
| **7** | **Support Agent** (`support_agent`) | `orders`, `customers`, `policies`, `faqs`, `tickets` | `support_tickets`, `escalations` | `search_knowledge_base`, `create_support_ticket`, `get_customer_history`, `send_message`, `escalate_ticket` | Verifies `(order_id + customer_email)` before revealing order PII. 3 failed verifications lock session. |
| **8** | **Compliance Agent** (`compliance_agent`) | All policies, tax rules, marketing drafts, PII logs | `compliance_flags`, `policy_approvals` | `validate_against_policy`, `calculate_gst`, `validate_pii_handling`, `review_customer_communication`, `approve_for_publication` | Blocks unverified claims (*"handcrafted"*, *"sustainable"* without cert). Enforces DPDP Act 2023 & Consumer Protection Act. |
| **9** | **Admin Agent** (`admin_agent`) | All operational tables & metrics | `business_config`, `manual_overrides`, `audit_exports` | `update_business_config`, `create_manual_order`, `override_decision`, `get_metrics`, `export_data`, `generate_report` | Requires admin role token + mandatory `override_reason` logged to immutable `audit_logs`. |

---

## 6. Data Layer Deep-Dive (PostgreSQL + Redis + Qdrant)

### 6.1 PostgreSQL 16 Schema (`src/db/postgres_schema.sql`)
All tables use short primary keys (`PRD-001`, `CUS-101`, `ORD-1001`) and `TIMESTAMPTZ`:

1. **`customers`**: `customer_id` (`CUS-101`), `name`, `email` (unique), `phone`, `loyalty_tier` (`STANDARD`, `VIP_SILVER`, `VIP_GOLD`), `dpdp_consent` (boolean), `created_at`.
2. **`products`**: `product_id` (`PRD-001`), `name`, `category`, `price_inr` (`NUMERIC(10,2)`), `original_price_inr`, `hsn_code` (`6109`), `gst_rate_pct` (`5.00`), `fit_guide`, `fabric_and_care`, `final_sale`, `clearance`, `description`, `search_vector` (`TSVECTOR` with `GIN` index).
3. **`product_variants`**: `sku` (`PRD-001-BLK-M`), `product_id`, `color`, `size`, `stock_count`, `reserved_count`.
4. **`serviceable_pins`**: `pin_code` (`600001`, `560001`, `400001`, `110001`, etc.), `city`, `state`, `standard_days`, `express_available`.
5. **`coupons`**: `coupon_code` (`WELCOME10`), `discount_pct`, `max_discount_inr`, `min_cart_inr`, `active`.
6. **`orders`**: `order_id` (`ORD-1001`), `customer_id`, `customer_email`, `status` (`pending_payment`, `processing`, `shipped`, `delivered`, `cancelled`, `returned`), `subtotal_inr`, `gst_amount_inr`, `shipping_inr`, `discount_inr`, `total_inr`, `shipping_pin`, `shipping_city`, `signature_required`, `order_date`, `delivery_date`.
7. **`order_items`**: `id`, `order_id`, `product_id`, `sku`, `name`, `size`, `color`, `quantity`, `unit_price_inr`, `final_sale`.
8. **`payments`**: `payment_id` (`PAY-5001`), `order_id`, `method` (`UPI`, `CARD`, `NET_BANKING`, `BANK_TRANSFER`), `status` (`pending`, `confirmed`, `failed`, `refunded`), `amount_inr`, `gateway_ref`, `fraud_flag`, `created_at`.
9. **`shipments`**: `shipment_id` (`SHP-3001`), `order_id`, `courier` (`Shiprocket-Delhivery`, `BlueDart`), `awb_code` (`AWB-1001`), `status`, `estimated_delivery`, `delivered_at`, `signature_proof`, `failed_attempts`.
10. **`returns`**: `return_id` (`RET-8802`), `order_id`, `action` (`return`, `exchange`, `cancel`), `reason`, `is_defective`, `replacement_sku`, `refund_id` (`REF-8801`), `refund_amount_inr`, `status`, `request_key` (unique).
11. **`policies` & `policy_conflicts`**: `policy_id` (`POL-RET-01`), `topic`, `title`, `rule`, `applies_to`, `return_window_days`.
12. **`support_tickets` & `escalations`**: `ticket_id` (`TKT-4001` / `ESC-9001`), `customer_email`, `order_id`, `category`, `severity`, `assigned_agent`, `reason`, `status`.
13. **`audit_logs` (Immutable)**: `log_id`, `trace_id` (`TRC-90001`), `timestamp`, `agent_name`, `tool_name`, `input_json`, `output_json`, `decision_type`, `duration_ms`, `customer_email`, `order_id`.

### 6.2 Qdrant Vector DB Configuration (`src/db/qdrant_store.py`)
- **Collection Name:** `noir_atelier_products`
- **Vector Dimensions:** `384` (using lightweight fast local/deterministic dense embeddings or `1536` OpenAI `text-embedding-3-small` when `OPENAI_API_KEY` is configured, with automatic local fallback so offline dev/tests always work).
- **Indexed Payload Fields:**
  - `product_id`: keyword (`PRD-001`)
  - `category`: keyword (`Tops / Tees`, `Outerwear / Hoodies`, `Bottoms / Pants`, etc.)
  - `price_inr`: float (`1199.0`)
  - `colors`: keyword array (`["black", "navy"]`)
  - `sizes_in_stock`: keyword array (`["S", "M", "L", "XL"]`)
  - `final_sale`: bool (`false`)
  - `style_tags`: keyword array (`["minimalist", "office", "streetwear", "essentials", "formal"]`)

### 6.3 Redis Key Namespaces & TTLs (`src/db/redis_store.py`)
- `session:{session_id}` → Verified customer email, active `trace_id`, turn history (`TTL: 86400s` / 24h)
- `cart:{customer_id}` → JSON cart items, applied coupon, calculated totals (`TTL: 1800s` / 30m)
- `lockout:{session_id}` → Failed order verification counter (`TTL: 1800s` / 30m; locks at `>= 3`)
- `order_dedup:{customer_id}:{cart_hash}` → Prevents duplicate order submission (`TTL: 300s` / 5m)
- `cache:product:{product_id}` → Hot product + variant stock snapshot (`TTL: 86400s` / 24h, invalidated on stock mutation)

---

## 7. Phased Implementation Plan (Step-by-Step Execution)

We will execute this transition cleanly in **4 structured build stages** without breaking any existing tests or safety guarantees:

### Stage 1: Infrastructure, Docker Compose & Local Object Storage (`storage/`)
1. Create `docker-compose.yml` defining:
   - `postgres:16-alpine` (Port `5432`, DB `noir_atelier`)
   - `redis:7-alpine` (Port `6379`)
   - `qdrant/qdrant:latest` (Port `6333`)
2. Build **Graceful Local Fallback**: If Docker services aren't running during unit tests or offline evaluation, the data layer automatically falls back to embedded PostgreSQL-compatible SQLite + in-memory Redis + in-memory Qdrant cosine similarity so `pytest`/`unittest` and `cli.py` run with zero external setup friction.
3. Build `src/storage/object_store.py` managing `./storage/` with short IDs (`PRD-001`, `ORD-1001`, `INV-1001`, `PAY-5001`, `RET-8802`, `ESC-9001`) and seed initial product assets & sample GST invoices.

### Stage 2: PostgreSQL 16 + Redis + Qdrant Data Layer & INR/GST Catalog Migration
1. Create `src/db/postgres_schema.sql` with all 13 tables, full-text search indexes, and synonym expansion (`tee` ↔ `t-shirt`, `kurta` ↔ `tunic`).
2. Update `data/products.json`, `data/orders.json`, and `data/policies.json` to support Indian retail rules (INR `₹` pricing alongside backward-compatible test fixtures, HSN codes, 5% GST, ₹1,999 free shipping threshold, serviceable PIN codes).
3. Implement `src/db/qdrant_store.py` for semantic `search_by_style` and `get_recommendations`.
4. Implement `src/db/redis_store.py` for cart state (`30m TTL`), session state (`24h TTL`), and 5-minute duplicate checkout lock.

### Stage 3: The 9 Specialized Agents & Per-Agent Whitelist Gate
1. Create `src/agents/` module containing:
   - `catalog_agent.py` (5 tools)
   - `shopping_agent.py` (6 tools)
   - `order_agent.py` (5 tools)
   - `payment_agent.py` (5 tools)
   - `fulfillment_agent.py` (5 tools)
   - `returns_agent.py` (5 tools)
   - `support_agent.py` (5 tools)
   - `compliance_agent.py` (5 tools)
   - `admin_agent.py` (6 tools)
2. Upgrade `ToolPolicyGate` in `src/llm_agent.py` to enforce per-agent `ALLOWED_TOOLS`, read/write table boundaries, and inter-agent escalation routing.
3. Build `src/orchestrator.py` (`AgentOrchestrator`) with Intent Classification, `trace_id` propagation (`TRC-XXXXX`), and immutable audit logging.

### Stage 4: FastAPI Service, CLI Upgrade & Verification Suite
1. Create `app.py` (FastAPI server) exposing `/api/v1/chat`, `/api/v1/cart`, `/api/v1/checkout`, `/api/v1/orders/{order_id}`, `/api/v1/storage/{category}/{entity_id}`, and `/api/v1/admin/metrics`.
2. Upgrade `cli.py` to allow testing all 9 agents, inspecting `./storage/` files, viewing live audit traces, and running the 6 core workflows from the architecture doc.
3. Expand `tests/` and `evals/` to verify all 9 agents, Qdrant style search, Redis cart/session TTLs, GST/PIN validation, DPDP compliance, and all 6 failure modes.

---

## 8. Target Repository Structure

```text
Noir-Atelier/
├── docker-compose.yml                # PostgreSQL 16 + Redis 7 + Qdrant
├── final-plan.md                     # This execution blueprint
├── PRD.md                            # Product Requirements Document
├── README.md                         # Setup & Architecture Guide
├── app.py                            # FastAPI Orchestration & REST API Server
├── cli.py                            # Interactive Multi-Agent CLI & Demo Runner
├── requirements.txt                  # Dependencies (fastapi, psycopg, redis, qdrant-client, etc.)
├── data/                             # Seed JSON files (products, customers, orders, policies, pins)
├── storage/                          # Local Object Storage (Short IDs)
│   ├── products/PRD-001/
│   ├── orders/ORD-1001/INV-1001.json
│   ├── payments/PAY-5001/
│   ├── returns/RET-8802/
│   ├── support/ESC-9001/
│   └── compliance/POL-RET-01/
├── src/
│   ├── constants.py                  # Short ID formats, agent whitelists, GST/shipping constants
│   ├── config.py                     # Postgres, Redis, Qdrant, Storage & LLM settings
│   ├── models.py                     # Pydantic / Dataclass schemas & Trace records
│   ├── guardrails.py                 # Prompt injection, DPDP PII scrubber, Compliance checks
│   ├── orchestrator.py               # Intent Classifier + 9-Agent Router + Audit Logger
│   ├── db/
│   │   ├── postgres_schema.sql       # Full PostgreSQL 16 DDL + FTS GIN indexes
│   │   ├── redis_store.py            # Cart, Session, Lockout & Inventory cache
│   │   └── qdrant_store.py           # Vector embeddings & hybrid style search
│   ├── storage/
│   │   └── object_store.py           # Local folder & short-ID asset manager
│   └── agents/                       # 9 Specialized Domain Agents + Per-Agent Toolkits
│       ├── catalog_agent.py
│       ├── shopping_agent.py
│       ├── order_agent.py
│       ├── payment_agent.py
│       ├── fulfillment_agent.py
│       ├── returns_agent.py
│       ├── support_agent.py
│       ├── compliance_agent.py
│       └── admin_agent.py
├── tests/                            # Unit, Failure-Mode, Multi-Agent & Security Tests
└── evals/                            # Repeatable Evaluation Dataset & Runner
```
