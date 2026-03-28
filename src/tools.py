"""
tools.py – Structured tool implementations called by the AI agent.

Each function is the authoritative data source; the LLM never invents data.
Tool schemas (for Gemini function-calling) are exported as TOOL_DECLARATIONS.
"""
from __future__ import annotations

import fnmatch
from typing import Any

from src.data_loader import load_products, load_orders
from src.policy_engine import evaluate_return as _eval_return


# ─── Tool implementations ──────────────────────────────────────────────────────

def search_products(
    tags: list[str] | None = None,
    max_price: float | None = None,
    min_price: float | None = None,
    size: str | None = None,
    on_sale: bool | None = None,
    is_clearance: bool | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    """
    Filter the product catalogue and return matching items, sorted by
    bestseller_score descending.

    Args:
        tags:         Substring-matched against product tags (e.g. ["modest","evening"]).
        max_price:    Upper price bound (inclusive).
        min_price:    Lower price bound (inclusive).
        size:         Size string (e.g. "8"). Only returns products with stock > 0
                      for that size.
        on_sale:      If True, only return items with is_sale == True.
        is_clearance: If True, only return clearance items.
        limit:        Maximum results to return (default 8).
    """
    products = load_products()
    results: list[dict] = []

    for p in products.values():
        # ── Tag filter ──────────────────────────────────────────────────────
        if tags:
            product_tag_str = " ".join(p["tags"]).lower()
            if not all(t.lower() in product_tag_str for t in tags):
                continue

        # ── Price filters ───────────────────────────────────────────────────
        if max_price is not None and p["price"] > max_price:
            continue
        if min_price is not None and p["price"] < min_price:
            continue

        # ── Sale / clearance ────────────────────────────────────────────────
        if on_sale is not None and p["is_sale"] != on_sale:
            continue
        if is_clearance is not None and p["is_clearance"] != is_clearance:
            continue

        # ── Size & stock filter ─────────────────────────────────────────────
        if size is not None:
            size_str = str(size)
            stock = p["size_stock"].get(size_str, 0)
            if stock <= 0:
                continue

        results.append(p)

    # Sort by bestseller_score descending
    results.sort(key=lambda x: x["bestseller_score"], reverse=True)
    results = results[:limit]

    if not results:
        return {
            "found": False,
            "count": 0,
            "products": [],
            "message": "No products match the given filters.",
        }

    return {
        "found": True,
        "count": len(results),
        "products": [_format_product_summary(p) for p in results],
    }


def get_product(product_id: str) -> dict[str, Any]:
    """
    Retrieve full details for a single product by its ID.

    Args:
        product_id: e.g. "P0086"
    """
    products = load_products()
    p = products.get(product_id.upper())
    if p is None:
        return {
            "found": False,
            "message": f"Product '{product_id}' does not exist in the catalogue.",
        }
    return {"found": True, "product": _format_product_full(p)}


def get_order(order_id: str) -> dict[str, Any]:
    """
    Retrieve order details by order ID.

    Args:
        order_id: e.g. "O0043"
    """
    orders = load_orders()
    o = orders.get(order_id.upper())
    if o is None:
        return {
            "found": False,
            "message": f"Order '{order_id}' was not found. Please double-check the order ID.",
        }
    return {"found": True, "order": o}


def evaluate_return_tool(order_id: str) -> dict[str, Any]:
    """
    Determine whether an order is eligible for return and explain why.

    Args:
        order_id: e.g. "O0043"
    """
    orders   = load_orders()
    products = load_products()

    o = orders.get(order_id.upper())
    if o is None:
        return {
            "found": False,
            "eligible": False,
            "verdict": "not_found",
            "message": f"Order '{order_id}' was not found. Cannot evaluate return eligibility.",
        }

    p = products.get(o["product_id"])
    if p is None:
        return {
            "found": False,
            "eligible": False,
            "verdict": "error",
            "message": (
                f"Order '{order_id}' found but its product '{o['product_id']}' "
                "is no longer in the catalogue."
            ),
        }

    result = _eval_return(o, p)
    return {
        "found":    True,
        "order_id": order_id,
        "product":  _format_product_summary(p),
        "order":    o,
        **result,
    }


# ─── Formatting helpers ────────────────────────────────────────────────────────

def _format_product_summary(p: dict) -> dict:
    return {
        "product_id":     p["product_id"],
        "title":          p["title"],
        "vendor":         p["vendor"],
        "price":          p["price"],
        "is_sale":        p["is_sale"],
        "is_clearance":   p["is_clearance"],
        "bestseller_score": p["bestseller_score"],
        "sizes_available": p["sizes_available"],
        "tags":           p["tags"],
    }


def _format_product_full(p: dict) -> dict:
    return {
        **_format_product_summary(p),
        "compare_at_price": p["compare_at_price"],
        "size_stock":       p["size_stock"],
    }


# ─── Gemini function-calling declarations ─────────────────────────────────────

TOOL_DECLARATIONS = [
    {
        "name": "search_products",
        "description": (
            "Search the product catalogue using filters such as style tags, price range, "
            "size availability, and sale status. Always call this before recommending products. "
            "Only products with stock > 0 for the requested size are returned."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of tag keywords (e.g. ['modest','evening','long-sleeve'])",
                },
                "max_price": {"type": "number", "description": "Maximum price (inclusive)"},
                "min_price": {"type": "number", "description": "Minimum price (inclusive)"},
                "size": {"type": "string", "description": "Clothing size e.g. '8', '12'"},
                "on_sale": {"type": "boolean", "description": "If true, only return sale items"},
                "is_clearance": {"type": "boolean", "description": "If true, only return clearance items"},
                "limit": {"type": "integer", "description": "Max number of results (default 8)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_product",
        "description": "Retrieve full details for a specific product by product_id (e.g. 'P0086').",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Product ID e.g. 'P0086'"},
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "get_order",
        "description": (
            "Retrieve an order's details by order_id (e.g. 'O0043'). "
            "Returns order date, product purchased, size, and customer ID."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Order ID e.g. 'O0001'"},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "evaluate_return",
        "description": (
            "Evaluate whether an order is eligible for return, exchange, or refund. "
            "Applies all policy rules (normal/sale/clearance windows, vendor exceptions). "
            "Always call this instead of guessing return eligibility."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Order ID e.g. 'O0043'"},
            },
            "required": ["order_id"],
        },
    },
]

# ─── Dispatcher (maps tool name → function) ───────────────────────────────────

TOOL_FUNCTIONS: dict[str, Any] = {
    "search_products": lambda args: search_products(**args),
    "get_product":     lambda args: get_product(**args),
    "get_order":       lambda args: get_order(**args),
    "evaluate_return": lambda args: evaluate_return_tool(**args),
}
