# ZEUZ DNC · dirección de diseño · 8 noviembre 2026

La página presenta ZEUZ DNC a responsables y operadores de talleres CNC: explica cómo llega un programa desde la computadora hasta el control RS232, ofrece las descargas y permite explorar el equipo. El rediseño adopta una presentación de producto inspirada en Apple y conserva la identidad ZEUZ.

## Composición y color

El blanco predomina por petición del usuario, también cuando el sistema operativo usa apariencia oscura. El azul identifica acciones y acentos; el azul marino concentra la explicación del flujo de trabajo. No hay selector de apariencia.

| Rol | Color |
| --- | --- |
| Lienzo | #FFFFFF |
| Superficie secundaria | #F5F7FA |
| Texto principal | #142235 |
| Texto secundario | #526174 |
| Acción | #086BC1 |
| Azul de marca y titulares grandes | #1E88E5 |
| Sección de conexión | #0B1B30 |

Tipografía de sistema, titulares adaptables de aproximadamente 45–98 px, cuerpo de 17 px y monoespaciada solo en la vista ilustrativa de código. Los contrastes calculados están en `VALIDATION.md`.

Regular: [marca | sistema | descargas | tienda | región | carrito] / [titular centrado + acciones] / [producto amplio] / [archivo → revisión → CNC, visual fijo al desplazarse] / [iZEUZ y Agent] / [tienda] / [descargas y preguntas].

Compacto: [marca | carrito | menú] / [titular y producto] / [flujo en lectura vertical] / [aplicaciones] / [productos en una columna] / [descargas y preguntas]. El pie pasa a una columna por debajo de 380 px.

La firma visual es el recorrido del programa CNC: al desplazarse, la vista ilustrativa acompaña selección, revisión y envío. La imagen principal cambia de escala suavemente y las secciones aparecen al entrar en pantalla, sin interceptar el scroll. El contenido permanece disponible sin JavaScript y con movimiento reducido. La translucidez se limita a la navegación; las superficies de contenido son sólidas.

## Funciones y contenido

- Descargas oficiales de Zeuz Agent para Windows y Mac con Apple Silicon, con versión, tamaño y archivo SHA-256. La indicación para Mac nombra la arquitectura y no presupone que todo Mac es compatible.
- Tienda en `/tienda`, con `/catalogo` conservado; fichas, filtros, carrito y resumen calculado por el servidor. Los cobros quedan desactivados mediante `PAYMENTS_ENABLED=false`; Stripe se integrará más adelante.
- Precios identificados como referencia mientras se prepara la tienda. Sin nuevas métricas, testimonios ni promesas de entrega. La imagen del equipo sin pantalla se identifica como referencia de la versión táctil.
- Navegación móvil con `details`, enlaces descriptivos, foco visible y controles principales de al menos 44 px. Ajuste de palabras y mínimos de grid para mantener el contenido dentro de pantallas estrechas.

## Referencias aplicadas a web

- `accessibility.md › Vision`: “Support larger text sizes.” El diseño permite reflujo del texto y conserva la jerarquía.
- `motion.md › Best practices`: “Make motion optional.” `prefers-reduced-motion` elimina transiciones, transformaciones y scroll suave.
- `materials.md › Liquid Glass`: “Don’t use Liquid Glass in the content layer.” El material se reserva a la navegación y se vuelve opaco con transparencia reducida.
- `buttons.md › Best practices`: “Always include a press state for a custom button.” Las acciones tienen respuesta visual y foco de teclado.
- `branding.md › Best practices`: “Ensure branding always defers to content.” Se conserva el logo vectorial actual y se evita repetir adornos de marca.

También se consultaron `layout.md`, `typography.md`, `color.md` y `designing-for-ios.md`. Se aplican sus principios de jerarquía y accesibilidad a la web, sin reproducir convenciones exclusivas de una aplicación nativa.
