# ZEUZ DNC · dirección de diseño

La web ayuda al responsable de un taller a entender cómo llegan sus programas al control CNC y elegir el equipo. El motivo propio del producto es la conexión entre carpeta, dispositivo y puerto RS232, representada como una ruta técnica sencilla. Se mantienen imágenes, enlaces, datos comerciales y funcionalidades del catálogo existente.

## Auditoría inicial

El sitio publicado y el checkout local comparten Flask/Jinja y CSS. La portada tiene una imagen de taller útil y una identidad azul reconocible, pero mucha tipografía en mayúsculas, bordes y resplandores compiten. La navegación desaparece en móvil sin sustituto. El botón ENVIAR de la miniatura parece accionable aunque es decorativo. Se conserva el contenido útil y se corrigen estos puntos.

## Sistema antes de implementar

| Rol | Claro | Oscuro |
| --- | --- | --- |
| Lienzo | #F5F7FA | #0B111A |
| Superficie | #FFFFFF | #131E2B |
| Texto | #142235 | #F1F5FA |
| Secundario | #526174 | #ADBDCF |
| Acción | #086BC1 | #74CAFF |
| Identidad decorativa | #29B6F6 | #29B6F6 |

Cian del logo conservado; azul más oscuro para texto y botones sobre blanco. Tipografía de sistema, titulares 40–76 px, subtítulos 28–48 px, cuerpo 17–20 px, controles 14–16 px. Monoespaciada solo para etiquetas de conexión. Contrastes calculados en VALIDATION.md tras implementar.

Regular: [marca | navegación | región | carrito] / [titular + acciones | dispositivo] / [ruta de conexión] / [soluciones] / [selección de equipo] / [pasos] / [FAQ].
Compacto: [marca | carrito | menú] / [región y navegación desplegables] / [titular] / [acciones] / [dispositivo] / [ruta vertical] / [secciones en una columna].

El vidrio vive en la barra flotante y el enlace sobre la foto del producto. Las tarjetas usan superficies sólidas. La composición se distingue por el dispositivo y la ruta de conexión real; no se añaden métricas, testimonios ni funciones de sincronización en desarrollo. No hay animación automática; solo respuesta corta al presionar controles.

## Referencias aplicadas a web

- `accessibility.md › Vision`: “Support larger text sizes.” Zoom al 200 %, foco visible, lectura sin depender del color.
- `buttons.md › Best practices`: “Always include a press state for a custom button.” Controles táctiles de al menos 44 px.
- `liquid-glass.md › The two layers`: el vidrio queda en navegación y controles flotantes; superficies opacas al reducir transparencia o aumentar contraste.
- `branding.md › Best practices`: “Ensure branding always defers to content.” Se retiran resplandores y accesorios repetidos.
- `layout.md`, `typography.md`, `color.md`, `materials.md` y `designing-for-ios.md`: jerarquía, tamaños adaptables y materiales. Las convenciones nativas se traducen a navegación web, sin imitar pestañas de una app.

Se reduce un accesorio: la tira de marcas de controles se sustituye por una explicación de RS232 y una referencia a confirmar los parámetros de cada máquina. La compatibilidad no se da por garantizada solo por la marca.
