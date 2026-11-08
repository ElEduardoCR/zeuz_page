# ZEUZ DNC — Tienda oficial

Sitio público de ZEUZ DNC, con envíos **solo a México**, precios en **pesos mexicanos (MXN)** y **Stripe Checkout** como único proveedor de pago de esta tienda. iZEUZ conserva su compra independiente en el App Store. Mercado Libre queda fuera de este sitio y de esta integración.

La tienda es un proyecto separado de `ZeuzDNC/`, el panel que opera en la red del taller. Está construida con Flask/Jinja, CSS, JavaScript, SQLAlchemy y Stripe Checkout.

## Estado de los pagos

`PAYMENTS_ENABLED=false` es el valor predeterminado. El catálogo, el carrito y las cotizaciones funcionan con los cobros apagados; el checkout no crea pedidos ni sesiones de pago en ese estado. La presencia de llaves antiguas no activa el cobro.

Antes de activar pagos, verificar la base de datos persistente, el secreto de sesión, las credenciales, el webhook y el catálogo. Validar primero el flujo completo con credenciales de prueba de Stripe. El checkout muestra una indicación visible cuando usa modo de prueba. La activación productiva es un paso separado de cambiar el código o publicar el diseño.

No se inventan términos comerciales, políticas de devolución ni plazos de entrega. Los precios y el envío actuales se conservan como datos editables.

## Catálogo y cambios de precio

`data/products.json` contiene los productos y la configuración de México. Se relee en cada petición. Modificar `prices.MXN` cambia el precio neto del producto. Escribir importes en MXN con hasta dos decimales; el servidor normaliza cada unidad a centavos con redondeo HALF_UP antes de aplicar la tasa de IVA configurada.

| Producto | Precio neto actual |
| --- | ---: |
| ZEUZ DNC con pantalla táctil 7″ | $8,900 MXN |
| ZEUZ DNC sin pantalla | $7,499 MXN |

Se conserva IVA de 16 % y envío fijo de $250 MXN en `regions.MX.shipping_flat`. El precio de referencia de iZEUZ ($299 MXN) ya es final: no se añade IVA de nuevo y no se vende mediante Stripe. Estos valores son configuración existente, no una nueva política fiscal o comercial.

Ejemplo de cambio de precio:

```json
"prices": { "MXN": 8900 }
```

Para cambiar el envío, editar `regions.MX.shipping_flat`. Para ocultar un producto sin eliminarlo, usar `active: false`. Sus fotos están en `images`; `external: true` mantiene la compra en una tienda externa. Las existencias se consultan en el servidor. Los accesorios permanecen inactivos hasta que se habiliten expresamente.

Después de cambiar un importe:

1. Ejecutar las pruebas y revisar la ficha, el carrito y el resumen.
2. Comprobar la cotización y Stripe Checkout en modo de prueba, incluidos IVA y envío.
3. Publicar el catálogo actualizado mediante el despliegue normal de Vercel.

Los pedidos conservan una copia de sus importes: editar el catálogo no cambia el histórico. Si cambia un precio o el envío entre la revisión del carrito y el inicio del pago, el servidor rechaza la cotización anterior; la interfaz muestra el nuevo total y pide volver a continuar. Una sesión de Stripe ya creada conserva los importes de esa sesión.

## Flujo de compra

1. El visitante añade equipos al carrito, guardado en el navegador.
2. `POST /api/quote` recibe `{cart}` y devuelve las líneas, totales MXN y `quote_token`. El servidor resuelve precios, impuestos, envío y disponibilidad; no acepta precios del navegador.
3. El checkout solicita nombre y correo electrónico; el teléfono es opcional. `POST /api/checkout` recibe `{cart, customer, quote_token, attempt_id}`. `attempt_id` es un UUIDv4 que el navegador reutiliza al reintentar la misma selección y contacto.
4. El servidor valida la cotización y registra el intento. Stripe recibe la misma clave de idempotencia para evitar crear sesiones duplicadas por un reintento.
5. Stripe recopila los datos de pago y la dirección completa de envío, restringida a México. Los importes se envían en MXN.
6. El webhook firmado confirma el estado. La página de regreso muestra “Pago confirmado” únicamente cuando el servidor tiene un pago confirmado; visitar la URL de éxito no acredita un pago.

Los resultados públicos del pedido se restringen a la sesión del navegador que inició la compra y contienen solo información mínima, sin datos de contacto ni dirección. Los datos completos permanecen en administración. El navegador debe permitir las cookies de la tienda para conservar la sesión de compra.

Errores previstos: `quote_changed` pide revisar un total actualizado; `stock_unavailable` pide corregir la selección; `attempt_conflict` o `attempt_expired` requieren otro intento. En errores de conexión, el navegador reutiliza el mismo intento. El botón se bloquea durante la solicitud y una modificación del carrito en otra pestaña detiene el salto a Stripe para volver a revisar.

## Configuración y ejecución

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Vista local: http://localhost:5001. Administración: http://localhost:5001/admin.

| Variable | Función |
| --- | --- |
| `PAYMENTS_ENABLED` | Mantener `false` hasta completar la validación; `true` permite iniciar pagos si el resto de la configuración es válido. |
| `STRIPE_SECRET_KEY` | Credencial del entorno de prueba o producción. |
| `STRIPE_WEBHOOK_SECRET` | Verificación de eventos del webhook del mismo entorno. |
| `DATABASE_URL` | Base persistente para pedidos e intentos. SQLite local sirve para desarrollo; el disco efímero de Vercel no sirve para pedidos. |
| `FLASK_SECRET` | Secreto aleatorio y estable de al menos 32 caracteres para firmar las sesiones. |
| `PUBLIC_BASE_URL` | Dominio usado en los retornos; producción: `https://www.zeuzdnc.com`. |
| `ADMIN_PASSWORD` | Acceso al panel; sin contraseña el panel permanece cerrado. |
| `SUPPORT_EMAIL` | Dirección de soporte mostrada en la web. |
| `APP_STORE_URL` | Enlace oficial de iZEUZ; vacío mantiene “Próximamente”. |
| `RESEND_API_KEY`, `NOTIFY_EMAIL`, `NOTIFY_FROM` | Configuración de avisos de pedidos. |

Las credenciales y `DATABASE_URL` se configuran en Vercel para el entorno correspondiente. No se incluyen en el repositorio, capturas ni registros. La migración entre bases requiere trasladar los datos existentes; cambiar la variable no los copia.

El backend de persistencia usa SQLAlchemy y guarda dinero en centavos enteros. Las tablas incluyen pedidos e intentos de checkout. En PostgreSQL, el arranque solo comprueba la conexión; no crea tablas. Antes de habilitar pagos, aplicar la migración explícita necesaria y comprobar que las tablas están disponibles en la base persistente.

## Webhook de Stripe

Endpoint de producción:

```text
https://www.zeuzdnc.com/webhook/stripe
```

Eventos usados: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed` y `checkout.session.expired`. El secreto de firma debe corresponder a ese endpoint y al entorno utilizado. No se considera pagado un pedido solo por la redirección del navegador.

Para pruebas locales con Stripe CLI:

```sh
stripe listen --forward-to localhost:5001/webhook/stripe
```

El código histórico de Mercado Pago, si se conserva para pedidos antiguos, no lo habilita como opción para nuevas compras en la tienda oficial.

## Descargas

`/descargas` ofrece Zeuz Agent para Windows y Mac con Apple Silicon. `data/downloads.json` fija versión, plataforma, tamaño y SHA-256 de los archivos de GitHub Releases. Las rutas estables son:

- `/descargas/agent-windows`
- `/descargas/agent-macos`
- Las mismas rutas con `/sha256` entregan el archivo de verificación.

Ambos binarios de v0.4.1 fueron verificados el 8 de noviembre de 2026: HTTP 200 y `Content-Disposition: attachment`. Sus tamaños y SHA-256 proceden de la API pública de GitHub Releases. Para actualizar, cambiar juntos URL, versión, tamaño y checksum. Los binarios no se incluyen en el repositorio de la tienda.

## Pruebas y vista de diseño

```sh
python -m unittest discover -s tests -v
node --check static/js/cart.js
node --check static/js/shop.js
node --check static/js/checkout.js
node tests/test_checkout_frontend.js
node tests/test_receipt_frontend.js
.venv/bin/python design-review/preview.py
```

Los dos comandos de pruebas JavaScript ejecutan 26 escenarios de checkout y recibo con simulaciones locales: reintentos, cambios de precio, validación de redirecciones y limpieza segura del carrito. No usan navegador, red, credenciales ni cargos.

La vista de diseño corre en http://127.0.0.1:5088/, evita cargar `.env`, desactiva pagos y utiliza una base temporal. No sirve para validar un cobro productivo. `design-review/DESIGN.md` y `VALIDATION.md` documentan el rediseño; la validación de pago en Stripe debe registrarse por separado.

## Rutas y archivos principales

- `/`: presentación del producto; `/tienda`: catálogo; `/catalogo`: alias conservado.
- `/producto/<id>`, `/carrito`, `/checkout`: selección y pago.
- `products.py`, `data/products.json`: catálogo y cálculos.
- `app.py`, `orders.py`, `db.py`, `payments_stripe.py`: compra, persistencia y Stripe.
- `static/js/cart.js`, `shop.js`, `checkout.js`: carrito, cotización y salto al pago.
- `/admin`: consulta de pedidos, dirección de envío, seguimiento y notas internas.
