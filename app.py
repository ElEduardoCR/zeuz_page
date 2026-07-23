"""ZeuzDNC-Shop — Tienda publica del sistema ZeuzDNC.

Rutas:
  GET  /                    Landing
  GET  /catalogo            Listado de productos
  GET  /producto/<id>       Detalle de un producto
  GET  /carrito             Vista del carrito (render server-side con cart del cliente via JS)
  GET  /checkout            Formulario de pago
  POST /api/create-pref     Recibe carrito + datos del cliente, crea la preferencia y devuelve init_point
  GET  /pago/exito          Pago aprobado
  GET  /pago/fallo          Pago rechazado
  GET  /pago/pendiente      Pago pendiente (efectivo, transferencia, etc.)
  POST /webhook/mp          Notificaciones de Mercado Pago
  GET  /api/order/<id>      Estado de una orden (para la pantalla de exito)
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

import orders
import payments
import products as catalog

load_dotenv()

BASE_DIR = Path(__file__).parent
app = Flask(__name__, static_folder=str(BASE_DIR / "static"), template_folder=str(BASE_DIR / "templates"))
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret-change-me")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = app.logger

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:5000").rstrip("/")
APP_STORE_URL = os.environ.get("APP_STORE_URL", "").strip()


@app.context_processor
def storefront_links():
    """Enlaces comerciales compartidos por todas las plantillas."""
    return {"app_store_url": APP_STORE_URL}


# ============================================================
# Paginas
# ============================================================

@app.route("/")
def index():
    featured = catalog.all_products()[:3]  # 3 primeros para la landing
    return render_template("index.html", products=featured, config=catalog.get_config())


@app.route("/catalogo")
def catalog_page():
    return render_template("catalog.html", products=catalog.all_products(), config=catalog.get_config())


@app.route("/producto/<product_id>")
def product_page(product_id: str):
    product = catalog.get_product(product_id)
    if not product:
        abort(404)
    return render_template("product.html", product=product, config=catalog.get_config())


@app.route("/carrito")
def cart_page():
    return render_template("cart.html", products=catalog.all_products(), config=catalog.get_config())


@app.route("/checkout")
def checkout_page():
    return render_template("checkout.html", products=catalog.all_products(), config=catalog.get_config())


@app.route("/pago/exito")
def payment_success():
    payment_id = request.args.get("payment_id") or request.args.get("collection_id")
    order_id = request.args.get("external_reference")
    return render_template("success.html", payment_id=payment_id, order_id=order_id, config=catalog.get_config())


@app.route("/pago/fallo")
def payment_failure():
    return render_template("failure.html", config=catalog.get_config())


@app.route("/pago/pendiente")
def payment_pending():
    return render_template("pending.html", config=catalog.get_config())


# ============================================================
# API
# ============================================================

@app.route("/api/products")
def api_products():
    return jsonify(catalog.all_products())


@app.route("/api/create-pref", methods=["POST"])
def api_create_preference():
    """Crea la preferencia de MP a partir del carrito y datos del cliente."""
    data = request.get_json(force=True, silent=True) or {}
    cart = data.get("cart") or []
    customer = data.get("customer") or {}

    if not cart:
        return jsonify({"ok": False, "error": "El carrito esta vacio"}), 400
    required = ("name", "email")
    missing = [k for k in required if not customer.get(k)]
    if missing:
        return jsonify({"ok": False, "error": f"Faltan datos: {', '.join(missing)}"}), 400

    # Resolver productos y total en backend (nunca confiar en el precio del cliente)
    items_in: list[dict] = cart  # [{"id": "zeuzdnc-device", "qty": 1}, ...]
    products = {p["id"]: p for p in catalog.all_products()}
    items: list[dict] = []
    total = 0.0
    for it in items_in:
        pid = it.get("id")
        qty = int(it.get("qty") or 0)
        p = products.get(pid)
        if not p or p.get("external") or qty <= 0:
            continue
        # Limite defensivo contra manipulacion del cliente
        if qty > 99:
            qty = 99
        unit = float(p["price"])
        items.append({
            "id": p["id"],
            "title": p["name"],
            "description": p.get("short", ""),
            "quantity": qty,
            "unit_price": unit,
            "currency_id": catalog.get_config()["currency"],
        })
        total += unit * qty

    if not items:
        return jsonify({"ok": False, "error": "Carrito invalido"}), 400

    cfg = catalog.get_config()
    if cfg.get("shipping_free"):
        # No cobramos envio al cliente. Lo absorbemos en el precio.
        # Si quisieras mostrarlo separado, agrega un item "Envio" con unit_price 0.
        pass

    # Datos del pagador
    payer = {
        "name": customer.get("name", "").split(" ", 1)[0],
        "surname": (customer.get("name", "").split(" ", 1)[1] if " " in customer.get("name", "") else ""),
        "email": customer["email"],
    }
    if customer.get("phone"):
        payer["phone"] = {"number": str(customer["phone"])}

    # Crear orden interna ANTES de ir a MP
    internal_id = orders.create_order(
        cart=[{"id": it["id"], "qty": it["quantity"], "unit": it["unit_price"]} for it in items],
        customer={
            "name": customer["name"],
            "email": customer["email"],
            "phone": customer.get("phone", ""),
            "address": customer.get("address", ""),
            "city": customer.get("city", ""),
            "state": customer.get("state", ""),
            "zip": customer.get("zip", ""),
            "notes": customer.get("notes", ""),
        },
        total=total,
    )

    back_urls = {
        "success": f"{PUBLIC_BASE_URL}/pago/exito",
        "failure": f"{PUBLIC_BASE_URL}/pago/fallo",
        "pending": f"{PUBLIC_BASE_URL}/pago/pendiente",
    }

    try:
        pref = payments.create_preference(items, payer, internal_id, back_urls)
    except RuntimeError as exc:
        log.exception("No se pudo crear la preferencia MP")
        return jsonify({"ok": False, "error": str(exc)}), 500

    init_point = pref.get("init_point") or pref.get("sandbox_init_point")
    if not init_point:
        log.error("MP no devolvio init_point: %s", pref)
        return jsonify({"ok": False, "error": "Mercado Pago no devolvio URL de pago"}), 500

    # Guardamos el preference_id junto a la orden para luego correlacionar
    orders.update_order(internal_id, mp_preference_id=pref.get("id"), mp_init_point=init_point)

    return jsonify({
        "ok": True,
        "order_id": internal_id,
        "init_point": init_point,
        "preference_id": pref.get("id"),
    })


@app.route("/api/order/<order_id>")
def api_order(order_id: str):
    order = orders.get_order(order_id)
    if not order:
        return jsonify({"ok": False, "error": "Orden no encontrada"}), 404
    return jsonify({"ok": True, "order": order})


# ============================================================
# Webhook de Mercado Pago
# ============================================================

@app.route("/webhook/mp", methods=["GET", "POST"])
def mp_webhook():
    # GET: ping simple que MP hace para validar que la URL existe.
    if request.method == "GET":
        return "ok", 200

    # POST: notificacion real. MP envia data_id con el id del pago (o del recurso).
    data = request.get_json(silent=True) or {}
    log.info("Webhook MP: %s", data)

    # IPN/Standard webhook: data_id = payment id cuando topic=payment
    topic = (data.get("type") or data.get("topic") or "").lower()
    resource_id = (
        data.get("data", {}).get("id")
        if isinstance(data.get("data"), dict)
        else data.get("data_id")
    )
    if topic == "payment" and resource_id:
        payment = payments.get_payment(str(resource_id))
        if not payment:
            log.warning("Webhook: no se pudo obtener pago %s", resource_id)
            return "ok", 200
        status = payment.get("status")
        order_id = (payment.get("external_reference") or "").strip()
        if order_id:
            orders.update_order(
                order_id,
                status=status,
                mp_payment_id=payment.get("id"),
                mp_status_detail=payment.get("status_detail"),
                mp_payment_type=payment.get("payment_type_id"),
            )
            log.info("Orden %s actualizada a %s", order_id, status)
    return "ok", 200


# ============================================================
# Errores
# ============================================================

@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html", config=catalog.get_config()), 404


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    port = int(os.environ.get("PORT", "5001"))  # 5000 lo suele agarrar AirPlay en macOS
    app.run(host="0.0.0.0", port=port, debug=debug)
