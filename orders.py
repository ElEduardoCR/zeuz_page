"""Registro de ordenes en base de datos.

Sustituye al antiguo `data/orders.jsonl`. Ese esquema no podia funcionar en
produccion: en Vercel el sistema de archivos es de solo lectura salvo /tmp, y
/tmp se descarta entre invocaciones, asi que cada pedido pagado se perdia.

Los importes viajan como Decimal en la API de este modulo y se guardan como
enteros en centavos. Ver db.py para el porque.
"""
from __future__ import annotations

import json
import time
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select

import db

# Estados que consideramos "el dinero ya entro".
PAID_STATUSES = ("paid", "shipped")


def _now() -> int:
    return int(time.time())


def _new_id() -> str:
    # Corto, legible y unico. Se lo mandamos a la pasarela como referencia
    # externa, asi que conviene que se lea bien en un dashboard.
    return "ZEUZ-%d-%s" % (_now(), uuid.uuid4().hex[:6].upper())


def _cents(value: Any) -> int:
    return int(value or 0)


def _to_cents(amount: Decimal) -> int:
    """Decimal -> centavos. Redondea en vez de truncar: int(Decimal) tira los
    decimales, y un importe que llegue como 8698.8399 se convertiria en 869883."""
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Convierte una fila en el dict que consumen plantillas y API."""
    d = dict(row._mapping)
    d["items"] = json.loads(d.pop("items_json") or "[]")
    for key in ("subtotal_net", "tax", "shipping", "total"):
        d[key] = _cents(d.get(key + "_cents")) / 100.0
    d["is_paid"] = d.get("status") in PAID_STATUSES
    return d


# ============================================================
# Escritura
# ============================================================

def create_order(
    *,
    region: str,
    currency: str,
    gateway: str,
    items: List[Dict[str, Any]],
    customer: Dict[str, str],
    subtotal_net: Decimal,
    tax: Decimal,
    shipping: Decimal,
    total: Decimal,
) -> str:
    """Guarda una orden pendiente antes de mandar al cliente a la pasarela."""
    order_id = _new_id()
    now = _now()
    payload = {
        "id": order_id,
        "created_at": now,
        "updated_at": now,
        "status": "pending",
        "gateway": gateway,
        "region": region,
        "currency": currency,
        "subtotal_net_cents": _to_cents(subtotal_net),
        "tax_cents": _to_cents(tax),
        "shipping_cents": _to_cents(shipping),
        "total_cents": _to_cents(total),
        "items_json": json.dumps(items, ensure_ascii=False),
        "customer_name": customer.get("name", "")[:160],
        "customer_email": customer.get("email", "")[:160],
        "customer_phone": customer.get("phone", "")[:60],
        "ship_line1": customer.get("address", "")[:200],
        "ship_line2": customer.get("address2", "")[:200],
        "ship_city": customer.get("city", "")[:120],
        "ship_state": customer.get("state", "")[:120],
        "ship_zip": customer.get("zip", "")[:24],
        "ship_country": customer.get("country", region)[:4],
        "notes": customer.get("notes", ""),
        "gateway_ref": "",
        "gateway_payment_id": "",
        "gateway_status": "",
        "gateway_url": "",
        "tracking_carrier": "",
        "tracking_number": "",
        "shipped_at": None,
        "admin_notes": "",
    }
    with db.get_engine().begin() as conn:
        conn.execute(db.orders.insert().values(**payload))
    return order_id


def update_order(order_id: str, **fields: Any) -> None:
    """Actualiza campos sueltos de una orden. Ignora claves desconocidas."""
    allowed = {c.name for c in db.orders.columns} - {"id", "created_at"}
    values = {k: v for k, v in fields.items() if k in allowed}
    if not values:
        return
    values["updated_at"] = _now()
    with db.get_engine().begin() as conn:
        conn.execute(
            db.orders.update().where(db.orders.c.id == order_id).values(**values)
        )


def mark_shipped(order_id: str, carrier: str, tracking: str) -> None:
    update_order(
        order_id,
        status="shipped",
        tracking_carrier=carrier.strip()[:80],
        tracking_number=tracking.strip()[:120],
        shipped_at=_now(),
    )


# ============================================================
# Lectura
# ============================================================

def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    with db.get_engine().connect() as conn:
        row = conn.execute(
            select(db.orders).where(db.orders.c.id == order_id)
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_order_by_gateway_ref(ref: str) -> Optional[Dict[str, Any]]:
    """Busca por el id que devolvio la pasarela (session de Stripe, preference de MP)."""
    if not ref:
        return None
    with db.get_engine().connect() as conn:
        row = conn.execute(
            select(db.orders).where(db.orders.c.gateway_ref == ref)
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_orders(
    status: Optional[str] = None,
    limit: int = 200,
    search: str = "",
) -> List[Dict[str, Any]]:
    """Ordenes mas recientes primero. Para el panel de administracion."""
    stmt = select(db.orders)
    if status == "paid":
        stmt = stmt.where(db.orders.c.status == "paid")
    elif status == "shipped":
        stmt = stmt.where(db.orders.c.status == "shipped")
    elif status == "pending":
        stmt = stmt.where(db.orders.c.status.in_(("pending", "pending_payment")))
    if search:
        like = "%%%s%%" % search.strip()
        stmt = stmt.where(
            db.orders.c.customer_email.ilike(like)
            | db.orders.c.customer_name.ilike(like)
            | db.orders.c.id.ilike(like)
        )
    stmt = stmt.order_by(desc(db.orders.c.created_at)).limit(limit)
    with db.get_engine().connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [_row_to_dict(r) for r in rows]


def counts_by_status() -> Dict[str, int]:
    """Resumen para la cabecera del panel."""
    out = {"pending": 0, "paid": 0, "shipped": 0, "other": 0}
    with db.get_engine().connect() as conn:
        rows = conn.execute(select(db.orders.c.status)).fetchall()
    for (status,) in rows:
        if status in ("pending", "pending_payment"):
            out["pending"] += 1
        elif status == "paid":
            out["paid"] += 1
        elif status == "shipped":
            out["shipped"] += 1
        else:
            out["other"] += 1
    return out
