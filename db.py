"""Conexion y esquema de base de datos.

Una sola implementacion para local y produccion. El destino lo decide
DATABASE_URL:

    local     sqlite:///data/shop.db          (valor por defecto)
    Supabase  postgresql://...pooler.supabase.com:6543/postgres

PostgreSQL requiere aplicar primero la migración revisada con RLS/permisos.
El arranque solo comprueba el esquema remoto; no crea tablas de producción.

El dinero se guarda SIEMPRE en centavos (enteros). SQLite no tiene tipo
decimal y los flotantes acumulan error en sumas de importes; los enteros son
exactos en las dos bases y son lo que pide Stripe.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
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

# Intentos privados de compra. Se crean con el pedido en una transacción;
# la clave única evita duplicar pedidos al reintentar una petición.
checkout_attempts = Table(
    "checkout_attempts", metadata,
    Column("attempt_id", String(36), primary_key=True),
    Column("order_id", String(40), ForeignKey("orders.id"), nullable=False, unique=True),
    Column("payload_hash", String(64), nullable=False),
    Column("owner_hash", String(64), nullable=False),
    Column("payment_mode", String(16), nullable=False),
    Column("created_at", BigInteger, nullable=False),
    Column("session_expires_at", BigInteger, nullable=False, default=0, server_default="0"),
)

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
    """Crea el esquema local o verifica el esquema previamente migrado en PostgreSQL.

    Devuelve si la base quedo utilizable en vez de lanzar. Un despliegue sin
    DATABASE_URL debe seguir sirviendo el catalogo y solo negar el checkout;
    lanzar aqui, en el import del modulo, tumbaria el sitio completo.
    """
    global _ready
    try:
        engine = get_engine()
        if engine.dialect.name == "sqlite":
            metadata.create_all(engine)
        else:
            # Producción se aprovisiona con una migración revisada que incluye
            # RLS y permisos. Importar Flask nunca debe crear tablas públicas.
            with engine.connect() as connection:
                connection.execute(select(orders).limit(0))
                connection.execute(select(checkout_attempts).limit(0))
        _ready = True
    except Exception:  # noqa: BLE001 - cualquier fallo de conexion o de DDL
        log.exception("Base de datos no disponible: el checkout quedara deshabilitado")
        _ready = False
    return _ready


def is_ready() -> bool:
    return _ready


def is_persistent() -> bool:
    """Inspecciona el destino real; ningún SQLite es durable en serverless."""
    if not _ready:
        return False
    engine = get_engine()
    if engine.dialect.name != "sqlite":
        return True
    if any(os.environ.get(name) for name in ("VERCEL", "AWS_LAMBDA_FUNCTION_NAME", "K_SERVICE")):
        return False
    database = engine.url.database
    if not database or database == ":memory:":
        return False
    path = Path(database).resolve()
    temporary_roots = (Path("/tmp").resolve(), Path("/private/tmp").resolve(), Path(tempfile.gettempdir()).resolve())
    return not any(path == root or root in path.parents for root in temporary_roots)


def is_sqlite() -> bool:
    return get_engine().dialect.name == "sqlite"
