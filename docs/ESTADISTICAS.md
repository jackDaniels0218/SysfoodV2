# Inventario de estadísticas de SysFood V2

Todas las estadísticas exportables se declaran **una sola vez** en `reportes/consultas.py` (`ESTADISTICAS`). De ese registro salen la página *Sistema › Reportes*, el catálogo *Todas las estadísticas*, la exportación a PDF, Excel y CSV, y los envíos programados por correo. Para agregar una estadística basta con escribir su función y una línea en el registro.

Cada estadística devuelve el mismo formato: título, columnas, filas, uno o dos gráficos, un resumen y las opciones del filtro «estado». En pantalla cada gráfico se puede descargar como imagen PNG.

## Estadísticas exportables

| Clave | Estadística | Grupo | Filtros | Gráficos |
| --- | --- | --- | --- | --- |
| `donaciones` | Donaciones por periodo y estado | Donaciones e inventario | fechas, estado, categoría, donante, bodega | barras por estado · línea por mes |
| `inventario` | Inventario por vencimiento | Donaciones e inventario | fechas, vigencia, categoría, donante, bodega | dona por vigencia |
| `vencidos` | Productos vencidos y retirados | Donaciones e inventario | fechas, categoría, donante, bodega | barras por motivo |
| `solicitudes` | Solicitudes y entregas por estado | Solicitudes y entregas | fechas, estado, categoría, donante, bodega | barras de solicitudes · barras de entregas |
| `beneficiarios` | Beneficiarios por estado de verificación | Beneficiarios | fechas, estado | torta por estado |
| `necesidad` | Beneficiarios por grupo de necesidad | Beneficiarios | fechas, grupo | barras con el color de cada grupo |
| `zonas` | Beneficiarios por zona (**nueva**) | Beneficiarios | fechas, grupo | barras por zona · puntaje promedio por zona |
| `verificaciones` | Verificaciones automáticas y manuales (**nueva**) | Verificación de documentos | fechas, automática o manual | dona automática/manual · resultado por tipo |
| `tiempo_verificacion` | Tiempo promedio de verificación (**nueva**) | Verificación de documentos | fechas, automática o manual | horas por tipo de documento · horas por mes |
| `chat` | Consultas del asistente de ayuda (**nueva**) | Asistente de ayuda | fechas, cómo se respondió | dona por tipo de respuesta · línea por día |

La estadística `zonas` es la versión en tabla del **mapa de calor** (*Sistema › Mapa de beneficiarios*) y enlaza con él. El mapa tiene su propia exportación, anonimizada, en GeoJSON y CSV.

## Indicadores de los paneles (no exportables)

| Dónde | Qué muestra |
| --- | --- |
| Panel del administrador | Usuarios por rol y estado; donaciones y entregas por estado (gráficos); inventario disponible, próximo a vencer, vencido y reservado; documentos y solicitudes pendientes; mapa de calor |
| Panel del donante | Sus donaciones por estado (gráfico); cantidades donadas, entregadas y disponibles por unidad |
| Panel del beneficiario | Sus solicitudes por estado y sus entregas recientes |
| Inventario | Disponibles, próximos a vencer, vencidos por retirar, con reservas y cantidades por revisar |
| Consultas del asistente | Consultas de 30 días, sin respuesta, enviadas al administrador y calificación |

## Exportación y envíos

| Formato | Contenido |
| --- | --- |
| PDF | Título, filtros, resumen, gráficos y tabla |
| Excel | Hoja con la tabla, hoja de resumen y una hoja por gráfico con un gráfico nativo de Excel |
| CSV | Solo la tabla, en UTF-8 con BOM; el separador se configura en `reportes_separador_csv` |
| PNG | Cada gráfico en pantalla, con su título y el fondo del tema actual |

**Envíos programados** (*Reportes › Programar envío*): estadística, filtros, frecuencia (diaria, semanal o mensual), formato y destinatarios. Con «solo el último periodo», cada envío cubre el último día, semana o mes. La tarea horaria `reportes_programados` los envía a partir de `reportes_hora_envio`. Cada envío queda en la bitácora («Envío programado de reporte»), y cada exportación manual también.

**Parámetros** (*Parámetros › Reportes y estadísticas*): `reportes_dias_por_defecto` (rango cuando no se eligen fechas; 0 = todo), `reportes_separador_csv` y `reportes_hora_envio`.
