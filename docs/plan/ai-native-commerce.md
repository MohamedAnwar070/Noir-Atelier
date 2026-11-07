# Noir Atelier — AI-Native Commerce Plan

Status: **Phase 1 + Phase 2 done (2026-11-05) · Phase 3 next** · Phase 2 design: [docs/architecture/assistant.md](../architecture/assistant.md) · Owner: engineering · Last updated: 2026-11-05

This plan makes two things true:

1. **Stock is truthful per size**, everywhere (storefront, admin, orders, returns, AI).
2. **The shopping assistant understands natural language with the configured LLM**,
   uses only real backend data, checks its own answer, and logs everything
   internally without ever showing that to customers.

Phase 1 is the foundation: an assistant cannot be truthful about stock while the
data underneath is wrong.

---

## 0. Where we are today (verified 2026-11-05)

| Area | Status | Evidence |
|---|---|---|
| Total stock goes down on order, back up on cancel/return | ✅ works | end-to-end audit on a seeded copy |
| Over-ordering, cart over-adding, unsold sizes | ✅ blocked | 409 / 422 responses |
| Checkout holds, expiry, duplicate-order protection | ✅ works | audit steps 7–8 |
| **Stock per size** | ❌ broken | buying 2×L twice succeeded with only 2 L in stock |
| `size_breakdown` (per-size JSON) | ❌ never updated by orders/cancels/returns | only the admin "set stock" call writes it |
| Product page "N left in this size" | ❌ shows frozen numbers | reads `size_breakdown` |
| Real data drift | ⚠️ 7 of 100 products | e.g. PRD-003: total 25, sizes sum to 15 |
| Stock changes are traceable | ❌ no ledger | only some changes write `audit_log` |
| `POST /api/inventory/reserve` | ❌ unsafe | clamps at 0 (silently over-reserves), no audit, logic in the route |
| Chat routing | ❌ keyword based | `agents/main.py` `classify_agent_role`, regexes in `agents/nodes/*` |
| Stylist | ✅ LLM + grounding critic + audit | `agents/stylist/*` (kept and folded into Phase 2) |

---

## Phase 1 — Per-size inventory with a stock ledger

### 1.1 Schema (migration `0006_variant_inventory`)

**`variant_inventory`**: one row per size (variant). This becomes the only stock source.

| Column | Type | Rules |
|---|---|---|
| `variant_id` | int, PK, FK → `product_variants.variant_id` ON DELETE CASCADE | one row per variant |
| `quantity_available` | int | `>= 0`, sellable now |
| `quantity_reserved` | int | `>= 0`, held by pending checkouts (already removed from available) |
| `quantity_damaged` | int | `>= 0`, not sellable |
| `low_stock_threshold` | int | `>= 0`, default 2 |
| `created_at`, `updated_at` | timestamptz | |

The meaning matches today's product-level columns, so order logic keeps its semantics:
a hold moves units `available → reserved`, payment capture removes them from
`reserved`, release moves them back.

**`inventory_movements`** is an append-only ledger. Every stock change writes exactly one row per size.

| Column | Type | Rules |
|---|---|---|
| `movement_id` | bigint PK | |
| `variant_id` | FK → `product_variants` ON DELETE CASCADE | indexed with `created_at` |
| `movement_type` | varchar(24) | CHECK in the `MOVEMENT_TYPES` constant (below) |
| `delta_available`, `delta_reserved`, `delta_damaged` | int | at least one non-zero |
| `reference_type`, `reference_id` | varchar | `order` / `return` / `refund` / `admin`; indexed together |
| `actor_id`, `reason` | varchar | who and why |
| `created_at` | timestamptz | |

`MOVEMENT_TYPES = opening_balance, sale, hold, hold_release, hold_capture,
cancel_restock, return_restock, restock, adjustment, damage, late_capture`

**Invariant:** for every variant, the sum of its ledger deltas equals its current
quantities. A check script enforces this (1.6).

**`inventory`** (product level) is no longer read or written by code after this phase.
It is dropped in a later contract migration (`0008`) once production has run cleanly
on the new tables. Pattern: expand → backfill → switch → contract.

### 1.2 Backfill rules (in `0006`)

For each active variant:

1. Start from `inventory.size_breakdown[size]`.
2. **The product total is the truth**, because orders always decremented it. If the per-size
   sum differs from `inventory.quantity_available` (7 products today), rescale the sizes
   proportionally with the largest-remainder method so they sum exactly to the total.
   A size with no breakdown entry gets an even share.
3. `quantity_reserved` per size = the sum of `order_items.quantity` for **pending** orders
   of that product and size (exact, not estimated). `quantity_damaged` goes to the first size.
4. Write one `opening_balance` movement per variant.
5. Log every rescaled product (id, old sizes, new sizes) in the migration output.

The downgrade drops both tables. Tested up → down → up on Postgres and SQLite.

### 1.3 One owner for stock changes: `app/services/inventory_service.py`

All stock writes go through this module. Today they are scattered across about ten code
blocks in the order, returns, product and route files.

| Function | Used by |
|---|---|
| `lock_variants(db, keys)` | rows locked `FOR UPDATE` in `variant_id` order (no deadlocks) |
| `find_shortages(db, lines)` | cart add, order create, late payment recovery |
| `take(db, lines, hold=…, ref=…)` | order create (`sale`) / checkout hold (`hold`) |
| `release_hold(db, order)` | hold expiry, sweep, cancel of a pending hold, webhook `flag_review` |
| `capture_hold(db, order)` | webhook `mark_paid` |
| `restock(db, items, movement_type, ref)` | cancel of a paid order, return refund (both paths) |
| `set_levels(db, product, {size: qty}, reason, actor)` | admin / inventory agent adjustment |
| `stock_summary(product)` | read side: `{total, by_size, low_stock}` for every API payload |

Guarantees:
- **No oversell:** row locks plus a DB `CHECK (quantity_available >= 0)` as the final guard.
  This is safe across multiple server processes. The in-process `_ORDER_CONCURRENCY_LOCK`
  remains only as a SQLite test convenience.
- Every call writes ledger rows in the same transaction (all or nothing).
- Errors stay typed: `insufficient_stock` (409) with per-size `shortages`.

### 1.4 API changes

| Endpoint | Change |
|---|---|
| Product payload | `stock` (total), **`stock_by_size`** `{size: available}`; each `variants[]` entry gains `stock`, `in_stock`. `size_breakdown` is removed. |
| `POST /api/cart/add` | checks the **chosen size** |
| `POST /api/orders`, `/hold`, `/calculate` | per-size shortage check; 409 lists the size |
| `GET /api/inventory/list` | per product: total plus a `sizes[]` row each (available / reserved / damaged / threshold / low) |
| `PUT /api/inventory/{product_id}` | body `{sizes: {"M": 12}, reason}`: absolute level per size, writes `adjustment` |
| `POST /api/inventory/restock` | body `{product_id, size, quantity}` |
| `POST /api/inventory/reserve` | **removed.** Holds go only through `/api/orders/hold`. Callers updated (agent tool, gateway, seed permission). |
| `GET /api/inventory/{product_id}/movements` | **new**, ledger view, `inventory:read` |
| Search `in_stock_only` | an active variant with `available > 0` exists |

### 1.5 Consumers

- **Storefront** `ProductDetailModal`: per-size stock from `stock_by_size`; sold-out sizes are
  disabled ("Sold out in L"); the "N left" message uses live numbers.
- **Admin** inventory vault: per-size levels and per-size restock; low-stock flag per size.
- **API client** (`packages/api/client.js`): `updateInventory(productId, sizes, reason)`,
  `restockInventory(productId, size, qty)`, `listInventoryMovements(productId)`.
- **Legacy static storefront** (`app.js`): reads `stock_by_size`.
- **Agents:** `ops_tools.update_inventory(sizes=…)`; `reserve_inventory` tool removed;
  stylist `ProductFact` gains `stock_by_size`, and the critic rejects a pick whose requested size is sold out.
- **Seeds** (`seed_demo`, `seed_atelier_collection`): create `variant_inventory` plus `opening_balance` rows.

### 1.6 Tests and checks (definition of done)

- [x] Unit: each `inventory_service` function writes the right deltas and ledger rows.
- [x] Integration: the 2026-11-05 audit scenario. Buying 2×L twice → **second is 409** naming size L.
- [x] Hold → expire → stock back; hold → paid → reserved cleared; webhook late recovery per size.
- [x] Cancel (paid) and both return-refund paths restock the **same sizes** that were sold.
- [x] Concurrency: N parallel orders for the last unit of a size → exactly one succeeds.
- [x] Migration up → down → up on Postgres (real data, inside a rolled-back transaction), then applied; backfill report shows the 7 rescaled products.
- [x] `scripts/check_inventory_invariants.py`: ledger sums equal current levels, nothing negative.
- [x] Backend (56) and agent (18) suites green; Next build green; CSS verifier green.

---

## Phase 2 — Agent runtime (understand → plan → search → evaluate → respond → log) ✅

Delivered as designed below, plus security fixes found on the way:
- **Customer scope, enforced server-side.** Agents could read *any* order with no `X-On-Behalf-Of`, list any customer's orders, and read *any* shipment. Now `auth.assert_customer_access` applies, and `agent_permissions.customer_scoped` is set for svc-assistant and svc-stylist.
- **Internals removed from the chat API.** It returned `tool_traces`, `react_steps` and `memory`, and the UI rendered a "trace" panel. The public agent registry exposed system prompts and endpoints. Both are now staff-only.
- **Sessions.** Guessable `Math.random` session ids, and a shared default `SES-1001`, are replaced by UUIDs. A session's history is never loaded for another shopper.
- **Search.** An occasion or palette *inferred* from words ("summer" → resort) no longer zeroes out results. It is relaxed and reported (`relaxed_dimensions`).
- Migration `0007_agent_runtime`. The contract migration that drops `inventory` is renumbered to `0008`.

One bounded tool-use loop replaces keyword routing.

- **LLM gateway** (`agents/llm/`): a provider interface; the Anthropic implementation reads
  the existing `.env` settings (`USE_LIVE_LLM`, model IDs, key). It uses the reasoning model for the
  loop and the fast model for cheap checks, typed errors, timeouts, retries with backoff, and prompt caching
  of the system prompt and tool definitions.
- **Tool registry** (`agents/runtime/tools.py`): typed JSON-schema tools, each mapped to one
  existing endpoint through `PlatformApiClient` and the permission gate:
  `search_products`, `get_product`, `get_size_stock`, `get_policy`, `get_order`,
  `track_shipment`, `get_style_profile`, `save_style_profile`; write tools follow in Phase 3.
- **Loop:** maximum 8 tool calls per turn, a per-call timeout and a per-turn deadline. The model decides
  intent and tools; the code does no keyword matching.
- **Structured reply:** the model returns `{message, product_ids, proposed_action}`.
  Product cards (name, price per size, stock per size) are built **by code from tool results**,
  so the model never types a price.
- **Evaluate:** a deterministic grounding check covers every product, price, size, stock number and
  order status mentioned. On failure the reply is rewritten once, then falls back to a safe template.
- **Customer/internal separation by type:** `ChatReply` (customer) has no trace fields;
  `TurnTrace` (internal) is stored in `agent_traces`. Spans follow the OpenTelemetry GenAI
  names (`invoke_agent`, `chat`, `execute_tool`); the record holds the plan note, tool calls with
  timing, results summary, evaluation verdict, status, errors and final reply. PII is masked.
  Traces are readable only through an admin endpoint (`agents:trace_read`).
- **Fallback (LLM down or over budget):** the message goes straight to the search engine as a query,
  with an honest notice and human handoff. No intent keywords.
- **Rollout:** behind `AGENT_RUNTIME=llm` (default). The keyword agents remain until Phase 4 evals pass, then are deleted.
- **Follow-ups done (2026-11-07):** streamed progress over SSE; migration `0008` dropped the legacy `inventory` table (rollback rebuilds it from live stock); credentials via the Anthropic CLI (`ant auth login`), checked with `python -m agents.llm.check`.
- **Known limitation:** migration 0005 uses `ALTER CONSTRAINT`, so migrations are Postgres-only (SQLite tests use `create_all`).

## Phase 3 — Safe actions

- Write tools (`add_to_cart`, `place_order`, `cancel_order`, `start_return`) only **propose**.
  The server issues a one-time confirmation token bound to the session, action and arguments. Only the
  customer's click executes it, through the normal API. This is OWASP LLM01/LLM06 mitigation.
- Human handoff ticket with the conversation summary (no internal trace).
- Per-session rate limits and a cost budget.

## Phase 4 — Proof before real users

- An eval set of about 50 conversations (search, sizing, budget, out-of-stock, orders, returns,
  policy, multi-turn refinement, ambiguous requests, prompt-injection attempts), with a runner
  and pass thresholds in CI.
- Dashboards: latency (p50/p95), tool error rate, grounding failure rate, fallback rate, cost per turn.
- Load test for checkout concurrency per size; red-team pass.
- Delete the keyword agents and `classify_agent_role`.

---

## Decisions taken

| Decision | Why |
|---|---|
| Product total is the truth in the backfill | orders always decremented it; the breakdown was never updated |
| Keep "available = sellable now" semantics | no behaviour change for holds/payments, so the smallest risk |
| No `committed` (shipped vs unshipped) state yet | there is no fulfilment stock flow today; it can be added later without a redesign |
| Remove `/api/inventory/reserve` | duplicated holds without an order, unsafe clamp, no audit |
| Drop the old `inventory` table only in `0008` | lets a bad deploy roll back without data loss |
| Startup seed no longer runs `create_all` on an Alembic-managed DB | in demo mode it created the new tables behind the migration's back on the dev DB |
