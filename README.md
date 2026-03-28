# Retail AI Assistant

> **Personal Shopper + Customer Support Agent** powered by Google Gemini with function-calling, integrated via OpenClaw chat/WhatsApp simulation.

---

## Features

| Capability | Details |
|---|---|
| 🛍️ Personal Shopper | Multi-constraint product search (size, price, tags, sale, stock) |
| 📦 Order Support | Real-time order lookup and status |
| 🔄 Return Evaluator | Rule-based policy engine — no guessing |
| 📱 Channel Support | CLI, Chat, WhatsApp (via OpenClaw) |
| 🤖 Function Calling | Gemini 2.0 Flash with structured tool dispatch |
| 🛡️ Hallucination Guard | All answers grounded in CSV data + policy.txt |

---

## Project Structure

```
calwbot/
├── main.py                 # CLI entry point
├── requirements.txt
├── products.csv            # 100 products
├── orders.csv              # 100 orders
├── policy.txt              # Return policy rules
├── src/
│   ├── __init__.py
│   ├── data_loader.py      # CSV + policy loader (cached)
│   ├── policy_engine.py    # Rule-based return evaluator
│   ├── tools.py            # 4 structured tools + Gemini declarations
│   ├── agent.py            # Gemini agentic loop
│   └── channel_simulator.py# OpenClaw middleware (chat/WhatsApp)
└── docs/
    └── architecture.md     # Design document
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set your Gemini API key

```bash
export GEMINI_API_KEY="your-key-here"
```

> Get a free key at [aistudio.google.com](https://aistudio.google.com).  
> **Without a key** – the system runs in **offline/mock mode** which still demonstrates all tool calls correctly.

Optional (deterministic demos):

```bash
export REFERENCE_DATE="2026-03-03"
```

### 3. Run

```bash
# Interactive chat (CLI)
python main.py

# Simulate WhatsApp channel
python main.py --channel whatsapp

# Run all demo scenarios automatically
python main.py --demo

# Demo with intent-classification details
python main.py --demo --verbose
```

---

## Demo Scenarios

Run `python main.py --demo` to execute all scenarios:

| ID | Type | Query Summary |
|---|---|---|
| SHOP-1 | Shopping | Modest evening gown under $300, size 8, on sale |
| SHOP-2 | Shopping | Long-sleeve formal gown ~$400, size 10, for wedding |
| SIZE-1 | Sizing | Check if product P0016 is available in size 8 |
| SUPP-1 | Support | Return request for recent order O0018 |
| SUPP-2 | Support | Return of clearance order O0023 (should be denied) |
| SUPP-STATUS | Support | Order status check for O0047 |
| EDGE-1 | Edge Case | Invalid order ID O9999 (hallucination guard) |

---

## Tool Reference

| Tool | Purpose |
|---|---|
| `search_products(filters)` | Filter catalogue by tags, price, size (stock-checked), sale |
| `get_product(product_id)` | Full details for a single product |
| `get_order(order_id)` | Order details + simulated shipping status |
| `evaluate_return(order_id)` | Rule-based return eligibility decision |

---

## Design Highlights

- **No hardcoded responses** — every answer is derived from data + LLM reasoning.
- **Offline mock mode** — works without an API key for testing/demo.
- **Policy engine** — deterministic Python, not LLM inference.
- **OpenClaw** middleware handles escalation → human agent automatically when customer distress is detected.

See [`docs/architecture.md`](docs/architecture.md) for full design rationale.

---

## Channel Integration (Production Notes)

In a real deployment:
- **Chat**: Connect `OpenClawSimulator.handle_message()` to a WebSocket handler.
- **WhatsApp**: Wire to Meta's WhatsApp Business API webhook or Twilio.
- **Human escalation**: Replace the escalation flag with a Zendesk/Freshdesk ticket creation call.
