"""Avisos por correo cuando entra un pedido pagado.

Usa Resend por HTTP directo: es una sola llamada y evita sumar otra
dependencia al bundle que sube a Vercel.

Degrada en silencio a propósito. Si falta RESEND_API_KEY (desarrollo local, o
produccion antes de dar de alta el dominio) el aviso se registra en el log y
la peticion sigue. Un fallo mandando correo NUNCA debe tumbar un webhook de
pago: Stripe reintentaria el evento y acabariamos duplicando ordenes.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

log = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"
DEFAULT_FROM = "ZEUZ DNC <onboarding@resend.dev>"


def is_configured() -> bool:
    return bool((os.environ.get("RESEND_API_KEY") or "").strip())


def _recipients() -> List[str]:
    raw = (os.environ.get("NOTIFY_EMAIL") or "").strip()
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


def _money(amount: float, currency: str) -> str:
    return "%s %s" % (format(amount, ",.2f"), currency)


def _order_html(order: Dict[str, Any], base_url: str) -> str:
    rows = "".join(
        "<tr><td style='padding:6px 12px 6px 0'>%s</td>"
        "<td style='padding:6px 12px 6px 0'>x%s</td>"
        "<td style='padding:6px 0;text-align:right'>%s</td></tr>"
        % (
            it.get("name", it.get("id", "?")),
            it.get("qty", 1),
            _money(it.get("line_gross_cents", 0) / 100.0, order["currency"]),
        )
        for it in order.get("items", [])
    )
    address = "<br>".join(
        part
        for part in [
            order.get("customer_name"),
            order.get("ship_line1"),
            order.get("ship_line2"),
            " ".join(
                p for p in [order.get("ship_city"), order.get("ship_state"), order.get("ship_zip")] if p
            ),
            order.get("ship_country"),
        ]
        if part and part.strip()
    )
    notes = order.get("notes") or ""
    return """
<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#111;max-width:560px">
  <h2 style="margin:0 0 4px">Nuevo pedido pagado</h2>
  <p style="margin:0 0 16px;color:#555">%(id)s &middot; %(region)s &middot; %(gateway)s</p>

  <table style="width:100%%;border-collapse:collapse;font-size:14px">%(rows)s</table>

  <table style="width:100%%;border-collapse:collapse;font-size:14px;margin-top:8px;border-top:1px solid #ddd">
    <tr><td style="padding:6px 0">Subtotal</td><td style="text-align:right">%(subtotal)s</td></tr>
    <tr><td style="padding:6px 0">Impuesto</td><td style="text-align:right">%(tax)s</td></tr>
    <tr><td style="padding:6px 0">Envio</td><td style="text-align:right">%(shipping)s</td></tr>
    <tr><td style="padding:6px 0;font-weight:700">Total</td>
        <td style="text-align:right;font-weight:700">%(total)s</td></tr>
  </table>

  <h3 style="margin:24px 0 6px">Enviar a</h3>
  <p style="margin:0;font-size:14px;line-height:1.6">%(address)s</p>
  <p style="margin:8px 0 0;font-size:14px;color:#555">%(email)s &middot; %(phone)s</p>
  %(notes)s

  <p style="margin:24px 0 0">
    <a href="%(base)s/admin" style="background:#111;color:#fff;padding:10px 16px;
       border-radius:6px;text-decoration:none;font-size:14px">Abrir panel</a>
  </p>
</div>
""" % {
        "id": order["id"],
        "region": order.get("region", ""),
        "gateway": order.get("gateway", ""),
        "rows": rows,
        "subtotal": _money(order.get("subtotal_net", 0), order["currency"]),
        "tax": _money(order.get("tax", 0), order["currency"]),
        "shipping": _money(order.get("shipping", 0), order["currency"]),
        "total": _money(order.get("total", 0), order["currency"]),
        "address": address or "(sin direccion capturada)",
        "email": order.get("customer_email", ""),
        "phone": order.get("customer_phone", "") or "sin telefono",
        "notes": (
            "<p style='margin:12px 0 0;font-size:14px'><strong>Notas:</strong> %s</p>" % notes
            if notes
            else ""
        ),
        "base": base_url.rstrip("/"),
    }


def notify_paid_order(order: Dict[str, Any], base_url: str) -> bool:
    """Manda el aviso. Devuelve True si salio, False si no (sin lanzar)."""
    to = _recipients()
    if not to:
        log.info("NOTIFY_EMAIL vacio; no mando aviso de la orden %s", order.get("id"))
        return False

    api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    if not api_key:
        log.info(
            "RESEND_API_KEY ausente; orden %s pagada por %s (%s). Aviso omitido.",
            order.get("id"),
            order.get("gateway"),
            _money(order.get("total", 0), order.get("currency", "")),
        )
        return False

    try:
        import requests

        response = requests.post(
            RESEND_ENDPOINT,
            headers={
                "Authorization": "Bearer %s" % api_key,
                "Content-Type": "application/json",
            },
            json={
                "from": (os.environ.get("NOTIFY_FROM") or "").strip() or DEFAULT_FROM,
                "to": to,
                "subject": "Nuevo pedido %s — %s"
                % (order["id"], _money(order.get("total", 0), order.get("currency", ""))),
                "html": _order_html(order, base_url),
            },
            timeout=10,
        )
        if response.status_code >= 300:
            log.warning("Resend respondio %s: %s", response.status_code, response.text[:400])
            return False
        return True
    except Exception as exc:
        # Nunca propagamos: el webhook debe responder 200 aunque el correo falle.
        log.warning("No se pudo mandar el aviso de la orden %s: %s", order.get("id"), exc)
        return False
