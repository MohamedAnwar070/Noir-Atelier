# Noir Atelier — System Architecture & Execution Plan

**Domain:** Premium Garments Only — **Men · Women · Kids** (`HSN 61 / 62`)  
**Architecture Pattern:** Unified AI-Native Commerce Platform (Storefront, LangGraph Agents, and Admin Portal sharing one FastAPI + PostgreSQL 16 + Redis 7 + Qdrant backend)

---

## 1. Architectural Invariants (Core Basement Rules)

1. **Single Source of Truth:** Storefront UI (`Next.js`), AI Agents (`LangGraph`), and Admin Portal (`React`) call the exact same `/api/*` endpoints and transact against the same **PostgreSQL 16** database.
2. **Zero Direct DB Access from Agents:** The `agents/` package communicates strictly over HTTP with `/api/*` using scoped service-account tokens (`svc-catalog`, `svc-cart`, `svc-order`, `svc-returns`, etc.).
3. **Config-Driven Rules:** Tax slabs, shipping thresholds, return windows, and refund approval bands live in `business_config` (cached in Redis, invalidated on write). Zero hardcoded business thresholds in agent prompts or UI code.
4. **Short Deterministic IDs:** Every entity and storage path uses short, sortable, human-readable IDs (`PRD-001`, `ORD-1001`, `RET-1001`, `RFD-1001`, `INV-1001`, `SHP-1001`, `TKT-1001`).
5. **Immutable Audit Trail:** Every state mutation writes an append-only row to `audit_log` within the same database transaction (`actor_type`, `actor_id`, `on_behalf_of`, `resource_type`, `resource_id`, `action`, `reason`, `trace_id`).

---

## 2. Merchandise & Tax Domain (Premium Garments: Men, Women, Kids)

Noir Atelier sells **garments only** across three departments. Non-apparel categories (jewellery, footwear, cosmetics) are excluded.

| Department | Category ID | Example SKUs (Seed Catalog) | HSN Chapter | Price Range (INR, MRP Inclusive) |
|---|---|---|---|---|
| **Men** | `CAT-MEN` | `PRD-001` Tailored Belgian Linen Shirt (`₹2,499`), `PRD-002` Structured Wool-Blend Overshirt (`₹6,499`) | Ch. 61 / 62 | `₹1,999 – ₹14,999` |
| **Women** | `CAT-WMN` | `PRD-003` Silk-Crepe Midi Dress (`₹7,999`), `PRD-004` Minimalist Pima Cotton Tee (`₹1,899`) | Ch. 61 / 62 | `₹1,899 – ₹18,999` |
| **Kids** | `CAT-KID` | `PRD-005` Kids Organic Merino Crewneck (`₹2,199`) | Ch. 61 / 62 | `₹1,299 – ₹4,999` |

### GST & Pricing Rules (`tax_service.py`)
- **MRP Inclusive of All Taxes:** Storefront and agent prices are displayed as GST-inclusive MRP per India Legal Metrology rules.
- **Apparel GST Slabs (HSN 61/62, per piece after discount):**
  - Net sale value **`<= ₹2,500` per piece** → **5% GST** (`2.5% CGST + 2.5% SGST` intra-state; `5% IGST` inter-state)
  - Net sale value **`> ₹2,500` per piece** → **18% GST** (`9% CGST + 9% SGST` intra-state; `18% IGST` inter-state)
- **Shipping Rule:** Free shipping on post-discount order value **`>= ₹1,999`**; otherwise `₹99` Metro / `₹149` Tier-2 / `₹249` Tier-3. No Cash-on-Delivery (COD).

---

## 3. Premium Garment Return & Refund Approval Architecture

Premium apparel requires **physical condition verification (security ribbon / atelier tag intact)** before releasing funds, preventing wardrobing while keeping genuine returns frictionless.

### 3.1 Return Lifecycle State Machine
`REQUESTED` → `LABEL_ISSUED` → `IN_TRANSIT` → `QC_INSPECTED` (`qc_passed: true | false`) → `APPROVED` / `ESCALATED` → `REFUNDED` + `RESTOCKED`

### 3.2 4-Tier Refund Approval Matrix (Enforced by `returns_service.py` + `agent_permissions`)

| Tier | Scenario & Value Band | Preconditions | Approver | System Enforcement |
|---|---|---|---|---|
| **Tier 0** | **Pre-Shipment Cancellation** (any value `<= ₹50,000`) | `order.status in ('confirmed', 'processing')` and shipment not dispatched | **Auto (`svc-order`)** | Immediate payment void/refund; reserved stock released |
| **Tier 1** | **Standard Garment Return (`<= ₹5,000`)** | Within **7 days of `delivered_date`**, `final_sale == false`, `qc_passed == true`, security tag intact | **Auto (`svc-returns`)** | Auto-refund to original payment method; restock inventory |
| **Tier 2** | **Premium / Archive Garment (`₹5,001 – ₹25,000`)** or **VIP Gold Final-Sale Conflict** | Within 7-day window + `qc_passed == true` (or policy conflict detected) | **Store Manager (`role: manager`)** | Agent creates return & sets `refund.status = 'pending_approval'`; manager approves via Admin Portal |
| **Tier 3** | **Couture / Multi-Item (`> ₹25,000`)** or **Defective / Damaged Claim Outside 7-Day Window** | Mandatory photo evidence in `storage/returns/RET-XXXX/` + QA inspection note | **Dual Approval (`manager` + `finance_admin`)** | Segregation of duties; hard ceiling of `₹50,000` for single-approver actions |

---

## 4. Tech Stack & Layer Architecture

| Layer | Technology | Role |
|---|---|---|
| **Core API** | FastAPI (Python 3.11+), SQLAlchemy 2.0 (async), Pydantic v2, Alembic | Shared REST API for Storefront, Agents, and Admin |
| **Primary DB** | **PostgreSQL 16** | 32 normalized tables (3NF), ACID transactions, `tsvector` FTS, monthly `orders` partitioning |
| **Cache & Queue** | **Redis 7** + **Celery** | Config cache (`1h`), product cache (`30m`), stock cache (`5m`), session/lockout (`30m`), async jobs |
| **Vector DB** | **Qdrant** | Product style embeddings (`products` collection) & customer preference vectors (`customers` collection) |
| **Search** | **PostgreSQL FTS** (`SEARCH_PROVIDER=postgres`) → **Elasticsearch 8** (`SEARCH_PROVIDER=elasticsearch`) | Pluggable `SearchProvider` toggled via `.env` |
| **Object Storage** | **Local Filesystem (`./storage/`)** → S3/MinIO ready | Short-ID folder hierarchy served via `/media/*` (public) and signed/authorized endpoints (private) |
| **Agents** | **LangGraph** + **Claude** (Anthropic API, optional OpenAI fallback) | 9 state-machine agents calling `/api/*` via `httpx` |
| **Frontend** | **Next.js 14+** (Storefront) + **React** (Admin Portal), TailwindCSS, TanStack Query, Zod | Monorepo under `frontend/` |

---

## 5. Basement Directory Structure

```text
Noir-Atelier/
├── .env.example                    # Focused environment template (selectable providers)
├── .env                            # Local active configuration (git-ignored)
├── .gitignore
├── docker-compose.yml              # postgres:16, redis:7, qdrant (optional elasticsearch profile)
├── final-plan.md                   # Architecture & execution blueprint
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── app/
│   │   ├── main.py                 # FastAPI entrypoint & router registration
│   │   ├── config.py               # Typed Settings loaded from .env
│   │   ├── database.py             # Async SQLAlchemy 2.0 engine & session factory
│   │   ├── auth.py                 # JWT (customer/admin) & Service Account (agent) auth
│   │   ├── api/                    # products, cart, orders, customers, returns, config, admin, audit
│   │   ├── services/               # product, cart, order, inventory, payment, fulfillment, returns, tax, config, audit
│   │   ├── models/                 # 32 SQLAlchemy 2.0 ORM models
│   │   ├── schemas/                # Pydantic v2 DTOs
│   │   ├── search/                 # SearchProvider (postgres_fts.py, elastic.py)
│   │   ├── vectors/                # Qdrant client & embedding pipeline
│   │   ├── storage/                # LocalObjectStore (short-ID path resolver)
│   │   ├── tasks/                  # Celery tasks (fulfillment, inventory_sync, email_notifications)
│   │   └── utils/                  # id_generator, exceptions, logging, validators
│   ├── migrations/                 # Alembic versions
│   ├── scripts/
│   │   └── seed_demo.py            # Seeds Men/Women/Kids garments, customers, business_config
│   └── tests/
│       ├── unit/
│       └── integration/
├── agents/
│   ├── main.py                     # LangGraph compiled state machine entrypoint
│   ├── client.py                   # Scoped async HTTP client for /api/*
│   ├── gateway.py                  # ToolPolicyGate, prompt-injection guardrails, PII scrubber
│   ├── tools/                      # product_tools, cart_tools, order_tools, refund_tools, config_tools
│   ├── nodes/                      # catalog, cart, order, fulfillment, returns, support, inventory, analytics, config
│   ├── schemas/                    # AgentState & tool input/output schemas
│   ├── prompts/                    # Versioned system prompts per agent
│   └── tests/
├── frontend/
│   ├── apps/
│   │   ├── storefront/             # Customer Next.js app
│   │   └── admin/                  # Staff Admin portal
│   └── packages/
│       ├── ui/
│       ├── api/
│       └── utils/
├── storage/                        # Local Object Storage (Short IDs)
│   ├── products/                   # PRD-001/01.jpg, size-chart.png
│   ├── categories/                 # CAT-MEN/, CAT-WMN/, CAT-KID/
│   ├── invoices/                   # 2026-10/INV-1001.pdf
│   ├── labels/                     # SHP-1001.pdf
│   ├── packing/                    # ORD-1001.pdf
│   ├── returns/                    # RET-1001/photo-1.jpg, qc-report.json
│   ├── tickets/                    # TKT-1001/
│   └── exports/                    # audit-2026-10.csv
└── prototype/                      # Legacy Phase-0 SQLite prototype (preserved for reference)
```

---

## 6. The 9 Agents & Endpoint Whitelists

| # | Agent Node | Service Account | Allowed `/api/*` Endpoints | Write Scope |
|---|---|---|---|---|
| 1 | `catalog_agent` | `svc-catalog` | `GET /api/products/search`, `GET /api/products/{id}`, `GET /api/products/{id}/recommendations`, `GET /api/categories` | Read-only |
| 2 | `cart_agent` | `svc-cart` | `POST /api/cart/add`, `DELETE /api/cart/remove/{id}`, `GET /api/cart`, `POST /api/cart/clear`, `POST /api/coupons/validate`, `POST /api/orders/calculate` | `cart` |
| 3 | `order_agent` | `svc-order` | `POST /api/orders`, `GET /api/orders/{id}`, `POST /api/orders/{id}/cancel`, `POST /api/payments/initiate` | `orders`, `order_items`, `payments`, `coupon_usage` |
| 4 | `fulfillment_agent` | `svc-fulfillment` | `GET /api/shipments/{id}`, `POST /api/shipments/schedule`, `POST /api/inventory/reserve` | `shipments`, `inventory` |
| 5 | `support_agent` | `svc-support` | `GET /api/orders/{id}`, `GET /api/refunds`, `POST /api/returns`, `POST /api/support/escalate` | `support_tickets` |
| 6 | `returns_agent` | `svc-returns` | `POST /api/returns`, `GET /api/returns/{id}`, `POST /api/refunds/{id}/approve`, `POST /api/refunds/{id}/process`, `POST /api/inventory/restock` | `returns`, `refunds`, `inventory` (Tier 1 auto; Tier 2/3 escalates) |
| 7 | `inventory_agent` | `svc-inventory` | `GET /api/inventory/list`, `PUT /api/inventory/{id}`, `POST /api/products/{id}/discontinue` | `inventory`, `products.is_active` |
| 8 | `analytics_agent` | `svc-analytics` | `GET /api/orders/analytics`, `GET /api/customers/analytics`, `GET /api/products/analytics` | Read-only |
| 9 | `config_agent` | `svc-config` | `GET /api/config/policies`, `PUT /api/admin/config/policies`, `GET /api/audit/log` | `business_config`, `policies` (Admin token required) |

---

## 7. Execution Sequence (Basement First)

- **Step 0 (Current — Basement Initialization):**
  1. Finalize selectable `.env.example` and `.env`.
  2. Initialize all folder paths (`backend/`, `agents/`, `frontend/`, `storage/` with `CAT-MEN`, `CAT-WMN`, `CAT-KID` and `PRD-001`..`PRD-005`).
  3. Create `docker-compose.yml` (`postgres:16`, `redis:7`, `qdrant`, optional `elasticsearch` profile) and base `backend/app/config.py` + `backend/app/database.py`.
- **Step 1 (Database & Core Config):** 32-table SQLAlchemy 2.0 models, Alembic migration `0001_initial`, `business_config` seed (Men/Women/Kids premium garments).
- **Step 2 (Core Services & Shared APIs):** Product, Cart, Order, Tax (HSN 61/62 5%/18%), and Audit services + FastAPI routers.
- **Step 3 (LangGraph Agents & Gateway):** HTTP tool wrappers, `ToolPolicyGate`, and LangGraph state machine.
- **Step 4 (Storefront & Admin UI):** Next.js storefront and Admin portal wired to the shared APIs.
