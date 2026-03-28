"""
data_loader.py – Loads and caches product, order, and policy data from disk.
"""
import csv
import os
from typing import Any

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────

def _parse_list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _parse_int_list(value: str) -> list[int]:
    try:
        return [int(v.strip()) for v in value.split(",") if v.strip()]
    except ValueError:
        return []


def _to_bool(value: str) -> bool:
    return value.strip().lower() == "true"


# ──────────────────────────────────────────────
# Loaders
# ──────────────────────────────────────────────

_products_cache: dict[str, dict] | None = None
_orders_cache: dict[str, dict] | None = None
_policy_cache: str | None = None


def load_products() -> dict[str, dict]:
    global _products_cache
    if _products_cache is not None:
        return _products_cache

    path = os.path.join(_BASE, "products.csv")
    products: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            sizes = _parse_list(row["sizes_available"])
            stock  = _parse_int_list(row["stock_per_size"])
            # Build size → stock map
            size_stock = dict(zip(sizes, stock)) if len(sizes) == len(stock) else {}

            products[row["product_id"]] = {
                "product_id":       row["product_id"],
                "title":            row["title"],
                "vendor":           row["vendor"],
                "price":            float(row["price"]),
                "compare_at_price": float(row["compare_at_price"]),
                "tags":             _parse_list(row["tags"]),
                "sizes_available":  sizes,
                "size_stock":       size_stock,
                "is_sale":          _to_bool(row["is_sale"]),
                "is_clearance":     _to_bool(row["is_clearance"]),
                "bestseller_score": int(row["bestseller_score"]),
            }
    _products_cache = products
    return products


def load_orders() -> dict[str, dict]:
    global _orders_cache
    if _orders_cache is not None:
        return _orders_cache

    path = os.path.join(_BASE, "orders.csv")
    orders: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            orders[row["order_id"]] = {
                "order_id":   row["order_id"],
                "order_date": row["order_date"],
                "product_id": row["product_id"],
                "size":       row["size"],
                "price_paid": float(row["price_paid"]),
                "customer_id": row["customer_id"],
            }
    _orders_cache = orders
    return orders


def load_policy() -> str:
    global _policy_cache
    if _policy_cache is not None:
        return _policy_cache

    path = os.path.join(_BASE, "policy.txt")
    with open(path, encoding="utf-8") as fh:
        _policy_cache = fh.read()
    return _policy_cache
