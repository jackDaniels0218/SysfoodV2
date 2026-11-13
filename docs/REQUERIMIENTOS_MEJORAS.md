# Requerimientos de las mejoras (23 a 31)

Estos requerimientos amplían los 22 originales. Siguen la numeración del documento de requerimientos e indican su tipo, la descripción y los criterios de aceptación con que se verifican. La implementación y las pruebas de cada uno están en [REQUERIMIENTOS.md](REQUERIMIENTOS.md).

---

## RF-23. Puntaje automático de necesidad y grupos de prioridad

**Tipo:** funcional · **Actor:** sistema y administrador

**Descripción.** El sistema calcula automáticamente un puntaje de necesidad de 0 a 100 para cada beneficiario. El puntaje es una suma ponderada de seis criterios: nivel de Sisbén, estrato, personas en el hogar, condición de discapacidad, solicitudes recientes y tiempo sin recibir ayuda. Según el puntaje, el beneficiario queda clasificado en un grupo de prioridad. Las solicitudes pendientes se atienden en orden de prioridad.

**Criterios de aceptación**

1. El puntaje se recalcula solo cuando cambian los datos o los documentos del beneficiario, cuando se aprueba una entrega y cada noche.
2. Los pesos, las escalas y los grupos (nombre, puntaje mínimo y color) se configuran en *Parámetros*, y cada cambio recalcula a todos los beneficiarios.
3. El administrador ve el desglose del puntaje por criterio. Una página pública explica la fórmula con ejemplos y una nota de equidad.
4. Las listas de usuarios y de solicitudes se filtran por grupo, y existe un reporte exportable por grupo.
5. Cada cálculo y cada cambio de grupo quedan en la bitácora con el motivo y la fecha.

---

## RF-24. Mapa de beneficiarios y mapa de calor

**Tipo:** funcional · **Actor:** administrador

**Descripción.** El panel del administrador muestra un mapa con la ubicación de los beneficiarios y un mapa de calor de la necesidad por zona. Las direcciones se convierten en coordenadas automáticamente.

**Criterios de aceptación**

1. La geocodificación es automática, guarda en caché las direcciones ya consultadas y reintenta las fallidas. Después de varios intentos fallidos, marca la dirección para revisión manual.
2. La intensidad del calor combina el puntaje, el número de solicitudes y el tamaño del hogar, con pesos configurables.
3. Las capas de puntos y de calor se pueden activar y desactivar, y se filtran por grupo, estado de verificación y rango de fechas.
4. El mapa usa librerías locales y teselas gratuitas de OpenStreetMap, y solo lo ve el administrador.
5. La exportación (GeoJSON o CSV) es anónima y desplaza los puntos al azar para no revelar la ubicación exacta. Cada consulta y cada exportación quedan en la bitácora.

---

## RF-25. Carga de documentos y verificación automática (OCR)

**Tipo:** funcional · **Actor:** beneficiario, sistema y administrador

**Descripción.** El beneficiario carga sus documentos desde el celular o el computador. El sistema revisa la calidad de la imagen al instante, lee el documento con OCR y lo compara con los datos registrados para decidir de forma automática.

**Criterios de aceptación**

1. La carga permite arrastrar el archivo, tomar una foto con la cámara, ver una vista previa y seguir el avance con una barra de progreso. Las fotos grandes se reducen solas.
2. Una foto borrosa, oscura o pequeña se rechaza de inmediato con el motivo y la indicación de repetirla.
3. El OCR (Tesseract) compara el número de documento, los nombres y las fechas, y calcula una confianza de 0 a 100.
4. Decisión por semáforo con umbrales configurables:
   - **Alta:** el documento queda pre-aprobado.
   - **Media:** pasa a la cola del administrador con las discrepancias resaltadas.
   - **Baja o ilegible:** se rechaza con el motivo.
5. El administrador ve lo que se leyó junto a la imagen y puede revertir cualquier decisión automática. Si el OCR no está disponible, el flujo manual sigue funcionando.

---

## RF-26. Asistente de ayuda (chat)

**Tipo:** funcional · **Actor:** visitante, donante, beneficiario y administrador

**Descripción.** Un asistente de chat, disponible en todas las páginas incluso antes de ingresar, responde preguntas sobre el uso del sistema y sobre los propios datos del usuario.

**Criterios de aceptación**

1. Las respuestas dependen del contexto: la página donde está el usuario, su rol y su estado. El asistente informa el estado de las solicitudes, documentos, donaciones o el puntaje del usuario que pregunta.
2. La base de conocimiento se genera sola con los valores vigentes de los parámetros.
3. Nunca revela datos de otras personas ni la identidad de los donantes anónimos.
4. Cuando no sabe la respuesta, ofrece enviar la consulta al administrador, quien recibe una notificación. El envío queda en la bitácora.
5. El modo con la API de Claude es opcional y se activa con una variable de entorno. Si falla, el asistente vuelve al modo de reglas. Hay un canal opcional de WhatsApp (Meta o Twilio) que verifica las firmas de los mensajes.

---

## RF-27. Inventario con cantidades coherentes según la unidad

**Tipo:** funcional y de integridad · **Actor:** donante, beneficiario y administrador

**Descripción.** Las unidades contables (latas, cajas, unidades…) solo admiten números enteros. Las divisibles (kg, g, L, mL) admiten decimales. Las cantidades se muestran según su unidad. El panel de inventario se rediseña para la gestión diaria.

**Criterios de aceptación**

1. La regla se valida en el formulario, en el servidor y en la base de datos (restricciones `CHECK`), y se aplica a donaciones, ajustes, carrito, solicitudes y entregas.
2. Las cantidades se muestran según su unidad, por ejemplo «50 kg», «24 latas», «1 lata» o «2,5 L». Las abreviaturas se configuran en *Parámetros*.
3. Los datos existentes se migran sin pérdidas, y un informe lista los registros que no cumplen la regla.
4. El panel muestra indicadores, alertas de vencimiento, vista en tabla o en tarjetas, ajuste rápido y filtros que cada usuario puede guardar.

---

## RF-28. Estadísticas, exportación y reportes programados

**Tipo:** funcional · **Actor:** administrador

**Descripción.** Todas las estadísticas se declaran en un registro único. Cada una tiene gráfico, filtros propios y exportación en varios formatos, y se puede programar su envío por correo.

**Criterios de aceptación**

1. Existe un inventario de todas las estadísticas, en una página del sistema y en un documento.
2. Cada estadística se exporta a PDF, Excel y CSV, y su gráfico como imagen PNG.
3. Se agregan estadísticas nuevas: beneficiarios por zona, verificaciones automáticas frente a manuales, tiempo promedio de verificación y consultas del asistente.
4. Los reportes se envían por correo de forma programada (diaria, semanal o mensual), con formato y destinatarios elegidos. Cada envío queda en la bitácora.
5. El rango de fechas por defecto, el separador del CSV y la hora de envío se configuran en *Parámetros*.

---

## RNF-29. Usabilidad y accesibilidad

**Tipo:** no funcional · Amplía el requerimiento 20

**Descripción.** La interfaz facilita los flujos principales y es accesible con el teclado y con lector de pantalla. Conserva el estilo visual, el modo oscuro y el respeto a «reducir movimiento».

**Criterios de aceptación**

1. Hay una auditoría documentada de los flujos principales, con cada problema encontrado y su corrección.
2. Existe una búsqueda global con <kbd>Ctrl</kbd>+<kbd>K</kbd> que respeta el rol de quien busca, y atajos de teclado con su ayuda en pantalla.
3. Hay asistentes guiados: una guía de «Primeros pasos» para cada rol y el registro de donaciones en tres pasos.
4. Las acciones destructivas piden confirmación en una ventana accesible. Al quitar productos del carrito o vaciarlo se puede deshacer.
5. Las listas vacías muestran un mensaje útil con la siguiente acción. Mientras algo carga se muestra un esqueleto de carga. Hay enlace para «Saltar al contenido», el foco es visible y los avisos se anuncian al lector de pantalla.

---

## RNF-30. Automatización parametrizada y auditable

**Tipo:** no funcional · Transversal

**Descripción.** El sistema decide solo en los casos claros y deja al administrador únicamente los dudosos. Todo umbral o regla es configurable, y toda decisión automática se puede auditar.

**Criterios de aceptación**

1. Cada regla automática (pesos, umbrales, grupos, límites) es un parámetro con tipo, rango y validación, editable en *Parámetros*.
2. Cada decisión automática queda en la bitácora con el motivo y la fecha.
3. Los procesos automáticos (vencimientos, puntajes, geocodificación, OCR, reportes y limpieza) están en un registro único, se ejecutan una sola vez por periodo y se pueden lanzar a mano desde *Tareas automáticas*.

---

## RNF-31. Despliegue en la nube y calidad del software

**Tipo:** no funcional · Amplía los requerimientos 21 y 22

**Descripción.** El sistema se despliega en la nube con PostgreSQL y mantiene controles automáticos de calidad.

**Criterios de aceptación**

1. PostgreSQL es el motor principal (también funciona con MySQL 8). La conexión se configura con `DATABASE_URL` o con variables de entorno.
2. El despliegue en Render se hace en un paso con `render.yaml`, que crea la base y el servicio web en Docker con HTTPS. El contenedor no corre como root.
3. En producción, el sistema no arranca con la clave de desarrollo, y la revisión `check --deploy` de Django no reporta avisos.
4. La integración continua (GitHub Actions) revisa el formato y el análisis estático (ruff), las migraciones y las pruebas sobre PostgreSQL, con una cobertura mínima del 80 %.
