# Validación del rediseño · 22 septiembre 2026

## Vista previa

Desde `ZeuzDNC-Shop`:

```sh
.venv/bin/python design-review/preview.py
```

- Normal, respeta la apariencia del sistema: http://127.0.0.1:5088/
- Captura clara: http://127.0.0.1:5088/?preview_scheme=light
- Captura oscura: http://127.0.0.1:5088/?preview_scheme=dark
- Fixture de texto ampliado: http://127.0.0.1:5088/?preview_scheme=light&preview_text=200

Los parámetros de apariencia solo existen en el ejecutor local de revisión; no añaden controles ni rutas al sitio público. Este ejecutor no carga `.env`, desactiva credenciales de pagos y utiliza SQLite temporal. El servidor escucha únicamente en localhost. No se hicieron cobros ni despliegues.

## Comprobaciones completadas

- Sitio público de referencia inspeccionado en https://www.zeuzdnc.com/; contenido coincide con el proyecto local.
- Portada revisada visualmente en claro y oscuro, a 1280 px y 390 px; sección de ecosistema y preguntas revisadas en móvil.
- Ancho de 320 px: inicio, catálogo, ficha de producto, descargas, carrito y checkout sin desbordamiento horizontal (305 px de área útil debido a la barra de desplazamiento del navegador).
- Portada a 320 px con texto al 200 %: sin desbordamiento después de corregir mínimos de grid, botones y ajuste de texto. Los titulares largos se parten en varias líneas.
- Menú móvil abre, muestra todas las secciones y regiones, cierra con Escape y devuelve el foco al control. HTML `details` permite navegar sin JavaScript.
- Filtro iZEUZ muestra solo software; filtro Dispositivo muestra las dos variantes. Estado `aria-pressed` actualizado.
- Carrito: añadir equipo, aumentar cantidad, quitar y volver al estado vacío.
- Cambio de región a USD: una unidad $499 + $60 envío = $559. Dos unidades $998 + $60 = $1,058, iguales en carrito y checkout. Cotización MXN de una unidad: $10,324 con IVA + $250 envío = $10,574. Son los datos existentes, sin edición de precios.
- FAQ abre/cierra con `details`; enlaces de sección respetan la barra flotante.
- 11 rutas públicas y 39 enlaces/recursos internos comprobaron respuesta 200 o redirección 302. Producto inactivo conserva 404.
- Sin imágenes fallidas en portada ni errores/avisos de consola en la comprobación del navegador.
- `node --check` para los tres scripts involucrados y `git diff --check` correctos.

## Contraste calculado

| Texto / superficie | Relación |
| --- | --- |
| #142235 / #F5F7FA | 14.94:1 |
| #526174 / #F5F7FA | 5.89:1 |
| #FFFFFF / #086BC1 (botón) | 5.41:1 |
| #F1F5FA / #131E2B | 15.37:1 |
| #ADBDCF / #131E2B | 8.78:1 |
| #74CAFF / #131E2B | 9.32:1 |

Estos valores corresponden a colores sólidos de los tokens; no son una medición de cada píxel sobre fotografías o vidrio. El material tiene relleno alto y texto monocromo. Se implementan variantes opacas para `prefers-reduced-transparency`/`prefers-contrast`, ausencia de blur cuando no hay soporte, y eliminación de movimiento con `prefers-reduced-motion`. Estas preferencias se revisaron en código, no cambiando ajustes del sistema del usuario.

## Límites

Las capturas claras usan el fixture local porque el navegador del equipo está en modo oscuro. No se ejecutaron pagos, envíos de correo, descargas de binarios ni una auditoría completa con lector de pantalla. Las funciones y los mensajes comerciales existentes no se validaron contra hardware CNC. iZEUZ conserva su estado “Próximamente” cuando falta el enlace de App Store. La imagen existente del equipo sin pantalla está rotulada como referencia de la versión con pantalla.

Los cambios se limitan a `ZeuzDNC-Shop`: plantillas, estilos, accesibilidad del carrito/navegación y estos recursos de revisión. Sin cambios al backend de pagos, catálogo, base productiva, Zeuz Agent, ZeuzDNC ni iOS.
