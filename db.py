"""Conexion y esquema de base de datos.

Una sola implementacion para local y produccion. El destino lo decide
DATABASE_URL:

    local     sqlite:///data/shop.db          (valor por defecto)
    Supabase  postgresql://...pooler.supabase.com:6543/postgres

Migrar de uno a otro es cambiar esa variable de entorno. No hay una segunda
ruta de codigo que pueda desincronizarse.

El dinero se guarda SIEMPRE en centavos (enteros). SQLite no tiene tipo
decimal y los flotantes acumulan error en sumas de importes; los enteros son
exactos en las dos bases y son ademas lo que piden Stripe y Mercado Pago.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

from sqlalchemy import (
    BigInteger,
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

BASE_DIR = Path(__file__).parent
DEFAULT_SQLITE = "sqlite:///" + str(BASE_DIR / "data" / "shop.db")

metadata = MetaData()

orders = Table(
    "orders",
    metadata,
    Column("id", String(40), primary_key=True),
    Column("created_at", BigInteger, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
    # pending | paid | pending_payment | failed | refunded | shipped | cancelled
    Column("status", String(24), nullable=False, default="pending"),
    Column("gateway", String(24), nullable=False),
    Column("region", String(4), nullable=False),
    Column("currency", String(4), nullable=False),
    # Importes en centavos de `currency`.
    Column("subtotal_net_cents", BigInteger, nullable=False, default=0),
    Column("tax_cents", BigInteger, nullable=False, default=0),
    Column("shipping_cents", BigInteger, nullable=False, default=0),
    Column("total_cents", BigInteger, nullable=False, default=0),
    # Snapshot del carrito al momento de comprar, en JSON. Se guarda el precio
    # cobrado para que un cambio de catalogo no altere ordenes historicas.
    Column("items_json", Text, nullable=False, default="[]"),
    Column("customer_name", String(160), nullable=False, default=""),
    Column("customer_email", String(160), nullable=False, default=""),
    Column("customer_phone", String(60), nullable=False, default=""),
    Column("ship_line1", String(200), nullable=False, default=""),
    Column("ship_line2", String(200), nullable=False, default=""),
    Column("ship_city", String(120), nullable=False, default=""),
    Column("ship_state", String(120), nullable=False, default=""),
    Column("ship_zip", String(24), nullable=False, default=""),
    Column("ship_country", String(4), nullable=False, default=""),
    Column("notes", Text, nullable=False, default=""),
    # Referencias de la pasarela
    Column("gateway_ref", String(255), nullable=False, default=""),
    Column("gateway_payment_id", String(255), nullable=False, default=""),
    Column("gateway_status", String(80), nullable=False, default=""),
    Column("gateway_url", Text, nullable=False, default=""),
    # Envio
    Column("tracking_carrier", String(80), nullable=False, default=""),
    Column("tracking_number", String(120), nullable=False, default=""),
    Column("shipped_at", BigInteger, nullable=True),
    Column("admin_notes", Text, nullable=False, default=""),
)

Index("ix_orders_created_at", orders.c.created_at)
Index("ix_orders_status", orders.c.status)
Index("ix_orders_gateway_ref", orders.c.gateway_ref)

_engine: Engine | None = None


def database_url() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip() or DEFAULT_SQLITE
    # Varios proveedores entregan el esquema viejo `postgres://`, que
    # SQLAlchemy 2 ya no reconoce.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def get_engine() -> Engine:
    """Engine perezoso y compartido. Se crea una vez por proceso."""
    global _engine
    if _engine is not None:
        return _engine

    url = database_url()
    kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}

    if url.startswith("sqlite"):
        # El servidor de Flask atiende en varios hilos; SQLite lo permite
        # mientras no compartamos una conexion entre ellos.
        kwargs["connect_args"] = {"check_same_thread": False}
        try:
            Path(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
        except OSError:
            # En serverless el disco es de solo lectura salvo /tmp. Caer ahi
            # mantiene la app en pie (el catalogo no toca la base) en vez de
            # tumbar el sitio entero con un 500 en cada peticion. Los pedidos
            # NO sobreviven entre invocaciones: esto es una red de seguridad
            # para cuando falta DATABASE_URL, no un modo de operacion.
            url = "sqlite:////tmp/zeuz-shop.db"
    else:
        # En serverless cada invocacion es un proceso efimero: un pool
        # persistente solo deja conexiones colgadas del lado de Postgres.
        kwargs["poolclass"] = NullPool

    _engine = create_engine(url, **kwargs)
    return _engine


_ready = False


def init_db() -> bool:
    """Crea las tablas que falten. Idempotente.

    Devuelve si la base quedo utilizable en vez de lanzar. Un despliegue sin
    DATABASE_URL debe seguir sirviendo el catalogo y solo negar el checkout;
    lanzar aqui, en el import del modulo, tumbaria el sitio completo.
    """
    global _ready
    try:
        metadata.create_all(get_engine())
        _ready = True
    except Exception:  # noqa: BLE001 - cualquier fallo de conexion o de DDL
        log.exception("Base de datos no disponible: el checkout quedara deshabilitado")
        _ready = False
    return _ready


def is_ready() -> bool:
    return _ready


def is_persistent() -> bool:
    """False cuando estamos sobre el SQLite efimero de /tmp."""
    return _ready and not database_url().startswith("sqlite:////tmp")


def is_sqlite() -> bool:
    return database_url().startswith("sqlite")
