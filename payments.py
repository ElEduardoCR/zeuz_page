"""Integracion con Mercado Pago (Checkout Pro / preference API)."""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)


def is_configured() -> bool:
    """Si hay credenciales utilizables de Mercado Pago."""
    token = os.environ.get("MP_ACCESS_TOKEN", "").strip()
    return bool(token) and not token.startswith("APP_USR-TU_")


def _is_sandbox() -> bool:
    return os.environ.get("MP_ENV", "sandbox").lower() != "production"


def _sdk() -> Any:
    # El SDK es pesado y solo hace falta al crear o consultar un pago. La
    # importacion diferida mantiene rapidas las paginas publicas de la tienda.
    import mercadopago

    token = os.environ.get("MP_ACCESS_TOKEN", "").strip()
    if not token or token.startswith("APP_USR-TU_"):
        raise RuntimeError(
            "Falta MP_ACCESS_TOKEN. Crea el archivo .env con tu access token "
            "de Mercado Pago (https://www.mercadopago.com.mx/developers/panel/credentials)."
        )
    return mercadopago.SDK(token)


def create_preference(
    items: list[dict[str, Any]],
    payer: dict[str, str],
    order_id: str,
    back_urls: dict[str, str],
) -> dict[str, Any]:
    """Crea una preferencia de Checkout Pro. Devuelve el dict de MP con init_point."""
    sdk = _sdk()
    payload: dict[str, Any] = {
        "items": items,
        "payer": payer,
        "external_reference": order_id,
        "back_urls": back_urls,
        "auto_return": "approved",
        "statement_descriptor": "ZEUZ DNC",
        "metadata": {"order_id": order_id},
    }
    # En sandbox forzamos que el checkout se quede en el entorno de pruebas de MP.
    if _is_sandbox():
        # No hay flag nativo en la API; basta con un access token de TEST.
        pass
    log.info("Creando preferencia MP para orden %s con %d items", order_id, len(items))
    result = sdk.preference().create(payload)
    if result.get("status") not in (200, 201):
        log.error("MP preference error: %s", result)
        raise RuntimeError(f"Mercado Pago rechazo la preferencia: {result}")
    return result["response"]


def get_payment(payment_id: str) -> dict[str, Any] | None:
    """Consulta un pago por id (lo usa el webhook para verificar el estado)."""
    sdk = _sdk()
    result = sdk.payment().get(payment_id)
    if result.get("status") != 200:
        log.warning("MP payment().get fallo para %s: %s", payment_id, result)
        return None
    return result["response"]
