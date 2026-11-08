# Validación del rediseño · 8 noviembre 2026

## Vista previa

Desde `ZeuzDNC-Shop`:

```sh
.venv/bin/python design-review/preview.py
```

Vista local: http://127.0.0.1:5088/. El sitio mantiene la apariencia blanca independientemente del tema del sistema. El parámetro `?preview_text=200` es un fixture local que amplía el tamaño raíz de fuente al 200 %; no equivale a una prueba de zoom del navegador ni existe en producción.

El ejecutor evita cargar `.env`, elimina credenciales de pagos y correo, fija `PAYMENTS_ENABLED=false` y utiliza SQLite temporal. Escucha únicamente en localhost.

## Comprobaciones completadas

- Revisión visual mediante navegador a **1280×720**: portada, escena de scroll, tienda y carrito.
- Revisión visual a **390×844**: portada, descargas, ficha de producto y menú móvil.
- Revisión a **320×740**, incluido `preview_text=200`, de portada, tienda y carrito. Ancho del documento confirmado en 320 px. Se corrigieron palabras largas, mínimos de grid y disposición del pie y del carrito en el ancho más estrecho.
- **8 páginas y 322 referencias internas** comprobadas con el cliente de pruebas de Flask: recursos y anclas sin errores. Las páginas incluyen inicio, tienda, descargas, carrito, resumen y las tres fichas de producto.
- **12 pruebas de backend aprobadas**, sin credenciales productivas: bloqueo del checkout antes de crear pedidos, conservación de cotizaciones y precios del servidor, futura activación simulada, rutas y verificación de descargas, y estados públicos de la tienda.
- Pruebas de JavaScript mediante harness: almacenamiento corrupto o bloqueado, sincronización entre pestañas, respuestas de cotización fuera de orden, errores, reintento y carrito vacío.
- Descargas de Zeuz Agent **v0.4.1** verificadas contra GitHub Releases: ambos assets responden HTTP 200 con `Content-Disposition: attachment`. Versión, tamaños y SHA-256 corresponden a la metadata pública de esos assets. Las rutas locales redirigen a archivos de esa versión y entregan los checksums como adjuntos.
- La indicación de descarga en Mac se corrigió para decir “Para Mac con Apple Silicon”; no afirma haber detectado la arquitectura del equipo.

## Contraste calculado

| Texto / superficie | Relación |
| --- | --- |
| #142235 / #FFFFFF | 16.03:1 |
| #526174 / #FFFFFF | 6.32:1 |
| #526174 / #F5F7FA | 5.89:1 |
| #FFFFFF / #086BC1, botón | 5.41:1 |
| #1E88E5 / #FFFFFF, marca y titulares grandes | 3.68:1 |
| #F5F8FC / #0B1B30 | 16.24:1 |
| #C0CEDE / #0B1B30 | 10.81:1 |
| #78C4FF / #0B1B30, enlace | 9.18:1 |

Son relaciones de colores sólidos calculadas a partir de sus valores hexadecimales, no mediciones de todos los píxeles sobre fotografías o material translúcido. El azul de marca no se utiliza como texto pequeño sobre blanco.

## Alcance y límites

`prefers-reduced-motion`, `prefers-reduced-transparency` y `prefers-contrast` se verificaron en código; no se alternaron interactivamente las preferencias del sistema. No se realizó una auditoría completa con lector de pantalla ni una prueba contra hardware CNC. Las capturas PNG antiguas de este directorio son históricas y no representan el rediseño del 8 de noviembre.

No se hicieron cargos reales, pedidos reales ni envíos de correo. Los pagos permanecen desactivados; la integración de Stripe queda para una etapa posterior. Las pruebas de descargas verifican entrega y metadata, no instalación ni ejecución de los binarios. iZEUZ conserva “Próximamente” cuando falta el enlace de App Store.

La publicación productiva en Vercel forma parte del cierre de la tarea y su resultado se verifica por separado. Este registro acredita el código y la vista previa; no constituye confirmación de un despliegue productivo.
