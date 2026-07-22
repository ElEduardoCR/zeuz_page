# ZEUZ DNC — Tienda

Tienda pública del sistema **ZEUZ DNC**. Permite comprar el dispositivo, accesorios y
licencias con pago vía Mercado Pago (Checkout Pro). Proyecto aparte del
panel de operación (ZeuzDNC/) — separados a propósito porque la tienda va
expuesta a internet y el panel corre aislado en el taller.

## Stack

- **Flask 3** — backend
- **Mercado Pago SDK** (Checkout Pro) — pagos
- **Vanilla JS + localStorage** — carrito
- **CSS puro** — sin frameworks
- **Gunicorn** — servidor WSGI para producción

## Estructura

```
ZeuzDNC-Shop/
  app.py                  Flask app: rutas de la tienda + API
  products.py             Carga el catálogo desde data/products.json
  orders.py               Persistencia de órdenes (append-only en disco)
  payments.py             Integración con Mercado Pago
  data/
    products.json         Catálogo editable (precios, descripciones, stock)
    orders.jsonl          Órdenes (un JSON por línea)
  templates/
    base.html             Layout común
    index.html            Landing
    catalog.html          Listado
    product.html          Detalle
    cart.html             Carrito
    checkout.html         Formulario + resumen
    success.html          Pago aprobado
    failure.html          Pago rechazado
    pending.html          Pago pendiente
    404.html
  static/
    css/shop.css          Estilos con la paleta del logo
    js/cart.js            Carrito en localStorage
    js/shop.js            UI del carrito y checkout
    img/                  Logo + SVGs de productos
  requirements.txt
  .env.example
  README.md
```

## Puesta en marcha

### 1. Instalar dependencias

```bash
cd ZeuzDNC-Shop
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar Mercado Pago

1. Entra a https://www.mercadopago.com.mx/developers/panel/credentials
2. Crea una aplicación (tipo "Checkout Pro" o similar)
3. Copia tu **Access Token** y **Public Key** (empieza con las de TEST)
4. Edita `.env` y reemplaza los placeholders:
   ```
   MP_ACCESS_TOKEN=APP_USR-123456789...
   MP_PUBLIC_KEY=APP_USR-abcd-1234-...
   MP_ENV=sandbox
   ```

### 3. Arrancar

```bash
python app.py
# Abre http://localhost:5000
```

Para desarrollo con auto-reload:

```bash
FLASK_DEBUG=1 python app.py
```

## Flujo de pago

1. El cliente navega el catálogo y agrega productos al carrito
   (se guarda en `localStorage`).
2. Va a `/checkout`, llena sus datos.
3. El backend (`POST /api/create-pref`) crea la orden en disco, valida
   los precios contra el catálogo (nunca confía en el precio del cliente),
   y crea una **preferencia de Mercado Pago**.
4. Redirige a `init_point` (sandbox o producción según `MP_ENV`).
5. MP procesa el pago y redirige a:
   - `/pago/exito` — aprobado
   - `/pago/fallo` — rechazado
   - `/pago/pendiente` — esperando (OXXO, SPEI, etc.)
6. MP notifica al webhook `POST /webhook/mp` con el id del pago.
7. El backend consulta el pago, lo valida y actualiza el estado de la
   orden en disco.

## Configurar el webhook de MP

En el panel de MP Developers (Tus integraciones → Webhooks), apunta a:

```
https://TU-DOMINIO/webhook/mp
```

Para pruebas locales usa [ngrok](https://ngrok.com) o similar y configura
la URL temporal en MP.

## Editar el catálogo

Abre `data/products.json` y modifica/agrega productos. Los cambios se leen
en cada request, no hace falta reiniciar. Estructura:

```json
{
  "id": "zeuzdnc-device",
  "name": "Nombre visible",
  "short": "Subtítulo de una línea",
  "description": "Descripción completa",
  "price": 5499,
  "image": "img/product-xxx.svg",
  "badge": "Más vendido",
  "stock": 10,
  "category": "dispositivo"
}
```

- `price` en pesos mexicanos (entero, sin centavos por simplicidad).
- `stock` entero. Si es 0, se muestra "Agotado".
- `image` ruta relativa a `static/`.
- `category` libre (`dispositivo`, `accesorio`, `software`, etc.) — útil para
  filtrar más adelante.

## Personalizar marca

- Colores: edita las variables CSS en `static/css/shop.css` (sección
  `:root` arriba del archivo).
- Logo: reemplaza `static/img/logo.png` por tu versión.
- Textos: cada template es un HTML plano, sin framework.

## Producción

Antes de salir a producción:

1. **Credenciales LIVE**: cambia a las credenciales de producción en `.env`
   y pon `MP_ENV=production`.
2. **HTTPS obligatorio**: Mercado Pago requiere HTTPS para webhooks.
3. **Variable `PUBLIC_BASE_URL`**: apunta al dominio público real.
4. **Cambia `FLASK_SECRET`** por algo aleatorio.
5. **Servidor WSGI**: usa `gunicorn` o `uwsgi` en vez de `app.run()`.
   Ejemplo: `gunicorn -w 2 -b 0.0.0.0:5000 app:app`.
6. **Persistencia de `data/orders.jsonl`**: monta ese directorio en
   volumen si usas contenedor, o usa SQLite si esperas mucho volumen.

## Imágenes de campaña

La portada incluye dos fotografías generadas para esta tienda con personas
completamente ficticias: una estación ZEUZ DNC en uso y la app iZEUZ junto a
un torno CNC. Los archivos finales viven en `static/img/`.
