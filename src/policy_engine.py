"""
policy_engine.py – Rule-based return/exchange eligibility evaluator.

All logic is derived exclusively from policy.txt; no guesswork.
"""
from __future__ import annotations

import datetime
from typing import Any

from src.data_loader import get_reference_today

# ─── Constants derived from policy.txt ────────────────────────────────────────

NORMAL_RETURN_DAYS = 14          # full refund
SALE_RETURN_DAYS   = 7           # store credit only
CLEARANCE_RETURNABLE = False     # final sale – no returns/exchanges

VENDOR_RULES: dict[str, dict] = {
    "Aurelia Couture": {
        "exchanges_only": True,
        "no_refunds": True,
        "return_days": NORMAL_RETURN_DAYS,
        "note": "Exchanges only, no refunds.",
    },
    "Nocturne": {
        "exchanges_only": False,
        "no_refunds": False,
        "return_days": 21,        # extended window
        "note": "Extended return window of 21 days.",
    },
}

TODAY = get_reference_today()


# ─── Main evaluation function ─────────────────────────────────────────────────

def evaluate_return(order: dict, product: dict) -> dict[str, Any]:
    """
    Evaluate whether an order is eligible for return.

    Returns a dict with keys:
        eligible  – bool
        verdict   – short label ("full_refund" / "store_credit" / "exchange_only" / "denied")
        reason    – human-readable explanation
    """
    order_date = datetime.date.fromisoformat(order["order_date"])
    days_since = (TODAY - order_date).days
    vendor     = product["vendor"]
    is_sale    = product["is_sale"]
    is_clearance = product["is_clearance"]

    # ── Rule 1: Clearance items are final sale ──────────────────────────────
    if is_clearance:
        return {
            "eligible": False,
            "verdict":  "denied",
            "reason": (
                f"This item ('{product['title']}') is a clearance item – final sale. "
                "No returns or exchanges are accepted."
            ),
        }

    # ── Rule 2: Determine applicable return window ──────────────────────────
    vendor_rule = VENDOR_RULES.get(vendor)
    if vendor_rule:
        allowed_days  = vendor_rule["return_days"]
        exchanges_only = vendor_rule["exchanges_only"]
        vendor_note    = vendor_rule["note"]
    elif is_sale:
        allowed_days  = SALE_RETURN_DAYS
        exchanges_only = False
        vendor_note    = ""
    else:
        allowed_days  = NORMAL_RETURN_DAYS
        exchanges_only = False
        vendor_note    = ""

    # ── Rule 3: Check if within window ─────────────────────────────────────
    if days_since > allowed_days:
        window_desc = f"{allowed_days}-day" + (" (vendor exception)" if vendor_rule else "")
        return {
            "eligible": False,
            "verdict":  "denied",
            "reason": (
                f"Order placed on {order['order_date']} ({days_since} days ago). "
                f"The {window_desc} return window has expired. "
                + (f"Note: {vendor_note}" if vendor_note else "")
            ),
        }

    # ── Rule 4: Within window – determine refund type ──────────────────────
    if exchanges_only:
        return {
            "eligible": True,
            "verdict":  "exchange_only",
            "reason": (
                f"Order is within the {allowed_days}-day window ({days_since} days ago). "
                f"However, per vendor policy for {vendor}: {vendor_note} "
                "A size exchange is available if stock is in stock."
            ),
        }

    if is_sale:
        return {
            "eligible": True,
            "verdict":  "store_credit",
            "reason": (
                f"Order is within the {allowed_days}-day sale return window ({days_since} days ago). "
                "Sale items are eligible for store credit only (no cash refund). "
                + (f"Note: {vendor_note}" if vendor_note else "")
            ),
        }

    return {
        "eligible": True,
        "verdict":  "full_refund",
        "reason": (
            f"Order is within the {allowed_days}-day return window ({days_since} days ago). "
            "This item is eligible for a full refund. "
            + (f"Note: {vendor_note}" if vendor_note else "")
        ),
    }
