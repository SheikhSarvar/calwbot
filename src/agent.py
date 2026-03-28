"""
agent.py – Core agentic loop using Google Gemini with function-calling.

Design principles:
  1. All data comes from tools – the LLM never invents product IDs, prices, or policies.
  2. Tool results are injected back into the conversation as function responses.
  3. We run up to MAX_TOOL_ROUNDS per user turn to resolve multi-step queries.
  4. If no API key is configured we fall back to a mock mode for offline testing.
"""
from __future__ import annotations

import json
import os
from typing import Any

from src.tools import TOOL_DECLARATIONS, TOOL_FUNCTIONS
from src.data_loader import load_policy

# ─── Configuration ─────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL_NAME     = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
MAX_TOOL_ROUNDS = 5   # safety cap on tool-call iterations per turn

SYSTEM_PROMPT = """You are an intelligent retail assistant for a women's fashion boutique.
You have two roles:

1. PERSONAL SHOPPER – Help customers find clothing that matches their style, size,
   occasion, and budget. Always search for products using tools before recommending
   anything. Explain *why* each recommendation fits the customer's needs.
   Consider: size availability, stock levels, sale status, and bestseller score.

2. CUSTOMER SUPPORT – Handle order status, return eligibility, and policy questions.
   Always look up the order and evaluate return eligibility using tools.
   Apply policy rules strictly and explain your decision clearly.

CRITICAL RULES:
- NEVER invent product names, prices, IDs, or availability – only use tool results.
- NEVER guess return eligibility – always call evaluate_return.
- If an order ID does not exist, say so clearly.
- If a product does not exist, say so clearly.
- Route questions you cannot answer (e.g. payment issues) to a human agent.
- Keep responses professional, warm, and concise.
- For complex or upset customers, always offer to connect to a human agent.

POLICY SUMMARY (use evaluate_return tool for definitive answers):
""" + load_policy()

# ─── Gemini client (lazy init) ─────────────────────────────────────────────────

_gemini_client = None

def _get_client():
    global _gemini_client
    if _gemini_client is None:
        try:
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=GEMINI_API_KEY)
            _gemini_client = genai
        except ImportError:
            _gemini_client = None
    return _gemini_client


def _build_tools():
    """Convert TOOL_DECLARATIONS into Gemini Tool objects."""
    genai = _get_client()
    if genai is None:
        return None
    from google.generativeai.types import FunctionDeclaration, Tool  # type: ignore
    declarations = [
        FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters=t["parameters"],
        )
        for t in TOOL_DECLARATIONS
    ]
    return Tool(function_declarations=declarations)


# ─── Main agent class ──────────────────────────────────────────────────────────

class RetailAgent:
    """
    Stateless agent: each call() invocation is a self-contained conversation turn.
    The caller manages conversation history for multi-turn sessions.
    """

    def __init__(self, channel: str = "cli"):
        self.channel = channel  # "cli" | "chat" | "whatsapp"
        self._model  = None

    def _get_model(self):
        if self._model is None:
            genai = _get_client()
            if genai is None:
                return None
            tools = _build_tools()
            self._model = genai.GenerativeModel(
                model_name=MODEL_NAME,
                system_instruction=SYSTEM_PROMPT,
                tools=[tools] if tools else [],
            )
        return self._model

    # ── Public interface ────────────────────────────────────────────────────────

    def respond(self, user_message: str, history: list[dict] | None = None) -> str:
        """
        Process a user message and return the assistant's text response.

        Args:
            user_message: The customer's input.
            history:      Previous turns as [{"role": "user"|"model", "parts": [...]}]

        Returns:
            Assistant response string.
        """
        if not GEMINI_API_KEY:
            return self._mock_respond(user_message)

        model = self._get_model()
        if model is None:
            return self._mock_respond(user_message)

        chat = model.start_chat(history=history or [])

        # ── Agentic tool-calling loop ───────────────────────────────────────
        response = chat.send_message(user_message)

        for _ in range(MAX_TOOL_ROUNDS):
            # Check if the model wants to call tools
            tool_calls = self._extract_tool_calls(response)
            if not tool_calls:
                break   # Model returned text – we're done

            # Execute each requested tool
            tool_responses = []
            for call in tool_calls:
                result = self._dispatch_tool(call["name"], call["args"])
                tool_responses.append({
                    "name":     call["name"],
                    "response": result,
                })

            # Feed results back and get the next model turn
            response = chat.send_message(
                self._format_tool_responses(tool_responses)
            )

        return self._extract_text(response)

    # ── Internal helpers ────────────────────────────────────────────────────────

    def _extract_tool_calls(self, response) -> list[dict]:
        """Extract function_call parts from a Gemini response."""
        calls = []
        try:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "function_call") and part.function_call.name:
                    calls.append({
                        "name": part.function_call.name,
                        "args": dict(part.function_call.args),
                    })
        except (AttributeError, IndexError):
            pass
        return calls

    def _dispatch_tool(self, name: str, args: dict) -> dict:
        """Run the named tool with provided args; return result dict."""
        fn = TOOL_FUNCTIONS.get(name)
        if fn is None:
            return {"error": f"Unknown tool '{name}'"}
        try:
            return fn(args)
        except Exception as exc:
            return {"error": str(exc)}

    def _format_tool_responses(self, tool_responses: list[dict]):
        """Build Gemini FunctionResponse parts from tool results."""
        from google.generativeai.types import FunctionResponse  # type: ignore
        parts = []
        for tr in tool_responses:
            parts.append(FunctionResponse(
                name=tr["name"],
                response=tr["response"],
            ))
        return parts

    def _extract_text(self, response) -> str:
        """Pull plain text out of a Gemini response."""
        try:
            return response.text
        except Exception:
            try:
                return response.candidates[0].content.parts[0].text
            except Exception:
                return "[Agent returned an unexpected response format]"

    # ── Mock mode (no API key) ──────────────────────────────────────────────────

    def _mock_respond(self, user_message: str) -> str:
        """
        Offline mock: runs tools locally and prints results. Used for testing
        without a Gemini API key.
        """
        msg = user_message.lower()

        # Detect intent
        if any(kw in msg for kw in ["order", "return", "refund", "exchange", "status"]):
            # Try to extract an order ID
            import re
            m = re.search(r"\b(o\d{4})\b", msg, re.IGNORECASE)
            if m:
                order_id = m.group(1).upper()
                result = TOOL_FUNCTIONS["evaluate_return"]({"order_id": order_id})
                return self._mock_format_return(result)
            return (
                "I'd be happy to help with your order! Could you please provide "
                "your order ID? It looks like 'O' followed by four digits (e.g. O0043)."
            )

        # Detect shopping intent
        if any(kw in msg for kw in ["dress", "gown", "outfit", "wear", "looking for", "need", "find"]):
            # Build basic filters from message
            filters: dict[str, Any] = {}
            import re

            price_match = re.search(r"under\s*\$?(\d+)", msg)
            if price_match:
                filters["max_price"] = float(price_match.group(1))

            size_match = re.search(r"\bsize\s+(\d+)\b", msg)
            if size_match:
                filters["size"] = size_match.group(1)

            if "sale" in msg or "discount" in msg:
                filters["on_sale"] = True

            tags = []
            tag_keywords = [
                "modest", "evening", "gown", "long-sleeve", "casual",
                "formal", "lace", "velvet", "silk", "chiffon", "satin",
                "midi", "maxi", "fitted", "flowy", "wedding",
            ]
            for kw in tag_keywords:
                if kw in msg:
                    tags.append(kw)
            # Infer occasion tags from context
            if "wedding" in msg or "formal" in msg:
                tags = list(set(tags) | {"formal", "modest"})
            if "evening" in msg or "gown" in msg:
                tags = list(set(tags) | {"evening"})
            if tags:
                filters["tags"] = tags

            result = TOOL_FUNCTIONS["search_products"](filters)
            return self._mock_format_products(result, filters)

        # FAQ / general
        return (
            "Hello! I'm your retail assistant. I can help you:\n"
            "• 🛍️  Find the perfect outfit for any occasion\n"
            "• 📦  Check your order status\n"
            "• 🔄  Understand return & exchange eligibility\n\n"
            "What can I help you with today?"
        )

    def _mock_format_products(self, result: dict, filters: dict) -> str:
        if not result["found"]:
            return (
                "I'm sorry, I couldn't find any products matching your criteria. "
                "Could you try loosening some filters? "
                "I can also connect you to a personal stylist – just ask!"
            )
        lines = ["Here are my top recommendations for you:\n"]
        for i, p in enumerate(result["products"][:5], 1):
            sale_badge = " 🏷️ ON SALE" if p["is_sale"] else ""
            lines.append(
                f"{i}. **{p['title']}** by {p['vendor']}{sale_badge}\n"
                f"   Price: ${p['price']:.0f}  |  ⭐ Score: {p['bestseller_score']}\n"
                f"   Sizes: {', '.join(p['sizes_available'])}\n"
                f"   Style tags: {', '.join(p['tags'][:4])}\n"
            )
        size = filters.get("size")
        on_sale = filters.get("on_sale")
        note = ""
        if size:
            note += f" ✓ All have stock in size {size}."
        if on_sale:
            note += " ✓ All are on sale."
        if note:
            lines.append(note.strip())
        return "\n".join(lines)

    def _mock_format_return(self, result: dict) -> str:
        if not result.get("found"):
            return (
                f"❌ I couldn't find that order. {result.get('message', '')} "
                "Please double-check your order ID or contact us for help."
            )
        oid = result.get("order_id", "")
        product = result.get("product", {})
        decision = "✅ Yes" if result["eligible"] else "❌ No"
        verdict_labels = {
            "full_refund":   "Full Refund",
            "store_credit":  "Store Credit Only",
            "exchange_only": "Exchange Only",
            "denied":        "Return Denied",
            "not_found":     "Order Not Found",
        }
        verdict = verdict_labels.get(result.get("verdict", ""), result.get("verdict", ""))
        return (
            f"**Return Eligibility for {oid}**\n"
            f"Product: {product.get('title', 'N/A')}\n"
            f"Decision: {decision} – {verdict}\n\n"
            f"Reason: {result.get('reason', 'No reason provided.')}\n\n"
            "If you'd like to proceed with a return or exchange, please "
            "reply with 'start return' and we'll guide you through the process."
        )
