"""Integracion con Stripe (Checkout hospedado).

Corre en paralelo a Mercado Pago: MP sigue atendiendo Mexico y Stripe atiende
Estados Unidos y, opcionalmente, Mexico tambien.

Sobre impuestos
---------------
El IVA lo calculamos nosotros y mandamos a Stripe importes ya con impuesto
incluido. No usamos Stripe Tax todavia porque exige dar de alta registros
fiscales por jurisdiccion en el dashboard, y para vender a Estados Unidos sin
nexo economico no hay sales tax que retener. Cuando haya nexo, Stripe Tax se
activa cambiando los `unit_amount` a netos y agregando `automatic_tax`.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# Eventos que nos interesan del webhook.
EVENT_COMPLETED = "checkout.session.completed"
EVENT_ASYNC_OK = "checkout.session.async_payment_succeeded"
EVENT_ASYNC_FAIL = "checkout.session.async_payment_failed"
EVENT_EXPIRED = "checkout.session.expired"


def is_configured() -> bool:
    return bool((os.environ.get("STRIPE_SECRET_KEY") or "").strip())


def publishable_key() -> str:
    return (os.environ.get("STRIPE_PUBLISHABLE_KEY") or "").strip()


def _client() -> Any:
    """Import diferido: el SDK es pesado y solo hace falta al cobrar."""
    import stripe

    key = (os.environ.get("STRIPE_SECRET_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "Falta STRIPE_SECRET_KEY. Ponla en .env (local) y en las variables "
            "de entorno de Vercel (produccion)."
        )
    stripe.api_key = key
    return stripe


def create_checkout_session(
    *,
    items: List[Dict[str, Any]],
    order_id: str,
    currency: str,
    region: str,
    shipping_cents: int,
    success_url: str,
    cancel_url: str,
    customer_email: str,
) -> Dict[str, Any]:
    """Crea una sesion de Checkout y devuelve {id, url}.

    `items` trae importes CON impuesto incluido, en centavos:
        [{"name", "description", "unit_gross_cents", "qty"}]
    """
    stripe = _client()

    line_items = [
        {
            "price_data": {
                "currency": currency.lower(),
                "unit_amount": int(it["unit_gross_cents"]),
                "product_data": {
                    "name": it["name"],
                    # Stripe rechaza description vacia, mejor omitirla.
                    **({"description": it["description"]} if it.get("description") else {}),
                },
            },
            "quantity": int(it["qty"]),
        }
        for it in items
    ]

    payload: Dict[str, Any] = {
        "mode": "payment",
        "line_items": line_items,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": order_id,
        "metadata": {"order_id": order_id, "region": region},
        "payment_intent_data": {
            "description": "ZEUZ DNC %s" % order_id,
            "metadata": {"order_id": order_id},
        },
        # Que Stripe recoja la direccion tambien: es la que el cliente confirma
        # al pagar y sirve de contraste contra la que capturo en nuestro form.
        "shipping_address_collection": {"allowed_countries": [region]},
    }
    if customer_email:
        payload["customer_email"] = customer_email

    if shipping_cents > 0:
        payload["shipping_options"] = [
            {
                "shipping_rate_data": {
                    "type": "fixed_amount",
                    "fixed_amount": {"amount": int(shipping_cents), "currency": currency.lower()},
                    "display_name": "Envio",
                }
            }
        ]

    log.info("Creando sesion Stripe para orden %s (%s %s)", order_id, currency, region)
    session = stripe.checkout.Session.create(**payload)
    return {"id": session.id, "url": session.url}


def verify_webhook(payload: bytes, signature: str) -> Optional[Dict[str, Any]]:
    """Valida la firma del webhook y devuelve el evento.

    Devuelve None si la firma no cuadra. Sin esta verificacion cualquiera
    podria enviarnos un POST diciendo que una orden fue pagada.

    Importa el SDK directamente en vez de pasar por _client(): validar una
    firma no necesita la llave de la API, solo el secreto del webhook. Exigir
    STRIPE_SECRET_KEY aqui haria que un despliegue sin esa variable
    respondiera 500, y Stripe reintentaria el evento indefinidamente.
    """
    import stripe

    secret = (os.environ.get("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not secret:
        log.error("Falta STRIPE_WEBHOOK_SECRET: no puedo verificar el webhook")
        return None
    try:
        return stripe.Webhook.construct_event(payload, signature, secret)
    except ValueError:
        log.warning("Webhook Stripe con payload invalido")
        return None
    except Exception as exc:  # stripe.error.SignatureVerificationError
        log.warning("Firma de webhook Stripe invalida: %s", exc)
        return None


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    stripe = _client()
    try:
        return stripe.checkout.Session.retrieve(session_id)
    except Exception as exc:
        log.warning("No se pudo leer la sesion Stripe %s: %s", session_id, exc)
        return None


def shipping_from_session(session: Dict[str, Any]) -> Dict[str, str]:
    """Extrae la direccion de envio que el cliente confirmo en Stripe."""
    details = (session.get("collected_information") or {}).get("shipping_details") or {}
    if not details:
        # Sesiones creadas con versiones anteriores de la API.
        details = session.get("shipping_details") or {}
    address = details.get("address") or {}
    return {
        "name": details.get("name") or "",
        "line1": address.get("line1") or "",
        "line2": address.get("line2") or "",
        "city": address.get("city") or "",
        "state": address.get("state") or "",
        "zip": address.get("postal_code") or "",
        "country": address.get("country") or "",
    }
