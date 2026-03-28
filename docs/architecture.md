# Architecture Document
## Retail AI Assistant (OpenClaw Integration)

---

### 1. Overview

The Retail AI Assistant is a single intelligent agent deployed across **chat** and **WhatsApp** channels via an OpenClaw middleware simulation. It fulfils two roles simultaneously:

| Role | Behaviour |
|---|---|
| **Personal Shopper** | Recommends products based on multi-constraint reasoning (size, price, style, stock, sale status, bestseller score). |
| **Customer Support** | Evaluates return/exchange eligibility using strict rule-based policy logic and fetches real order data. |
| **Fast First Response** | Sends a channel-appropriate greeting and handles sizing, order-status, and FAQ-style questions quickly. |

---

### 2. Architecture

```
┌──────────────────────────────────────────────────────────┐
│              OpenClaw Channel Simulator                  │
│                                                          │
│  Chat ──┐                                                │
│         ├──▶ Intent Classifier ──▶ RetailAgent           │
│  WA  ──┘          │                    │                 │
│                   │                    ▼                 │
│              Escalation ◀──── Gemini 2.0 Flash           │
│              (Human Agent)     (Function-Calling Loop)   │
│                                    │                     │
│                   ┌────────────────┤                     │
│                   ▼                ▼                     │
│           ┌──────────────────────────────┐              │
│           │        Tool Layer            │              │
│           │  search_products             │              │
│           │  get_product                 │              │
│           │  get_order                   │              │
│           │  evaluate_return             │              │
│           └──────────┬───────────────────┘              │
│                      │                                   │
│           ┌──────────▼───────────────────┐              │
│           │        Data Layer            │              │
│           │  products.csv  orders.csv    │              │
│           │  policy.txt                  │              │
│           └──────────────────────────────┘              │
└──────────────────────────────────────────────────────────┘
```

---

### 3. Why This Structure?

**Separation of concerns** is the guiding principle:

- **LLM (Gemini)** handles *reasoning* — understanding the customer's intent, selecting which tools to call, and crafting natural language explanations.
- **Tools** handle *data retrieval* — they are deterministic Python functions that query CSVs or run rule-based logic.
- **policy_engine.py** handles *policy decisions* — a pure Python rule set derived directly from `policy.txt`. Zero LLM involvement.

This means the LLM can never hallucinate a price, invent an order, or fabricate a policy rule — all answers are grounded in real data.

---

### 4. How Hallucination Is Minimised

| Threat | Mitigation |
|---|---|
| Invented product names/prices | `search_products` / `get_product` always run; LLM uses results verbatim. |
| Made-up order data | `get_order` required before any order-related response. |
| Guessed return policy | `evaluate_return` runs the actual rule engine; LLM only explains the result. |
| Non-existent order/product | Tools return `{"found": false, "message": "..."}` — system prompt instructs the LLM to refuse and not guess. |
| Off-topic confident answers | System prompt explicitly lists scoped duties; everything else routes to human. |

---

### 5. Tool Selection Logic

The LLM (Gemini) decides which tools to call via **function-calling** (structured output). The agent loop:

1. User sends message.
2. Gemini reads the system prompt + user message and emits a `function_call` for the most relevant tool(s).
3. Tools execute and return JSON results.
4. Results are fed back to Gemini as `function_response` parts.
5. Gemini may call additional tools (up to **5 rounds**) before producing a final text response.

This multi-round capability allows complex queries like *"I need a modest gown in size 8 under $300 — and also can I return order O0015?"* to resolve multiple tools in one turn.

---

### 6. Channel Integration (OpenClaw)

`OpenClawSimulator` acts as the middleware between incoming messages and the agent:

1. **Intent Classification** — Regex patterns classify each message as `greeting`, `shopping`, `support`, `escalation`, or `general`.
2. **Escalation Gate** — Immediately routes to human agent if distress keywords detected (no LLM call).
3. **Channel Formatting** — Responses are post-processed for WhatsApp (converts `**bold**` → `*bold*`, line-wraps at 60 chars) vs. chat (full markdown).
4. **Session State** — Maintains per-session conversation history enabling multi-turn context.

In a production deployment, the `handle_message()` method would be called by a webhook handler (WhatsApp Business API / Twilio / custom chat socket).

---

### 7. Return Policy Decision Tree

```
evaluate_return(order_id)
        │
        ├─ Order not found? → DENIED (not_found)
        │
        ├─ Product is_clearance? → DENIED (final sale)
        │
        ├─ Vendor = "Aurelia Couture"?
        │    └─ Within 14 days? → EXCHANGE ONLY
        │    └─ Expired?        → DENIED
        │
        ├─ Vendor = "Nocturne"?
        │    └─ Within 21 days + is_sale? → STORE CREDIT
        │    └─ Within 21 days            → FULL REFUND
        │    └─ Expired?                  → DENIED
        │
        ├─ is_sale = True?
        │    └─ Within 7 days? → STORE CREDIT
        │    └─ Expired?       → DENIED
        │
        └─ Normal item
             └─ Within 14 days? → FULL REFUND
             └─ Expired?        → DENIED
```

---

### 8. Sizing & Availability Logic

`search_products(size="8")` filters the `size_stock` map so only products with **stock > 0** for the requested size are returned. Results are sorted by `bestseller_score` (descending) to surface the most popular in-stock options.

For direct sizing checks like “Is P0016 available in size 8?”, the agent calls `get_product(product_id)` and uses `size_stock` to confirm in-stock units (or to say it’s out of stock). The agent does **not** guess “runs small/large” because the dataset does not contain fit metadata; those requests are routed to a human stylist.

---

### 9. Order Status Simulation (No External Integration)

Because this is a simulation (no carrier API), order status is computed deterministically from the `order_date`:

- Days 0–1 → `processing`
- Days 2–3 → `shipped`
- Days 4–5 → `out_for_delivery`
- Day 6+ → `delivered` (expected)

`get_order(order_id)` returns the computed status and an `estimated_delivery_date` (order date + 5 days). The LLM only explains/communicates these tool results; it does not invent tracking numbers.

---

### 10. Assumptions

1. **Reference date** for simulations is deterministic: `REFERENCE_DATE` env var (if set) otherwise `(max order_date in orders.csv) + 7 days`.
2. **Sale return credit** means store credit only — no cash refunds (matching `policy.txt`).
3. WhatsApp Business API connection is simulated; in production, a webhook handler replaces `OpenClawSimulator.handle_message()`.
4. Human agent routing is simulated via an escalation flag — real integration would use a ticketing system (e.g. Zendesk).
