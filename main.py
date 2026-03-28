"""
main.py – CLI entry point for the Retail AI Assistant.

Usage:
    python main.py              → Interactive chat
    python main.py --demo       → Run all built-in demo scenarios
    python main.py --channel whatsapp  → Simulate WhatsApp channel
"""
from __future__ import annotations

import argparse
import sys
import time


# ─── Demo scenarios ───────────────────────────────────────────────────────────

DEMO_SCENARIOS = [
    # ── Shopping Scenario 1 ────────────────────────────────────────────────────
    {
        "id":      "SHOP-1",
        "title":   "Modest Evening Gown with Budget",
        "channel": "chat",
        "turns": [
            "I need a modest evening gown under $300 in size 8. I prefer something on sale.",
        ],
    },
    # ── Shopping Scenario 2 ────────────────────────────────────────────────────
    {
        "id":      "SHOP-2",
        "title":   "Formal Long-Sleeve Dress for Wedding",
        "channel": "whatsapp",
        "turns": [
            "Hi! Looking for a long-sleeve formal gown for a wedding. Budget around $400. Size 10.",
        ],
    },
    # ── Sizing Scenario ───────────────────────────────────────────────────────
    {
        "id":      "SIZE-1",
        "title":   "Product Sizing Availability Check",
        "channel": "chat",
        "turns": [
            "Is P0016 available in size 8?",
        ],
    },
    # ── Support Scenario 1 ────────────────────────────────────────────────────
    {
        "id":      "SUPP-1",
        "title":   "Return Request – Recent Order (Eligible)",
        "channel": "chat",
        "turns": [
            "Order O0018 — I bought this dress last week. It doesn't fit. Can I return it?",
        ],
    },
    # ── Support Scenario 2 ────────────────────────────────────────────────────
    {
        "id":      "SUPP-2",
        "title":   "Return Request – Clearance Item (Should Be Denied)",
        "channel": "chat",
        "turns": [
            "I want to return order O0023. I bought this dress recently but it's not what I expected.",
        ],
    },
    # ── Support Scenario 3 ────────────────────────────────────────────────────
    {
        "id":      "SUPP-STATUS",
        "title":   "Order Status / Tracking Update",
        "channel": "whatsapp",
        "turns": [
            "Can you check the status of order O0047? Has it shipped yet?",
        ],
    },
    # ── Edge Case ─────────────────────────────────────────────────────────────
    {
        "id":      "EDGE-1",
        "title":   "Invalid Order ID (Hallucination Guard)",
        "channel": "cli",
        "turns": [
            "Can I return order O9999? I bought it last week.",
        ],
    },
]


# ─── Runner ───────────────────────────────────────────────────────────────────

def run_demo(verbose: bool = True):
    """Run all demo scenarios and print results."""
    from src.channel_simulator import OpenClawSimulator

    sim = OpenClawSimulator()
    divider = "─" * 60

    print("\n" + "═" * 60)
    print("  RETAIL AI ASSISTANT – DEMO MODE")
    print("  Powered by OpenClaw + Gemini")
    print("═" * 60)

    for scenario in DEMO_SCENARIOS:
        sid      = scenario["id"]
        title    = scenario["title"]
        channel  = scenario["channel"]
        turns    = scenario["turns"]
        cust_id  = f"demo_{sid}"

        print(f"\n{'═'*60}")
        print(f"  [{sid}] {title}")
        print(f"  Channel: {channel.upper()}")
        print(f"{'═'*60}")

        for turn in turns:
            print(f"\n🧑 Customer: {turn}")
            print(divider)
            response = sim.handle_message(
                session_id=sid,
                user_text=turn,
                channel=channel,
                customer_id=cust_id,
                verbose=verbose,
            )
            print(f"🤖 Assistant:\n{response}")
            time.sleep(0.3)  # slight pause for readability

    print(f"\n{'═'*60}")
    print("  DEMO COMPLETE")
    print(f"{'═'*60}\n")


def run_interactive(channel: str = "cli"):
    """Start an interactive session."""
    from src.channel_simulator import OpenClawSimulator
    import os

    sim = OpenClawSimulator()
    session_id = f"live_{int(time.time())}"

    channel_label = channel.upper()
    print(f"\n{'═'*60}")
    print(f"  RETAIL AI ASSISTANT – Interactive Mode [{channel_label}]")
    print(f"  Type 'quit' or 'exit' to end. Type '/demo' to run demos.")
    if not os.environ.get("GEMINI_API_KEY"):
        print(f"  ⚠️  GEMINI_API_KEY not set – running in mock/offline mode.")
    print(f"{'═'*60}\n")

    # Initial greeting
    greeting = sim.handle_message(
        session_id=session_id,
        user_text="hello",
        channel=channel,
        customer_id="live_user",
        verbose=False,
    )
    print(f"🤖 Assistant:\n{greeting}\n")

    while True:
        try:
            user_input = input("🧑 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nGoodbye! Have a wonderful day! 👗")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "bye"):
            print("🤖 Assistant: Thank you for visiting! Have a wonderful day! 👗")
            break
        if user_input.lower() == "/demo":
            run_demo(verbose=False)
            continue

        response = sim.handle_message(
            session_id=session_id,
            user_text=user_input,
            channel=channel,
            customer_id="live_user",
            verbose=False,
        )
        print(f"\n🤖 Assistant:\n{response}\n")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Retail AI Assistant – Personal Shopper & Customer Support"
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Run all built-in demo scenarios and exit."
    )
    parser.add_argument(
        "--channel", choices=["cli", "chat", "whatsapp"], default="cli",
        help="Simulate a specific channel (default: cli)."
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show intent classification details."
    )
    args = parser.parse_args()

    if args.demo:
        run_demo(verbose=args.verbose)
    else:
        run_interactive(channel=args.channel)


if __name__ == "__main__":
    main()
