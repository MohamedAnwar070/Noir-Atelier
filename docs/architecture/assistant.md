# Shopping Assistant Runtime

The storefront chat (`POST /api/agents/chat`, with `AGENT_RUNTIME=llm`) is one bounded
tool-use loop driven by the configured LLM. There is no keyword routing and no
hand-written intent map: the model reads the conversation, decides which tools to call,
and answers through a reply tool that code verifies before anything reaches the shopper.

```
shopper message
   │
   ▼
Chat API (backend/app/api/agents.py)
   identity from auth only · session bound to its shopper · history loaded (text only)
   │
   ▼
AssistantRuntime.handle (agents/assistant/runtime.py)
   1 Understand + 2 Plan   LLM (LLM_MODEL_REASONING) + tools + catalogue vocabulary
   3 Search                tools → PlatformApiClient → real APIs (svc-assistant, on behalf of shopper)
   4 Evaluate              grounding.review: products / ₹ amounts / stock / ids / leaks vs. evidence
                           → 1 rewrite → template from verified facts
   5 Respond               ChatReply (text + product cards built by code)
   6 Log                   TurnTrace → agent_traces (staff-only)
```

## Modules

| Module | Responsibility |
|---|---|
| `agents/llm/gateway.py` | The only code that imports the Anthropic SDK. `converse()` (tool use) and `generate_json()` (stylist). Maps every failure to `LlmError`. Server-side refusal fallback on supported models. Prompt caching on the system block. |
| `agents/assistant/tools.py` | Tool registry: each tool validates its input and calls one existing endpoint. The model sees a whitelisted view (no pickup codes or payment ids). Order tools exist only for signed-in shoppers. |
| `agents/assistant/evidence.py` | Everything tools returned this turn: products (full payloads), money amounts, stock counts, record ids. |
| `agents/assistant/grounding.py` | Deterministic check of a draft against the evidence. Also rejects internal vocabulary (tool names, service accounts, trace ids). |
| `agents/assistant/fallback.py` | Offline reply (the message goes to the search engine as a query) and the verified-facts template. |
| `agents/assistant/prompt.py` | Static instructions + live vocabulary block (both cached) + shopper context inside the user turn. |
| `agents/assistant/contracts.py` | `ChatReply` (shopper, `extra="forbid"`) vs. `TurnTrace` (operators). |
| `backend/app/services/assistant_session_service.py` | Conversation memory in `agent_sessions.state_snapshot` (text and shown ids only). |
| `backend/app/services/agent_trace_service.py` | Persist and query traces. |

## Guarantees

- **No fabricated facts.** Every product card is a catalogue payload. Every ₹ amount must match a money field in a tool result (or the shopper's own words). Stock counts and record ids must match tool results. Sold-out pieces (in the shopper's size, when known) are rejected.
- **No internal leakage.** `ChatReply` has no trace fields. Traces are readable only with `agents:trace_read` (manager, super_admin). The public `/api/agents/registry` returns names and personas only.
- **Least privilege.** `svc-assistant` is read-only and **customer-scoped**: `auth.assert_customer_access` lets it read only the records of the shopper in `X-On-Behalf-Of`, which the server sets from authentication — never from the model or the request body. The client whitelist (`agents/gateway.py`) mirrors the server grant (`reference_data.ASSISTANT_AGENT_PERMISSION`), and a test keeps them identical.
- **Bounded.** `AGENT_MAX_STEPS` tool calls per turn, 6 model calls, `ASSISTANT_TURN_DEADLINE_SEC` wall clock, per-tool timeouts. When a budget runs out, the reply is the verified-facts template.
- **Degrades, never breaks.** If the model is unavailable (`USE_LIVE_LLM=0`, missing key, timeout, refusal, rate limit), the shopper gets a search-based reply and the trace records `llm:<reason>`.
- **Prompt-injection posture.** Tool results and product text are data, by instruction. Even a successful injection can only *read* the current shopper's own records, because no write tool exists. Changes to a cart, order or return are made by the shopper in the UI.

## Streaming (`POST /api/agents/chat/stream`)

Server-Sent Events for the same turn. `status {label}` events report live progress in the shopper's own words ("Searching the collection…", "Checking the details…"; never tool names). Then one `reply` event carries the final `ChatReply`, or an `error` event if the turn fails. Model tokens are deliberately **not** streamed, because a reply is shown only after it passes the grounding check. The storefront's `chatWithAgentsStream` shows the labels in the typing bubble and falls back to `/api/agents/chat` if streaming is unavailable.

## Trace record (`agent_traces`)

`trace_id, session_id, customer_id, runtime (llm|offline), model, status (answered|fallback|error|blocked), intent (reported by the model), plan_note, user_message, reply, product_ids, tool_calls[{name, input, status, http_status, latency_ms, summary, error}], evaluation{passed, attempts, problems, template_used}, errors[], usage{model_calls, tokens, request_ids}, latency_ms, created_at`

Free text is PII-scrubbed before storage. Query with `GET /api/admin/agents/traces?session_id=&status=&customer_id=&before=&limit=` and `GET /api/admin/agents/traces/{trace_id}`.

## Providers (switch in .env, no code changes)

| `LLM_PROVIDER` | Use | Notes |
|---|---|---|
| `anthropic` | **Production** | Anthropic API: native tool calls, prompt caching, refusal fallback. Needs API credits. Credentials come from `ANTHROPIC_API_KEY` or `ant auth login`. |
| `claude_code` | **Local development only** | `agents/llm/claude_code.py` runs `claude -p` on the developer's Claude Code login, with no API credits. Tools are described in the prompt and the model answers in JSON, which is adapted to the same `LlmTurn`, and the grounding check still applies. The CLI runs with its built-in tools, MCP and settings disabled, in a temp folder. Slower (one process per call). Refused when `APP_ENV=production`. |

## Configuration (.env)

| Variable | Default | Meaning |
|---|---|---|
| `AGENT_RUNTIME` | `llm` | `llm` = this runtime; `legacy` = keyword-routed agents (removed in Phase 4) |
| `USE_LIVE_LLM` | `0` | `1` to call the model; otherwise the offline search reply |
| `LLM_PROVIDER` / `ANTHROPIC_API_KEY` | `anthropic` / empty | Provider. Leave the key empty to use the Anthropic CLI sign-in (`ant auth login`); a non-empty key wins over the profile. `ANTHROPIC_PROFILE` picks a named profile. |
| `LLM_MODEL_REASONING` / `LLM_MODEL_FAST` | `claude-sonnet-5-5` / `claude-haiku-5-5` | Loop model / cheap-task model |
| `ASSISTANT_EFFORT` | `low` | Reasoning effort for the loop |
| `AGENT_MAX_STEPS` | `6` | Tool calls per turn |
| `ASSISTANT_TURN_DEADLINE_SEC` | `45` | Wall-clock ceiling per turn |
| `LLM_TIMEOUT_SEC` | `30` | Per model call |

Check the configuration end to end with `python -m agents.llm.check` (one tiny live call). Test suites force `USE_LIVE_LLM=0` (`backend/tests/__init__.py`, `agents/tests/__init__.py`), so they never call a paid model.

## Tests

`agents/tests/test_assistant_runtime.py` drives the real backend with a scripted fake model. It covers grounding, rewrite, template, outage, budgets, deadline, invalid input, guest vs. shopper tools, cross-shopper denial, history, permission parity and the HTTP contract. `backend/tests/integration/test_customer_scope_and_traces.py` covers the server-side scope rule and the trace/registry permissions.
