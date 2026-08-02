"""ZeuzDNC-Shop — Tienda publica del sistema ZeuzDNC.

Dos regiones (Mexico y Estados Unidos) y dos pasarelas (Mercado Pago y
Stripe). La region decide moneda, impuesto, costo de envio, forma del
formulario de direccion y que pasarelas se ofrecen.

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
  POST /webhook/mp          Notificaciones de Mercado Pago

Administracion
  /admin/*                  Ver admin.py
"""
from __future__ import annotations

import logging
import os
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
    url_for,
)

import db
import notifications
import orders
import payments as payments_mp
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = app.logger

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:5001").rstrip("/")
APP_STORE_URL = os.environ.get("APP_STORE_URL", "").strip()
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
    requested = request.args.get("region") or request.cookies.get(REGION_COOKIE)
    g.region = catalog.get_region(requested)


@app.context_processor
def inject_globals() -> Dict[str, Any]:
    """Variables que toda plantilla necesita."""
    import datetime

    region = getattr(g, "region", None) or catalog.get_region(None)
    return {
        "store": catalog.storefront_config(region),
        "regions": catalog.all_regions(),
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
    if not catalog.is_valid_region(code):
        abort(404)
    target = request.args.get("next") or request.referrer or url_for("index")
    # Solo aceptamos rutas internas: un `next` absoluto seria un redirect
    # abierto que alguien podria usar para lanzar phishing desde el dominio.
    if not target.startswith("/"):
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
    products = [p for p in catalog.all_products(g.region) if not p.get("external")][:3]
    return render_template("index.html", products=products)


@app.route("/catalogo")
def catalog_page():
    return render_template("catalog.html", products=catalog.all_products(g.region))


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


@app.route("/pago/exito")
def payment_success():
    order_id = (
        request.args.get("order")
        or request.args.get("external_reference")
        or ""
    )
    order = orders.get_order(order_id) if order_id else None
    # Stripe redirige antes de que llegue el webhook. Si la sesion ya esta
    # pagada, adelantamos el estado para no mostrar "pendiente" a alguien que
    # acaba de pagar bien.
    session_id = request.args.get("session_id")
    if order and order["status"] == "pending" and session_id:
        _reconcile_stripe_session(session_id)
        order = orders.get_order(order_id)
    return render_template("success.html", order=order, order_id=order_id)


@app.route("/pago/fallo")
def payment_failure():
    return render_template("failure.html", order_id=request.args.get("order", ""))


@app.route("/pago/pendiente")
def payment_pending():
    return render_template("pending.html", order_id=request.args.get("order", ""))


# ============================================================
# Precios (siempre en servidor)
# ============================================================

def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def price_cart(cart: List[Dict[str, Any]], region: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Decimal]]:
    """Resuelve el carrito del cliente contra el catalogo y calcula totales.

    Nunca se usa el precio que manda el navegador: se toma el del catalogo. El
    carrito del cliente solo aporta ids y cantidades.
    """
    available = {p["id"]: p for p in catalog.all_products(region)}
    items: List[Dict[str, Any]] = []
    subtotal_net = Decimal("0")
    tax_total = Decimal("0")

    for entry in cart:
        product = available.get(entry.get("id"))
        if not product or product.get("external"):
            continue
        try:
            qty = int(entry.get("qty") or 0)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        qty = min(qty, 99)  # limite defensivo contra manipulacion del cliente

        price = product["price"]
        unit_net = Decimal(str(price["net"]))
        unit_tax = Decimal(str(price["tax"]))
        unit_gross = Decimal(str(price["gross"]))

        line_net = _q(unit_net * qty)
        line_tax = _q(unit_tax * qty)
        line_gross = _q(unit_gross * qty)
        subtotal_net += line_net
        tax_total += line_tax

        items.append({
            "id": product["id"],
            "name": product["name"],
            "description": product.get("short", ""),
            "qty": qty,
            "unit_net_cents": catalog.to_minor_units(unit_net, price["currency"]),
            "unit_gross_cents": catalog.to_minor_units(unit_gross, price["currency"]),
            "line_gross_cents": catalog.to_minor_units(line_gross, price["currency"]),
        })

    subtotal_gross = _q(subtotal_net + tax_total)
    # La tarifa de envio se maneja como precio final al cliente (impuesto ya
    # considerado dentro), para que el total del checkout sea el que se cobra.
    shipping = _q(catalog.shipping_for(region, subtotal_gross)) if items else Decimal("0")
    totals = {
        "subtotal_net": _q(subtotal_net),
        "tax": _q(tax_total),
        "subtotal_gross": subtotal_gross,
        "shipping": shipping,
        "total": _q(subtotal_gross + shipping),
    }
    return items, totals


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
    """Totales del carrito segun el servidor. Lo usa el resumen del checkout."""
    data = request.get_json(force=True, silent=True) or {}
    items, totals = price_cart(data.get("cart") or [], g.region)
    return jsonify({
        "ok": True,
        "currency": g.region["currency"],
        "items": items,
        "totals": {k: float(v) for k, v in totals.items()},
    })


@app.route("/api/checkout", methods=["POST"])
def api_checkout():
    """Crea la orden y devuelve la URL de pago de la pasarela elegida."""
    data = request.get_json(force=True, silent=True) or {}
    cart = data.get("cart") or []
    customer = data.get("customer") or {}
    region = g.region
    gateway = (data.get("gateway") or region.get("default_gateway") or "stripe").lower()

    if gateway not in region.get("gateways", []):
        return jsonify({"ok": False, "error": "Metodo de pago no disponible en tu region"}), 400

    missing = [field for field in ("name", "email") if not (customer.get(field) or "").strip()]
    if missing:
        return jsonify({"ok": False, "error": "Faltan datos: %s" % ", ".join(missing)}), 400

    items, totals = price_cart(cart, region)
    if not items:
        return jsonify({"ok": False, "error": "Tu carrito esta vacio"}), 400

    customer = dict(customer)
    customer["country"] = region["code"]

    order_id = orders.create_order(
        region=region["code"],
        currency=region["currency"],
        gateway=gateway,
        items=items,
        customer=customer,
        subtotal_net=totals["subtotal_net"],
        tax=totals["tax"],
        shipping=totals["shipping"],
        total=totals["total"],
    )

    try:
        if gateway == "stripe":
            result = _start_stripe(order_id, items, totals, customer, region)
        else:
            result = _start_mercadopago(order_id, items, totals, customer, region)
    except RuntimeError as exc:
        log.exception("No se pudo iniciar el pago de la orden %s", order_id)
        orders.update_order(order_id, status="failed", gateway_status=str(exc)[:80])
        return jsonify({"ok": False, "error": str(exc)}), 500

    orders.update_order(
        order_id,
        gateway_ref=result["ref"],
        gateway_url=result["url"],
    )
    return jsonify({"ok": True, "order_id": order_id, "redirect_url": result["url"]})


def _start_stripe(order_id, items, totals, customer, region) -> Dict[str, str]:
    session = payments_stripe.create_checkout_session(
        items=items,
        order_id=order_id,
        currency=region["currency"],
        region=region["code"],
        shipping_cents=catalog.to_minor_units(totals["shipping"], region["currency"]),
        success_url="%s/pago/exito?order=%s&session_id={CHECKOUT_SESSION_ID}"
        % (PUBLIC_BASE_URL, order_id),
        cancel_url="%s/pago/fallo?order=%s" % (PUBLIC_BASE_URL, order_id),
        customer_email=customer.get("email", ""),
    )
    return {"ref": session["id"], "url": session["url"]}


def _start_mercadopago(order_id, items, totals, customer, region) -> Dict[str, str]:
    mp_items = [
        {
            "id": it["id"],
            "title": it["name"],
            "description": it["description"],
            "quantity": it["qty"],
            "unit_price": it["unit_gross_cents"] / 100.0,
            "currency_id": region["currency"],
        }
        for it in items
    ]
    if totals["shipping"] > 0:
        mp_items.append({
            "id": "shipping",
            "title": "Envio",
            "description": "Envio a domicilio",
            "quantity": 1,
            "unit_price": float(totals["shipping"]),
            "currency_id": region["currency"],
        })

    name = (customer.get("name") or "").strip()
    first, _, last = name.partition(" ")
    payer = {"name": first, "surname": last, "email": customer["email"]}
    if customer.get("phone"):
        payer["phone"] = {"number": str(customer["phone"])}

    preference = payments_mp.create_preference(
        mp_items,
        payer,
        order_id,
        {
            "success": "%s/pago/exito?order=%s" % (PUBLIC_BASE_URL, order_id),
            "failure": "%s/pago/fallo?order=%s" % (PUBLIC_BASE_URL, order_id),
            "pending": "%s/pago/pendiente?order=%s" % (PUBLIC_BASE_URL, order_id),
        },
    )
    url = preference.get("init_point") or preference.get("sandbox_init_point")
    if not url:
        raise RuntimeError("Mercado Pago no devolvio URL de pago")
    return {"ref": preference.get("id", ""), "url": url}


@app.route("/api/order/<order_id>")
def api_order(order_id: str):
    order = orders.get_order(order_id)
    if not order:
        return jsonify({"ok": False, "error": "Orden no encontrada"}), 404
    # Vista publica: nunca exponemos datos del cliente en un endpoint abierto.
    return jsonify({
        "ok": True,
        "order": {
            "id": order["id"],
            "status": order["status"],
            "currency": order["currency"],
            "total": order["total"],
            "is_paid": order["is_paid"],
        },
    })


# ============================================================
# Webhooks
# ============================================================

def _mark_paid(order_id: str, **fields: Any) -> None:
    """Marca pagada una orden y avisa por correo. Idempotente.

    Las pasarelas reintentan y a veces mandan el mismo evento dos veces; sin
    esta guarda mandariamos varios correos por el mismo pedido.
    """
    order = orders.get_order(order_id)
    if not order:
        log.warning("Webhook para orden desconocida %s", order_id)
        return
    already_paid = order["status"] in orders.PAID_STATUSES
    orders.update_order(order_id, status="paid", **fields)
    if already_paid:
        return
    notifications.notify_paid_order(orders.get_order(order_id), PUBLIC_BASE_URL)


def _reconcile_stripe_session(session_id: str) -> None:
    """Consulta una sesion de Stripe y aplica su estado a la orden."""
    session = payments_stripe.get_session(session_id)
    if not session:
        return
    order_id = session.get("client_reference_id") or ""
    if not order_id:
        return
    if session.get("payment_status") == "paid":
        _apply_stripe_paid(order_id, session)


def _apply_stripe_paid(order_id: str, session: Dict[str, Any]) -> None:
    shipping = payments_stripe.shipping_from_session(session)
    fields: Dict[str, Any] = {
        "gateway_payment_id": str(session.get("payment_intent") or ""),
        "gateway_status": str(session.get("payment_status") or ""),
    }
    # La direccion confirmada en Stripe manda sobre la del formulario: es la
    # que el cliente valido al pagar.
    if shipping.get("line1"):
        fields.update({
            "ship_line1": shipping["line1"],
            "ship_line2": shipping["line2"],
            "ship_city": shipping["city"],
            "ship_state": shipping["state"],
            "ship_zip": shipping["zip"],
            "ship_country": shipping["country"],
        })
    _mark_paid(order_id, **fields)


@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    event = payments_stripe.verify_webhook(
        request.get_data(), request.headers.get("Stripe-Signature", "")
    )
    if not event:
        return "invalid signature", 400

    kind = event.get("type")
    session = (event.get("data") or {}).get("object") or {}
    order_id = session.get("client_reference_id") or (session.get("metadata") or {}).get("order_id")
    log.info("Webhook Stripe %s para orden %s", kind, order_id)

    if not order_id:
        return "ok", 200

    if kind in (payments_stripe.EVENT_COMPLETED, payments_stripe.EVENT_ASYNC_OK):
        if session.get("payment_status") == "paid":
            _apply_stripe_paid(order_id, session)
        else:
            # Metodos diferidos (OXXO): la sesion se completa pero el dinero
            # todavia no llega. Se confirma en async_payment_succeeded.
            orders.update_order(order_id, status="pending_payment",
                                gateway_status=str(session.get("payment_status") or ""))
    elif kind == payments_stripe.EVENT_ASYNC_FAIL:
        orders.update_order(order_id, status="failed", gateway_status="async_payment_failed")
    elif kind == payments_stripe.EVENT_EXPIRED:
        orders.update_order(order_id, status="cancelled", gateway_status="expired")

    return "ok", 200


@app.route("/webhook/mp", methods=["GET", "POST"])
def mp_webhook():
    # GET: ping simple que MP hace para validar que la URL existe.
    if request.method == "GET":
        return "ok", 200

    data = request.get_json(silent=True) or {}
    log.info("Webhook MP: %s", data)

    topic = (data.get("type") or data.get("topic") or "").lower()
    resource_id = (
        data.get("data", {}).get("id")
        if isinstance(data.get("data"), dict)
        else data.get("data_id")
    )
    if topic != "payment" or not resource_id:
        return "ok", 200

    payment = payments_mp.get_payment(str(resource_id))
    if not payment:
        log.warning("Webhook: no se pudo obtener pago %s", resource_id)
        return "ok", 200

    order_id = (payment.get("external_reference") or "").strip()
    if not order_id:
        return "ok", 200

    status = payment.get("status")
    fields = {
        "gateway_payment_id": str(payment.get("id") or ""),
        "gateway_status": str(payment.get("status_detail") or ""),
    }
    if status == "approved":
        _mark_paid(order_id, **fields)
    elif status in ("rejected", "cancelled"):
        orders.update_order(order_id, status="failed", **fields)
    else:
        orders.update_order(order_id, status="pending_payment", **fields)
    log.info("Orden %s actualizada a %s", order_id, status)
    return "ok", 200


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
