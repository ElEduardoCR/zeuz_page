"""Catalogo de productos y precios por region.

Lee de data/products.json y resuelve precios en la moneda de cada region.

Modelo de precios
-----------------
`prices[<moneda>]` guarda SIEMPRE el precio NETO (sin impuesto). El impuesto
lo aporta la region: Mexico 16% de IVA, Estados Unidos 0% (la exportacion es
tasa 0 y no retenemos sales tax mientras no haya nexo).

Los productos `external` (iZEUZ, que se cobra en el App Store) son la
excepcion: su precio ya viene con impuesto incluido porque lo fija Apple, asi
que no se les aplica la tasa de la region.
"""
from __future__ import annotations

import json
import threading
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_DIR = Path(__file__).parent / "data"
PRODUCTS_FILE = DATA_DIR / "products.json"
_LOCK = threading.RLock()

# Monedas que manejamos, con su exponente de unidad minima (centavos).
_MINOR_UNITS = {"MXN": 2, "USD": 2}


def _load() -> Dict[str, Any]:
    with _LOCK:
        with PRODUCTS_FILE.open(encoding="utf-8") as fh:
            return json.load(fh)


# ============================================================
# Regiones
# ============================================================

def default_region() -> str:
    return _load().get("default_region", "MX")


def all_regions() -> Dict[str, Dict[str, Any]]:
    return _load().get("regions", {})


def get_region(code: Optional[str]) -> Dict[str, Any]:
    """Devuelve la config de una region. Cae a la region por defecto si no existe."""
    data = _load()
    regions = data.get("regions", {})
    fallback = data.get("default_region", "MX")
    key = (code or "").upper()
    if key not in regions:
        key = fallback
    region = dict(regions[key])
    region["code"] = key
    return region


def is_valid_region(code: Optional[str]) -> bool:
    return (code or "").upper() in _load().get("regions", {})


# ============================================================
# Dinero
# ============================================================

def _q(value: Decimal) -> Decimal:
    """Redondea a 2 decimales, medio hacia arriba (lo que espera un cliente)."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def to_minor_units(amount: Decimal, currency: str) -> int:
    """Convierte a la unidad minima que piden las pasarelas (centavos)."""
    exp = _MINOR_UNITS.get(currency.upper(), 2)
    return int((_q(amount) * (10 ** exp)).to_integral_value(rounding=ROUND_HALF_UP))


def price_for(product: Dict[str, Any], region: Dict[str, Any]) -> Dict[str, Any]:
    """Precio de un producto en una region: neto, impuesto y total.

    Devuelve floats listos para JSON. El calculo interno es Decimal para que
    el impuesto no se desvie por errores de punto flotante.
    """
    currency = region["currency"]
    raw = product.get("prices", {}).get(currency)
    if raw is None:
        return {
            "currency": currency,
            "net": 0.0,
            "tax": 0.0,
            "gross": 0.0,
            "tax_rate": 0.0,
            "available": False,
        }

    net = Decimal(str(raw))
    # Los productos externos traen precio final fijado por la tienda de Apple.
    rate = Decimal("0") if product.get("external") else Decimal(str(region.get("tax_rate", 0)))
    tax = _q(net * rate)
    gross = _q(net + tax)
    return {
        "currency": currency,
        "net": float(net),
        "tax": float(tax),
        "gross": float(gross),
        "tax_rate": float(rate),
        "available": True,
    }


# ============================================================
# Productos
# ============================================================

def _decorate(product: Dict[str, Any], region: Dict[str, Any]) -> Dict[str, Any]:
    """Copia el producto con el precio de la region ya resuelto."""
    out = dict(product)
    images = out.get("images") or []
    out["images"] = images
    # Conveniencia para plantillas que solo necesitan la portada.
    out["image"] = images[0] if images else ""
    out["price"] = price_for(product, region)
    return out


def all_products(region: Dict[str, Any], include_inactive: bool = False) -> List[Dict[str, Any]]:
    """Productos vendibles en una region, con precio resuelto.

    Filtra los desactivados (`active: false`) y los que no tienen precio en la
    moneda de la region.
    """
    out: List[Dict[str, Any]] = []
    for p in _load().get("products", []):
        if not include_inactive and not p.get("active", True):
            continue
        decorated = _decorate(p, region)
        if not decorated["price"]["available"]:
            continue
        out.append(decorated)
    return out


def get_product(
    product_id: str,
    region: Dict[str, Any],
    include_inactive: bool = False,
) -> Optional[Dict[str, Any]]:
    for p in _load().get("products", []):
        if p["id"] != product_id:
            continue
        if not include_inactive and not p.get("active", True):
            return None
        return _decorate(p, region)
    return None


def shipping_for(region: Dict[str, Any], subtotal_gross: Decimal) -> Decimal:
    """Costo de envio de la region. Tarifa plana, gratis si pasa el umbral."""
    flat = Decimal(str(region.get("shipping_flat") or 0))
    threshold = region.get("free_shipping_over")
    if threshold is not None and subtotal_gross >= Decimal(str(threshold)):
        return Decimal("0")
    return flat


def storefront_config(region: Dict[str, Any]) -> Dict[str, Any]:
    """Config que las plantillas y el JS necesitan para pintar precios."""
    return {
        "region": region["code"],
        "region_label": region.get("label", region["code"]),
        "currency": region["currency"],
        "locale": region.get("locale", "es-MX"),
        "tax_rate": float(region.get("tax_rate", 0)),
        "tax_label": region.get("tax_label", "IVA"),
        "shipping_flat": float(region.get("shipping_flat") or 0),
        "free_shipping_over": region.get("free_shipping_over"),
        "gateways": region.get("gateways", []),
        "default_gateway": region.get("default_gateway"),
        "customs_notice": bool(region.get("customs_notice")),
    }
