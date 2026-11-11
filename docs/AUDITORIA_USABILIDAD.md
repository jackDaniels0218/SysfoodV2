# Auditoría de usabilidad (mejora 5)

Se recorrieron los flujos principales en Chrome en escritorio (1366 px) y en celular (390 px), en modo claro y oscuro, con el teclado y con «reducir movimiento» activado. Para cada flujo se anotó dónde se trababa el usuario, y luego se corrigió cada problema. El estilo «Cosecha», el modo oscuro y el respeto a «reducir movimiento» se mantienen en todo lo nuevo.

## Hallazgos y correcciones

| Flujo | Problema encontrado | Corrección |
| --- | --- | --- |
| Todo el sistema | Para ir a un registro concreto (una persona, un producto, la solicitud #12) había que pasar por menús y filtros | **Búsqueda global** con <kbd>/</kbd> o <kbd>Ctrl</kbd>+<kbd>K</kbd>: páginas, usuarios, donaciones, inventario, solicitudes y códigos de entrega, según el rol. Se navega con las flechas y <kbd>Enter</kbd>, y sin JavaScript queda la página `/buscar/` |
| Todo el sistema | Sin atajos de teclado ni forma de descubrirlos | **Atajos:** <kbd>?</kbd> muestra la lista; <kbd>g</kbd> + letra lleva al panel, el inventario, las solicitudes, los documentos o los reportes según el rol; <kbd>t</kbd> cambia el tema; <kbd>Alt</kbd>+<kbd>A</kbd> abre el asistente. No se activan mientras se escribe |
| Todo el sistema | Las confirmaciones usaban la ventana nativa del navegador, que no sigue el estilo, en algunos celulares bloquea la página y no se puede leer bien con lector de pantalla | **Ventana de confirmación propia**, accesible (título, descripción y foco en el botón), para todos los formularios `data-confirmar` |
| Beneficiario: carrito | Al quitar un producto o vaciar el carrito por error se perdía lo elegido | **Deshacer:** el aviso trae un botón que lo devuelve al carrito si sigue disponible, y si ya no alcanza, explica por qué |
| Donante: registrar donación | Formulario largo de una sola vez, sin repaso antes de guardar | **Asistente en tres pasos** (productos → opciones → revisar y guardar), con validación por paso y una tabla de resumen. Si el servidor devuelve errores, abre el paso donde están. Sin JavaScript funciona como antes |
| Primer ingreso de cualquier rol | El usuario nuevo no sabía qué hacer primero (sobre todo el beneficiario: cargar documentos, esperar la verificación…) | **Guía «Primeros pasos»** en el panel, con avance, el paso actual resaltado y un botón a la pantalla donde se hace. Se calcula sola con los datos reales y desaparece al completarla (o con «Ocultar») |
| Listas vacías | Mensajes como «No hay entregas.» que no decían qué hacer, y que no distinguían entre «no hay nada» y «los filtros no encuentran nada» | **Estados vacíos útiles** en donaciones, entregas, solicitudes, usuarios, categorías, bodegas, carrito, inventario y búsqueda, con un ícono, una explicación y una acción (por ejemplo «Registrar mi primera donación» o «Quitar filtros») |
| Gráficos y búsqueda | Mientras cargaban se veían huecos en blanco | **Esqueletos** con brillo suave (se detiene con «reducir movimiento») en los gráficos y en los resultados de la búsqueda |
| Navegación con teclado | No había forma de saltar el menú, el foco casi no se veía y no se marcaba la página actual | Enlace **«Saltar al contenido»** (primer <kbd>Tab</kbd>), anillo de foco visible en todos los controles y `aria-current="page"` en el menú |
| Lectores de pantalla | Varios filtros sin etiqueta, mensajes que no se anunciaban, iconos leídos como texto | Etiquetas (`aria-label` o `<label>`) en los filtros de donaciones, entregas, solicitudes y categorías; avisos con `role="status"` o `alert` dentro de una región `aria-live`; iconos decorativos con `aria-hidden`; `caption` y `scope` en las tablas nuevas o rediseñadas (inventario, reportes, envíos programados, consultas del asistente) |
| Celular | Las tablas con etiquetas ocultas desbordaban la página a lo ancho (con «reducir movimiento») | `.table-responsive` contiene ahora a sus elementos posicionados: sin desborde horizontal en ninguna lista (corregido en la mejora 6) |

## Cómo se verificó

- **Pruebas automáticas:** `core/tests/test_ux.py` cubre la búsqueda por rol, incluido que no revele donantes anónimos ni datos ajenos; el enlace para saltar al contenido y los atajos; la guía de cada rol; deshacer en el carrito; los estados vacíos y el asistente de donación.
- **Navegador real (Chrome):** búsqueda con <kbd>Ctrl</kbd>+<kbd>K</kbd> → flechas → <kbd>Enter</kbd>; <kbd>?</kbd> y <kbd>g</kbd> <kbd>i</kbd>; vaciar el carrito con la ventana de confirmación y deshacer; la donación completa por el asistente; la guía en un celular en modo oscuro. Sin errores de JavaScript y sin desborde horizontal a 390 px.

## Pendiente (no se hizo)

- No se hicieron pruebas con usuarios reales ni con lectores de pantalla como NVDA o VoiceOver: solo revisión técnica y navegación con teclado.
- No se midió el contraste de cada combinación de colores con una herramienta; se revisó a ojo en los dos temas.
