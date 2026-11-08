"""ZeuzDNC-Shop — Tienda pública mexicana, MXN y Stripe Checkout.

Rutas publicas
  GET  /                    Landing
  GET  /catalogo            Listado
  GET  /producto/<id>       Detalle
  GET  /carrito             Carrito
  GET  /checkout            Formulario de pago
  GET  /region/<code>       Cambia de region y regresa

API
  GET  /api/products        Catalogo de la region activa
  POST /api/checkout        Crea la orden y devuelve la URL de la pasarela
  GET  /api/order/<id>      Estado de una orden

Retornos y webhooks
  GET  /pago/exito|fallo|pendiente
  POST /webhook/stripe      Notificaciones de Stripe (firma verificada)

Administracion
  /admin/*                  Ver admin.py
"""
from __future__ import annotations

import json
import logging
import os
import hashlib
import hmac
import re
import time
import uuid
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import db
import notifications
import orders
import payments_stripe
import products as catalog

load_dotenv()

BASE_DIR = Path(__file__).parent
app = Flask(
    __name__,
    static_folder=str(BASE_DIR / "static"),
    template_folder=str(BASE_DIR / "templates"),
)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret-change-me")
# La tienda se puede explorar antes de conectar Stripe. Tener credenciales
# antiguas en el entorno no activa los cobros sin este opt-in explícito.
app.config["PAYMENTS_ENABLED"] = os.environ.get("PAYMENTS_ENABLED", "false").strip().lower() == "true"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = app.logger

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:5001").rstrip("/")
APP_STORE_URL = os.environ.get("APP_STORE_URL", "").strip()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=PUBLIC_BASE_URL.startswith("https://"),
                  MAX_CONTENT_LENGTH=64 * 1024)

# Descargas de Zeuz Agent (el puente local que corre en la PC del taller). Los
# binarios se publican en GitHub Releases. El manifiesto fija una versión para
# que el archivo, tamaño y checksum visibles siempre correspondan entre sí.
AGENT_REPO_URL = "https://github.com/ElEduardoCR/zeuzagent"
AGENT_RELEASES_URL = f"{AGENT_REPO_URL}/releases"
DOWNLOADS = json.loads((BASE_DIR / "data" / "downloads.json").read_text(encoding="utf-8"))


def download_catalog() -> List[Dict[str, Any]]:
    """Datos públicos de los archivos con rutas estables de la tienda."""
    return [
        {
            **item,
            "url": url_for("download_file", download_id=item["id"]),
            "checksum_url": url_for("download_checksum", download_id=item["id"]),
        }
        for item in DOWNLOADS
    ]

REGION_COOKIE = "zeuz_region"
REGION_COOKIE_MAX_AGE = 60 * 60 * 24 * 365

# Ids que cambiaron al separar el producto en dos variantes. Mantenemos la URL
# vieja viva porque ya estaba publicada.
LEGACY_PRODUCT_IDS = {"zeuzdnc-device": "zeuzdnc-touch"}

# Stripe y las paqueterias esperan el codigo de dos letras, no el nombre. Un
# campo de texto libre acabaria con "Texas", "TX" y "tejas" en la misma tabla.
US_STATES = [
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"),
    ("CA", "California"), ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"),
    ("DC", "District of Columbia"), ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"),
    ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"),
    ("KS", "Kansas"), ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"),
    ("MD", "Maryland"), ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"),
    ("MS", "Mississippi"), ("MO", "Missouri"), ("MT", "Montana"), ("NE", "Nebraska"),
    ("NV", "Nevada"), ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NM", "New Mexico"),
    ("NY", "New York"), ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"),
    ("OK", "Oklahoma"), ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"),
    ("SC", "South Carolina"), ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"),
    ("UT", "Utah"), ("VT", "Vermont"), ("VA", "Virginia"), ("WA", "Washington"),
    ("WV", "West Virginia"), ("WI", "Wisconsin"), ("WY", "Wyoming"),
]

db.init_db()


# ============================================================
# Region activa
# ============================================================

@app.before_request
def resolve_region() -> None:
    """Fija g.region para toda la peticion.

    Prioridad: parametro ?region= (permite compartir un enlace ya localizado)
    y despues la cookie. Si ninguno es valido, cae a la region por defecto.
    """
    # Una cookie antigua de EE. UU. no cambia la moneda de la tienda mexicana.
    region = catalog.get_region("MX")

    # Ofrecer solo las pasarelas que de verdad tienen credenciales. Sin este
    # filtro, una region que lista Mercado Pago sin token configurado le
    # muestra la opcion al cliente y revienta al pulsar pagar.
    region["gateways"] = ["stripe"] if app.config["PAYMENTS_ENABLED"] and payments_stripe.is_configured() else []
    if region.get("default_gateway") not in region["gateways"]:
        region["default_gateway"] = region["gateways"][0] if region["gateways"] else None

    g.region = region


@app.context_processor
def inject_globals() -> Dict[str, Any]:
    """Variables que toda plantilla necesita."""
    import datetime

    region = getattr(g, "region", None) or catalog.get_region(None)
    store = catalog.storefront_config(region)
    store["payments_enabled"] = app.config["PAYMENTS_ENABLED"]
    store["payment_mode"] = payments_stripe.payment_mode()
    return {
        "store": store,
        "payments_enabled": app.config["PAYMENTS_ENABLED"],
        "regions": {"MX": catalog.get_region("MX")},
        "app_store_url": APP_STORE_URL,
        "support_email": os.environ.get("SUPPORT_EMAIL", "eduardo@voxa.mx"),
        "now_year": datetime.datetime.now().year,
        "us_states": US_STATES,
    }


@app.template_filter("money")
def money_filter(amount: Any, currency: str = "", decimals: int = 2) -> str:
    """Formatea un importe. Sin decimales cuando el precio es redondo."""
    try:
        value = Decimal(str(amount))
    except Exception:
        return str(amount)
    if decimals == 0 or value == value.to_integral_value():
        text = format(value.to_integral_value(), ",.0f")
    else:
        text = format(value, ",.2f")
    return ("$%s %s" % (text, currency)).strip()


@app.template_filter("ts")
def timestamp_filter(value: Any) -> str:
    """Epoch -> fecha legible. Para el panel de administracion."""
    import datetime

    if not value:
        return "—"
    try:
        return datetime.datetime.fromtimestamp(int(value)).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError, OSError):
        return "—"


@app.route("/region/<code>")
def set_region(code: str):
    """Cambia la region y regresa a donde estaba el visitante."""
    if code.upper() != "MX":
        abort(404)
    target = request.args.get("next") or request.referrer or url_for("index")
    # Solo aceptamos rutas internas: un `next` absoluto seria un redirect
    # abierto que alguien podria usar para lanzar phishing desde el dominio.
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        target = url_for("index")
    response = make_response(redirect(target))
    response.set_cookie(
        REGION_COOKIE,
        code.upper(),
        max_age=REGION_COOKIE_MAX_AGE,
        samesite="Lax",
        secure=PUBLIC_BASE_URL.startswith("https"),
        httponly=False,
    )
    return response


# ============================================================
# Paginas
# ============================================================

@app.route("/")
def index():
    products = catalog.all_products(g.region)[:3]
    return render_template("index.html", products=products)


@app.route("/catalogo")
@app.route("/tienda")
def catalog_page():
    return render_template("catalog.html", products=catalog.all_products(g.region))


@app.route("/descargas")
def downloads_page():
    return render_template(
        "descargas.html",
        downloads=download_catalog(),
        agent_windows_url=url_for("download_file", download_id="agent-windows"),
        agent_macos_url=url_for("download_file", download_id="agent-macos"),
        agent_releases_url=AGENT_RELEASES_URL,
        agent_repo_url=AGENT_REPO_URL,
    )


@app.route("/descargas/<download_id>")
def download_file(download_id: str):
    # El visitante solo puede elegir un ID publicado. No se aceptan URLs ni
    # rutas del cliente, y los binarios se sirven desde su publicación oficial.
    item = next((item for item in DOWNLOADS if item["id"] == download_id), None)
    if item is None:
        abort(404)
    response = redirect(item["download_url"], code=302)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/descargas/<download_id>/sha256")
def download_checksum(download_id: str):
    item = next((item for item in DOWNLOADS if item["id"] == download_id), None)
    if item is None:
        abort(404)
    response = make_response(f'{item["sha256"]}  {item["filename"]}\n')
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="{item["filename"]}.sha256"'
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.route("/producto/<product_id>")
def product_page(product_id: str):
    if product_id in LEGACY_PRODUCT_IDS:
        return redirect(
            url_for("product_page", product_id=LEGACY_PRODUCT_IDS[product_id]), code=301
        )
    product = catalog.get_product(product_id, g.region)
    if not product:
        abort(404)
    related = [
        p
        for p in catalog.all_products(g.region)
        if p["id"] != product_id and not p.get("external")
    ][:2]
    return render_template("product.html", product=product, related=related)


@app.route("/carrito")
def cart_page():
    return render_template("cart.html", products=catalog.all_products(g.region))


@app.route("/checkout")
def checkout_page():
    return render_template("checkout.html", products=catalog.all_products(g.region))


def _owner_hash() -> str:
    shopper = session.get("shopper_id")
    return hashlib.sha256(shopper.encode()).hexdigest() if isinstance(shopper, str) else ""


def _owned_order(order_id: str):
    if not order_id or not _owner_hash() or not db.is_ready():
        return None
    attempt = orders.get_order_attempt(order_id)
    if not attempt or not hmac.compare_digest(attempt["owner_hash"], _owner_hash()):
        return None
    order = orders.get_order(order_id)
    if order:
        order["payment_mode"] = attempt["payment_mode"]
    return order


def _public_order(order):
    if not order:
        return None
    return {
        key: order[key] for key in ("id", "status", "is_paid", "currency", "total", "payment_mode")
    } | {"items": [{"name": item["name"], "qty": item["qty"]} for item in order["items"]]}


@app.after_request
def private_payment_responses(response):
    if request.path.startswith(("/pago/", "/api/order/", "/api/checkout", "/api/quote", "/checkout")):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.route("/pago/exito")
def payment_success():
    order_id = request.args.get("order", "")
    order = _owned_order(order_id)
    session_id = request.args.get("session_id", "")
    if order and order["status"] not in orders.PROTECTED_STATUSES and session_id == order["gateway_ref"]:
        _reconcile_stripe_session(session_id, order_id)
        order = _owned_order(order_id)
    return render_template("success.html", order=_public_order(order), order_id=order_id if order else "")


@app.route("/pago/fallo")
def payment_failure():
    order = _owned_order(request.args.get("order", ""))
    return render_template("failure.html", order=_public_order(order), order_id=order["id"] if order else "")


@app.route("/pago/pendiente")
def payment_pending():
    order = _owned_order(request.args.get("order", ""))
    return render_template("pending.html", order=_public_order(order), order_id=order["id"] if order else "")


# ============================================================
# Precios (siempre en servidor)
# ============================================================

def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CheckoutError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status


@app.errorhandler(CheckoutError)
def checkout_error(error):
    return jsonify(ok=False, code=error.code, error=str(error)), error.status


def _json_object():
    data = request.get_json(silent=True) if request.is_json else None
    if not isinstance(data, dict):
        raise CheckoutError("invalid_request", "Envía una solicitud de compra válida.")
    return data


def _mexico_only(data):
    requested = [request.args.get("region"), data.get("region"), data.get("country")]
    if any(value is not None and value != "MX" for value in requested):
        raise CheckoutError("region_unavailable", "Por ahora solo realizamos envíos dentro de México.")
    if data.get("gateway", "stripe") != "stripe":
        raise CheckoutError("gateway_unavailable", "El pago se realiza únicamente con Stripe.")
    if data.get("currency", "MXN") != "MXN" or g.region["currency"] != "MXN":
        raise CheckoutError("currency_unavailable", "Los precios de la tienda están en pesos mexicanos.")


def price_cart(cart: List[Dict[str, Any]], region: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Decimal]]:
    """Valida todo el carrito antes de cotizar; nunca ignora líneas inválidas."""
    if not isinstance(cart, list) or len(cart) > 100:
        raise CheckoutError("invalid_cart", "Revisa los productos de tu carrito.")
    quantities = {}
    for entry in cart:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", entry["id"]):
            raise CheckoutError("invalid_cart", "Hay un producto no válido en el carrito.")
        qty = entry.get("qty")
        if type(qty) is not int or not 1 <= qty <= 99:
            raise CheckoutError("invalid_cart", "La cantidad debe ser un número entero entre 1 y 99.")
        quantities[entry["id"]] = quantities.get(entry["id"], 0) + qty
        if quantities[entry["id"]] > 99:
            raise CheckoutError("invalid_cart", "La cantidad máxima por producto es 99.")
    available = {product["id"]: product for product in catalog.all_products(region)}
    items, subtotal_net, tax_total = [], Decimal("0"), Decimal("0")
    for product_id, qty in sorted(quantities.items()):
        product = available.get(product_id)
        if not product or product.get("external"):
            raise CheckoutError("invalid_cart", "Uno de los productos ya no está disponible. Actualiza tu carrito.")
        stock = product.get("stock", 0)
        if type(stock) is not int or qty > stock:
            raise CheckoutError("stock_unavailable", "No hay suficientes unidades de %s. Ajusta la cantidad." % product["name"], 409)
        price = product["price"]
        unit_net, unit_tax, unit_gross = (Decimal(str(price[key])) for key in ("net", "tax", "gross"))
        if any(not value.is_finite() or value < 0 for value in (unit_net, unit_tax, unit_gross)) or unit_gross <= 0:
            raise CheckoutError("price_unavailable", "Este producto no tiene un precio disponible.", 503)
        unit_net, unit_tax, unit_gross = (_q(value) for value in (unit_net, unit_tax, unit_gross))
        if unit_gross != unit_net + unit_tax:
            raise CheckoutError("price_unavailable", "El precio de este producto necesita revisión.", 503)
        line_net, line_tax, line_gross = (_q(value * qty) for value in (unit_net, unit_tax, unit_gross))
        subtotal_net += line_net
        tax_total += line_tax
        items.append({"id": product_id, "name": product["name"], "description": product.get("short", ""), "qty": qty,
                      "unit_net_cents": catalog.to_minor_units(unit_net, "MXN"),
                      "unit_gross_cents": catalog.to_minor_units(unit_gross, "MXN"),
                      "line_gross_cents": catalog.to_minor_units(line_gross, "MXN")})
    subtotal_gross = _q(subtotal_net + tax_total)
    shipping = _q(catalog.shipping_for(region, subtotal_gross)) if items else Decimal("0")
    if not shipping.is_finite() or shipping < 0:
        raise CheckoutError("price_unavailable", "No pudimos calcular el envío.", 503)
    totals = {"subtotal_net": _q(subtotal_net), "tax": _q(tax_total), "subtotal_gross": subtotal_gross,
              "shipping": shipping, "total": _q(subtotal_gross + shipping)}
    return items, totals


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _quote_token(items, totals):
    return _fingerprint({"items": items, "totals": {key: str(value) for key, value in totals.items()}, "currency": "MXN", "region": "MX"})


def _customer(data):
    customer = data.get("customer")
    if not isinstance(customer, dict):
        raise CheckoutError("invalid_customer", "Escribe tu nombre y correo electrónico.")
    if customer.get("country", "MX") != "MX":
        raise CheckoutError("region_unavailable", "Por ahora solo realizamos envíos dentro de México.")
    result = {}
    for key, limit in (("name", 160), ("email", 160), ("phone", 60)):
        value = customer.get(key, "")
        if not isinstance(value, str) or len(value.strip()) > limit or any(ord(char) < 32 for char in value):
            raise CheckoutError("invalid_customer", "Revisa tus datos de contacto.")
        result[key] = value.strip()
    if not result["name"] or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", result["email"]):
        raise CheckoutError("invalid_customer", "Escribe tu nombre y un correo electrónico válido.")
    result["email"] = result["email"].lower()
    result["country"] = "MX"
    return result


# ============================================================
# API
# ============================================================

@app.route("/api/products")
def api_products():
    return jsonify({
        "region": g.region["code"],
        "currency": g.region["currency"],
        "products": catalog.all_products(g.region),
    })


@app.route("/api/quote", methods=["POST"])
def api_quote():
    data = _json_object()
    _mexico_only(data)
    items, totals = price_cart(data.get("cart"), g.region)
    if not session.get("shopper_id"):
        session["shopper_id"] = uuid.uuid4().hex
    return jsonify(ok=True, currency="MXN", items=items,
                   totals={key: float(value) for key, value in totals.items()},
                   quote_token=_quote_token(items, totals))


@app.route("/api/checkout", methods=["POST"])
def api_checkout():
    if not app.config["PAYMENTS_ENABLED"]:
        raise CheckoutError("payments_not_enabled", "La compra en línea estará disponible próximamente. Tu selección permanece en el carrito.", 503)
    data = _json_object()
    _mexico_only(data)
    if not payments_stripe.is_configured() or not db.is_persistent():
        raise CheckoutError("checkout_unavailable", "La tienda no puede procesar pagos en este momento. Vuelve a intentarlo más tarde.", 503)
    if not app.secret_key or len(app.secret_key) < 32 or app.secret_key == "dev-secret-change-me":
        raise CheckoutError("checkout_unavailable", "La tienda no puede procesar pagos en este momento.", 503)
    mode = payments_stripe.payment_mode()
    if mode == "live" and not PUBLIC_BASE_URL.startswith("https://"):
        raise CheckoutError("checkout_unavailable", "La tienda no puede procesar pagos en este momento.", 503)
    if not _owner_hash():
        raise CheckoutError("cookies_required", "Permite las cookies de esta página y actualiza el resumen antes de continuar.")
    items, totals = price_cart(data.get("cart"), g.region)
    if not items:
        raise CheckoutError("invalid_cart", "Tu carrito está vacío.")
    token = data.get("quote_token")
    expected = _quote_token(items, totals)
    if not isinstance(token, str) or not hmac.compare_digest(token, expected):
        raise CheckoutError("quote_changed", "Los precios o el envío cambiaron. Actualiza el resumen y confirma el nuevo total.", 409)
    customer = _customer(data)
    attempt_id = data.get("attempt_id")
    try:
        parsed = uuid.UUID(attempt_id) if isinstance(attempt_id, str) else None
        if not parsed or parsed.version != 4 or str(parsed) != attempt_id:
            raise ValueError
    except (ValueError, AttributeError):
        raise CheckoutError("invalid_attempt", "Actualiza la página e intenta continuar de nuevo.")
    attempt = {"attempt_id": attempt_id, "payload_hash": _fingerprint({"quote": expected, "customer": customer}),
               "owner_hash": _owner_hash(), "payment_mode": mode}
    existing = orders.get_attempt(attempt_id)
    if existing and int(time.time()) - existing["created_at"] > 23 * 3600:
        raise CheckoutError("attempt_expired", "Este intento de compra venció. Revisa tu selección e inicia uno nuevo.", 409)
    try:
        order_id = orders.create_order(region="MX", currency="MXN", gateway="stripe", items=items, customer=customer,
            subtotal_net=totals["subtotal_net"], tax=totals["tax"], shipping=totals["shipping"], total=totals["total"], attempt=attempt)
    except orders.AttemptConflict:
        raise CheckoutError("attempt_conflict", "La selección o los datos de contacto cambiaron. Inicia un nuevo intento.", 409)
    order = orders.get_order(order_id)
    if order["status"] in orders.PROTECTED_STATUSES:
        return jsonify(ok=True, order_id=order_id, receipt_url=url_for("payment_success", order=order_id))
    if order["status"] not in ("pending", "pending_payment"):
        raise CheckoutError("attempt_expired", "Este intento ya terminó. Revisa tu selección e inicia uno nuevo.", 409)
    if order["gateway_ref"]:
        existing = orders.get_attempt(attempt_id)
        if existing["session_expires_at"] <= int(time.time()):
            raise CheckoutError("attempt_expired", "La sesión de pago venció. Inicia un nuevo intento.", 409)
        if order["gateway_url"]:
            return jsonify(ok=True, order_id=order_id, redirect_url=order["gateway_url"])
    try:
        result = _start_stripe(order_id, items, totals, customer, g.region, attempt_id)
    except RuntimeError:
        # Mantener el pedido pending: Stripe pudo haber recibido la petición.
        # El mismo intento y la misma clave de idempotencia recuperan la sesión.
        raise CheckoutError("payment_unavailable", "No pudimos conectar con el pago. Vuelve a intentarlo con la misma selección.", 503)
    if not orders.attach_session(order_id, result["ref"], result["url"], result["expires_at"]):
        raise CheckoutError("attempt_conflict", "No pudimos recuperar esta sesión de pago. Contacta a soporte.", 409)
    return jsonify(ok=True, order_id=order_id, redirect_url=result["url"])


def _start_stripe(order_id, items, totals, customer, region, attempt_id) -> Dict[str, Any]:
    result = payments_stripe.create_checkout_session(
        items=items, order_id=order_id, currency="MXN", region="MX",
        shipping_cents=catalog.to_minor_units(totals["shipping"], "MXN"),
        success_url="%s/pago/exito?order=%s&session_id={CHECKOUT_SESSION_ID}" % (PUBLIC_BASE_URL, order_id),
        cancel_url="%s/pago/fallo?order=%s" % (PUBLIC_BASE_URL, order_id),
        customer_email=customer["email"], attempt_id=attempt_id,
    )
    return {"ref": result["id"], "url": result["url"], "expires_at": result["expires_at"]}


@app.route("/api/order/<order_id>")
def api_order(order_id: str):
    order = _owned_order(order_id)
    if not order:
        return jsonify(ok=False, error="Orden no encontrada"), 404
    return jsonify(ok=True, order=_public_order(order))


# ============================================================
# Webhooks
# ============================================================

def _validated_stripe_order(stripe_session):
    if not isinstance(stripe_session, dict) and not hasattr(stripe_session, "get"):
        raise ValueError("invalid session")
    session_id = stripe_session.get("id")
    order_id = stripe_session.get("client_reference_id")
    metadata = stripe_session.get("metadata") or {}
    if not isinstance(session_id, str) or not session_id.startswith("cs_") or not isinstance(order_id, str):
        raise ValueError("invalid session identity")
    order = orders.get_order(order_id)
    if not order:
        return None
    attempt = orders.get_order_attempt(order_id)
    if (not attempt or stripe_session.get("object") != "checkout.session" or stripe_session.get("mode") != "payment"
        or order["gateway"] != "stripe" or order["region"] != "MX" or order["currency"] != "MXN"
        or metadata.get("order_id") != order_id or metadata.get("attempt_id") != attempt["attempt_id"]
        or metadata.get("region") != "MX"
        or order["gateway_ref"] not in ("", session_id)
        or stripe_session.get("currency") != "mxn"
        or type(stripe_session.get("amount_total")) is not int
        or stripe_session["amount_total"] != order["total_cents"]
        or type(stripe_session.get("livemode")) is not bool
        or stripe_session["livemode"] != (attempt["payment_mode"] == "live")):
        raise ValueError("session does not match order")
    return order


def _apply_stripe_paid(order_id: str, stripe_session) -> bool:
    order = _validated_stripe_order(stripe_session)
    if not order or order["id"] != order_id or stripe_session.get("payment_status") != "paid":
        return False
    if stripe_session.get("status") != "complete":
        raise ValueError("session not complete")
    shipping = payments_stripe.shipping_from_session(stripe_session)
    if shipping.get("country") != "MX" or not shipping.get("line1"):
        raise ValueError("missing Mexico shipping address")
    fields = {"gateway_payment_id": str(stripe_session.get("payment_intent") or ""), "gateway_status": "paid",
              "ship_line1": shipping["line1"], "ship_line2": shipping["line2"], "ship_city": shipping["city"],
              "ship_state": shipping["state"], "ship_zip": shipping["zip"], "ship_country": "MX"}
    changed = orders.transition_payment(order_id, stripe_session["id"], "paid", **fields)
    # Solo el ganador de la actualización condicional manda el aviso.
    if changed:
        notifications.notify_paid_order(orders.get_order(order_id), PUBLIC_BASE_URL)
    return changed


def _reconcile_stripe_session(session_id: str, order_id: str) -> None:
    stripe_session = payments_stripe.get_session(session_id)
    if not stripe_session:
        return
    try:
        _apply_stripe_paid(order_id, stripe_session)
    except ValueError:
        log.warning("La sesión de retorno no corresponde al pedido %s", order_id)


@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    event = payments_stripe.verify_webhook(request.get_data(), request.headers.get("Stripe-Signature", ""))
    if not event:
        return "invalid signature", 400
    kind = event.get("type")
    if kind not in (payments_stripe.EVENT_COMPLETED, payments_stripe.EVENT_ASYNC_OK,
                    payments_stripe.EVENT_ASYNC_FAIL, payments_stripe.EVENT_EXPIRED):
        return "ignored", 200
    stripe_session = (event.get("data") or {}).get("object") or {}
    try:
        order = _validated_stripe_order(stripe_session)
        if not order:
            return "unknown order", 200
        if kind in (payments_stripe.EVENT_COMPLETED, payments_stripe.EVENT_ASYNC_OK):
            if stripe_session.get("payment_status") == "paid":
                _apply_stripe_paid(order["id"], stripe_session)
            elif kind == payments_stripe.EVENT_COMPLETED:
                orders.transition_payment(order["id"], stripe_session["id"], "pending_payment", gateway_status="unpaid")
        else:
            status = "failed" if kind == payments_stripe.EVENT_ASYNC_FAIL else "cancelled"
            orders.transition_payment(order["id"], stripe_session["id"], status, gateway_status=kind.rsplit(".", 1)[-1])
    except ValueError:
        log.warning("Webhook Stripe rechazado: la sesión no corresponde al pedido")
        return "session mismatch", 400
    return "ok", 200


@app.route("/webhook/mp", methods=["GET", "POST"])
def mp_webhook():
    return "This store uses Stripe only", 410


# ============================================================
# Errores
# ============================================================

@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html"), 404


# Panel de administracion. Se registra al final para que las rutas publicas
# queden definidas primero.
from admin import admin_bp  # noqa: E402

app.register_blueprint(admin_bp)


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    port = int(os.environ.get("PORT", "5001"))  # 5000 lo suele agarrar AirPlay en macOS
    app.run(host="0.0.0.0", port=port, debug=debug)
