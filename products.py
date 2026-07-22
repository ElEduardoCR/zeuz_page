"""Catalogo de productos. Lee de data/products.json y expone helpers."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent / "data"
PRODUCTS_FILE = DATA_DIR / "products.json"
_LOCK = threading.RLock()


def _load() -> dict[str, Any]:
    with _LOCK:
        with PRODUCTS_FILE.open(encoding="utf-8") as fh:
            return json.load(fh)


def get_config() -> dict[str, Any]:
    """Config general: currency, country, shipping_free."""
    data = _load()
    return {
        "currency": data.get("currency", "MXN"),
        "country": data.get("country", "MEX"),
        "shipping_free": data.get("shipping_free", True),
    }


def all_products() -> list[dict[str, Any]]:
    return _load().get("products", [])


def get_product(product_id: str) -> dict[str, Any] | None:
    for p in all_products():
        if p["id"] == product_id:
            return p
    return None


def by_ids(ids: list[str]) -> list[dict[str, Any]]:
    """Resuelve una lista de ids a productos (preserva el orden, ignora ids invalidos)."""
    by_id = {p["id"]: p for p in all_products()}
    return [by_id[i] for i in ids if i in by_id]
