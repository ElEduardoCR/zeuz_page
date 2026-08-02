"""Panel de administracion de pedidos.

Responde la pregunta operativa: que pedidos entraron, quien los pago y a que
direccion hay que mandarlos.

Autenticacion deliberadamente minima: una contraseña compartida en
ADMIN_PASSWORD, guardada en la sesion firmada de Flask. Es suficiente para un
panel de una sola persona y no arrastra tabla de usuarios ni recuperacion de
contraseña. Si algun dia entran varias personas, esto se cambia por cuentas
reales.

Si ADMIN_PASSWORD no esta definida el panel queda CERRADO, no abierto. Un
panel con todas las direcciones de los clientes no puede quedar expuesto por
una variable de entorno que se olvido de poner.
"""
from __future__ import annotations

import hmac
import os
from functools import wraps
from typing import Any, Callable

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import orders

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

SESSION_KEY = "admin_ok"

CARRIERS = ["DHL Express", "FedEx", "Estafeta", "UPS", "Paquetexpress", "Otro"]


def _configured_password() -> str:
    return (os.environ.get("ADMIN_PASSWORD") or "").strip()


def login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if not _configured_password():
            abort(503, "Panel deshabilitado: falta definir ADMIN_PASSWORD.")
        if not session.get(SESSION_KEY):
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    expected = _configured_password()
    if not expected:
        abort(503, "Panel deshabilitado: falta definir ADMIN_PASSWORD.")

    error = ""
    if request.method == "POST":
        supplied = request.form.get("password", "")
        # Comparacion en tiempo constante: un `==` normal filtra por cuanto
        # tarda en fallar cuantos caracteres iniciales acerto quien prueba.
        if hmac.compare_digest(supplied, expected):
            session[SESSION_KEY] = True
            session.permanent = True
            target = request.args.get("next") or url_for("admin.orders_list")
            if not target.startswith("/"):
                target = url_for("admin.orders_list")
            return redirect(target)
        error = "Contraseña incorrecta."

    return render_template("admin/login.html", error=error)


@admin_bp.route("/logout", methods=["POST"])
def logout():
    session.pop(SESSION_KEY, None)
    return redirect(url_for("admin.login"))


@admin_bp.route("/")
@login_required
def orders_list():
    status = request.args.get("status") or ""
    search = request.args.get("q") or ""
    return render_template(
        "admin/orders.html",
        orders=orders.list_orders(status=status or None, search=search),
        counts=orders.counts_by_status(),
        active_status=status,
        search=search,
    )


@admin_bp.route("/orden/<order_id>")
@login_required
def order_detail(order_id: str):
    order = orders.get_order(order_id)
    if not order:
        abort(404)
    return render_template("admin/order_detail.html", order=order, carriers=CARRIERS)


@admin_bp.route("/orden/<order_id>/enviar", methods=["POST"])
@login_required
def mark_shipped(order_id: str):
    order = orders.get_order(order_id)
    if not order:
        abort(404)
    carrier = request.form.get("carrier", "").strip()
    tracking = request.form.get("tracking", "").strip()
    if not tracking:
        flash("Necesitas el numero de guia para marcar el pedido como enviado.", "error")
    else:
        orders.mark_shipped(order_id, carrier, tracking)
        flash("Pedido marcado como enviado.", "ok")
    return redirect(url_for("admin.order_detail", order_id=order_id))


@admin_bp.route("/orden/<order_id>/notas", methods=["POST"])
@login_required
def save_notes(order_id: str):
    if not orders.get_order(order_id):
        abort(404)
    orders.update_order(order_id, admin_notes=request.form.get("admin_notes", ""))
    flash("Notas guardadas.", "ok")
    return redirect(url_for("admin.order_detail", order_id=order_id))
