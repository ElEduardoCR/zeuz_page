# ZEUZ DNC — Tienda

Tienda pública del sistema **ZEUZ DNC**. Vende el dispositivo en sus dos
variantes a México y Estados Unidos, con pagos por **Stripe** y **Mercado
Pago**. Proyecto aparte del panel de operación (`ZeuzDNC/`) — separados a
propósito porque la tienda va expuesta a internet y el panel corre aislado en
el taller.

## Stack

- **Flask 3** — backend
- **Stripe Checkout** — pagos en Estados Unidos y (opcional) México
- **Mercado Pago Checkout Pro** — pagos en México
- **SQLAlchemy Core** — persistencia (SQLite local, Postgres/Supabase en prod)
- **Resend** — avisos de pedido por correo
- **Vanilla JS + localStorage** — carrito
- **CSS puro** — sin frameworks

## Estructura

```
ZeuzDNC-Shop/
  app.py                  Rutas públicas, API, webhooks, cálculo de totales
  admin.py                Panel de pedidos (/admin)
  products.py             Catálogo, regiones y precios
  db.py                   Motor y esquema de base de datos
  orders.py               Alta y consulta de pedidos
  payments_stripe.py      Stripe Checkout + verificación de webhook
  payments.py             Mercado Pago Checkout Pro
  notifications.py        Avisos por correo vía Resend
  data/
    products.json         Catálogo y config de regiones (editable)
    shop.db               SQLite local (ignorado por git)
  templates/
    base.html             Layout de la tienda
    index/catalog/product/cart/checkout/…
    admin/                Layout, login, listado y detalle de pedidos
  static/
    css/shop.css          Estilos de la tienda
    css/admin.css         Estilos del panel
    js/cart.js            Carrito en localStorage
    js/shop.js            UI del carrito y checkout
```

## Regiones

Una región define moneda, impuesto, envío y pasarelas disponibles. Se
configuran en `data/products.json` bajo `regions`:

| | México | Estados Unidos |
|---|---|---|
| Moneda | MXN | USD |
| Impuesto | IVA 16% | 0% (exportación tasa 0; sin nexo en EE. UU.) |
| Envío | $250 tarifa plana | $60 tarifa plana |
| Pasarelas | Mercado Pago, Stripe | Stripe |
| Aduana | — | Aviso de aranceles DAP en el checkout |

El visitante cambia de región con el selector de la barra superior; la
elección se guarda en la cookie `zeuz_region` por un año.

**Los precios en `products.json` son siempre netos (sin impuesto).** El
impuesto lo aporta la región. Los productos con `external: true` (iZEUZ, que
cobra Apple) son la excepción: su precio ya viene final.

> Las tarifas de envío ($250 MXN / $60 USD) son **provisionales**. Cámbialas
> en `regions.<código>.shipping_flat`. Para dar envío gratis a partir de un
> monto, pon `free_shipping_over`.

## Puesta en marcha

### 1. Dependencias

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configuración

```bash
cp .env.example .env
```

Llena `.env` siguiendo los comentarios del propio archivo. Lo mínimo para
arrancar en local es `ADMIN_PASSWORD`; sin llaves de pasarela la tienda
navega pero no cobra.

**Nunca** commitees `.env` ni pegues una llave secreta (`sk_…`, contraseña de
base de datos) en un chat, ticket o captura. Si pasa, rótala.

### 3. Arrancar

```bash
python app.py
```

Abre http://localhost:5001 (el 5000 lo suele tomar AirPlay en macOS).
El panel de pedidos está en http://localhost:5001/admin

Con auto-reload:

```bash
FLASK_DEBUG=1 python app.py
```

## Base de datos

El destino lo decide `DATABASE_URL`:

| Entorno | Valor |
|---|---|
| Local | vacío → `sqlite:///data/shop.db` |
| Supabase | `postgresql://postgres.<ref>:<password>@aws-0-<región>.pooler.supabase.com:6543/postgres` |

Las tablas se crean solas al arrancar. Migrar de SQLite a Postgres es cambiar
esa variable: no hay una segunda ruta de código que mantener.

> En Vercel usa siempre la cadena del **pooler** (puerto 6543), no la conexión
> directa (`db.<ref>.supabase.co:5432`). Cada invocación serverless abre su
> propia conexión y la conexión directa se queda sin cupo; además su host es
> IPv6 y Vercel no siempre lo alcanza.

Los importes se guardan en **centavos** (enteros). SQLite no tiene tipo
decimal y los flotantes acumulan error al sumar; los enteros son exactos en
ambas bases y son lo que piden las dos pasarelas.

## Flujo de pago

1. El cliente arma el carrito (`localStorage`) y va a `/checkout`.
2. El resumen pide los totales a `POST /api/quote` — el navegador nunca los
   calcula, para que lo mostrado sea exactamente lo que se cobra.
3. `POST /api/checkout` resuelve el carrito **contra el catálogo del
   servidor** (ignora cualquier precio que mande el cliente), da de alta la
   orden como `pending` y crea la sesión de pago.
4. Redirige a Stripe Checkout o a Mercado Pago según la pasarela elegida.
5. La pasarela redirige de vuelta a `/pago/exito|fallo|pendiente`.
6. El webhook (`/webhook/stripe` o `/webhook/mp`) confirma el cobro, marca la
   orden como `paid` y dispara el aviso por correo.

El webhook es la fuente de verdad, no el redirect: el cliente puede cerrar el
navegador antes de volver.

### Webhooks

**Stripe** — https://dashboard.stripe.com/webhooks

```
https://www.zeuzdnc.com/webhook/stripe
```

Eventos: `checkout.session.completed`, `checkout.session.async_payment_succeeded`,
`checkout.session.async_payment_failed`, `checkout.session.expired`.
Copia el signing secret a `STRIPE_WEBHOOK_SECRET`. Sin él la firma no se puede
verificar y el endpoint rechaza todo — que es lo correcto: es lo que impide
que alguien mande un POST falso diciendo que una orden fue pagada.

**Mercado Pago** — Tus integraciones → Webhooks

```
https://www.zeuzdnc.com/webhook/mp
```

Para probar en local usa `stripe listen --forward-to localhost:5001/webhook/stripe`
o un túnel tipo ngrok.

## Panel de pedidos

`/admin`, protegido con `ADMIN_PASSWORD`. Muestra por pedido: cliente,
**dirección completa de envío** (con botón de copiar, lista para pegar en la
guía), productos, importes, moneda, pasarela y estado del pago. Permite
marcarlo como enviado con paquetería y número de guía, y dejar notas internas.

**Si `ADMIN_PASSWORD` no está definida el panel queda cerrado, no abierto.**
Contiene las direcciones de todos los clientes y no puede quedar expuesto
porque se olvidó una variable de entorno.

## Editar el catálogo

`data/products.json`. Se relee en cada request, no hace falta reiniciar.

```json
{
  "id": "zeuzdnc-touch",
  "active": true,
  "name": "Nombre visible",
  "short": "Subtítulo de una línea",
  "description": "Descripción completa",
  "prices": { "MXN": 8900, "USD": 499 },
  "includes": ["Lo que trae la caja"],
  "images": ["img/foto-1.jpg", "img/foto-2.jpg"],
  "badge": "Más vendido",
  "stock": 10,
  "category": "dispositivo"
}
```

- `active: false` oculta el producto de la tienda sin borrarlo, y su ficha
  responde 404. Así están hoy el adaptador RS232 y el cable DB9.
- `images` es una galería: con una sola foto la ficha se ve como siempre, con
  varias aparecen miniaturas. Agregar fotos es agregar rutas aquí.
- `external: true` marca los productos que cobra otra tienda (iZEUZ en el App
  Store): se muestra el precio y el distintivo, pero no se puede añadir al
  carrito.

La ficha de iZEUZ muestra “Próximamente” mientras `APP_STORE_URL` esté vacía.
Al llenarla, el distintivo se vuelve un enlace al App Store.

## Pendientes conocidos

- Precios y tarifas de envío provisionales.
- Clasificación arancelaria y dictamen de origen T-MEC para exportar a EE. UU.
- Stripe Tax queda pendiente hasta que haya nexo económico en algún estado.
  Hoy el IVA se calcula aquí y a Stripe se le mandan importes ya con impuesto.
