"""Registro de ordenes en disco. Append-only, una linea JSON por orden."""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

ORDERS_FILE = Path(__file__).parent / "data" / "orders.jsonl"
_LOCK = threading.Lock()


def _new_id() -> str:
    # Corto, legible, unico. Suficiente para MVP.
    return f"ZEUZ-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"


def create_order(cart: list[dict[str, Any]], customer: dict[str, str], total: float) -> str:
    """Guarda una orden pendiente. Devuelve el id interno."""
    order_id = _new_id()
    record = {
        "id": order_id,
        "created_at": int(time.time()),
        "status": "pending",
        "items": cart,
        "customer": customer,
        "total": total,
        "mp": {},
    }
    with _LOCK:
        with ORDERS_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return order_id


def update_order(order_id: str, **fields: Any) -> None:
    """Actualiza una orden existente. Carga -> modifica -> reescribe todo."""
    with _LOCK:
        records = _read_all_locked()
        for r in records:
            if r["id"] == order_id:
                r.update(fields)
                break
        else:
            return
        with ORDERS_FILE.open("w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def get_order(order_id: str) -> dict[str, Any] | None:
    with _LOCK:
        for r in _read_all_locked():
            if r["id"] == order_id:
                return r
    return None


def _read_all_locked() -> list[dict[str, Any]]:
    if not ORDERS_FILE.exists():
        return []
    out: list[dict[str, Any]] = []
    with ORDERS_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # Saltamos lineas corruptas sin tumbar la app.
                continue
    return out
