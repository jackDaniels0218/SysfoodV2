# Guía de pruebas manuales

Antes de empezar: `python manage.py migrate`, `python manage.py cargar_demo` y `python manage.py runserver`.
Contraseña de todas las cuentas de demostración: **`Sysfood2025*`**.
Marque cada casilla cuando el resultado coincida con lo esperado.

> Consejo: abra una ventana normal para el administrador y una ventana de incógnito para el donante o el beneficiario, así puede tener dos sesiones a la vez.

## 1. Acceso y autenticación (Actividades 1, 10 y 17)

- [ ] **Registro de donante:** *Registrarse* → «Donante». Si elige «Persona jurídica» aparece *Razón social* y el tipo de documento cambia a NIT. Sin marcar la política de datos sale el error «Debe aceptar la política…».
- [ ] **Contraseña débil:** use `abc12345`. Se rechaza porque debe tener mayúscula, minúscula, número y carácter especial. Si las dos contraseñas no coinciden, también se rechaza.
- [ ] **Correo repetido:** regístrese con `donante@sysfood.local`. Sale «Ya existe una cuenta con este correo».
- [ ] **Registro de beneficiario:** una fecha de expedición futura se rechaza. Al terminar, la cuenta queda *Pendiente* y lo lleva a *Documentos*.
- [ ] **Bloqueo:** en *Ingresar* escriba 5 veces una contraseña errada para `donante@sysfood.local`. La cuenta queda bloqueada 15 minutos y ni siquiera con la contraseña correcta se puede entrar. El administrador puede desbloquearla en *Usuarios › (usuario) › Desbloquear*.
- [ ] **Recuperar contraseña:** *¿Olvidó su contraseña?* → su correo. Sin SMTP configurado, el enlace aparece en la consola del servidor. Ábralo, defina una nueva contraseña y vuelva a abrir el mismo enlace: debe decir que ya no es válido.
- [ ] **Acceso por dirección:** como beneficiario escriba en el navegador `http://127.0.0.1:8000/inventario/`. Sale «Acceso denegado». Sin sesión iniciada, lo envía a *Ingresar*.

## 2. Documentos de validación (Actividades 2 y 18)

Con `nuevo@sysfood.local` (o con un beneficiario recién registrado):

- [ ] Cargar un archivo `.docx` o `.exe` → «Formato no permitido».
- [ ] Renombrar un `.txt` a `.pdf` y cargarlo → «El contenido del archivo no corresponde a un PDF válido».
- [ ] Cargar un archivo de más de 5 MB → «supera el tamaño máximo».
- [ ] Cargar con otra cuenta exactamente el mismo archivo → «Este documento ya fue cargado en otra cuenta».
- [ ] En el celular, **Tomar foto con la cámara** abre la cámara trasera.
- [ ] Al completar identidad, Sisbén y residencia (más discapacidad, si marcó esa opción), la cuenta pasa a **En revisión**.
- [ ] Como administrador: *Usuarios › Documentos por revisar*. Se ve la vista previa. Rechazar sin observación no se permite; rechace uno con observación → el beneficiario queda **Rechazado** y recibe la notificación con el motivo. Vuelve a cargarlo → *En revisión* → apruebe todos → **Verificado**.
- [ ] Copie el enlace «Ver» de un documento e intente abrirlo con otra cuenta → *Acceso denegado*.

## 3. Categorías, bodegas y parámetros (Actividades 3, 4 y 9)

Como administrador:

- [ ] *Inventario › Categorías*: cree «Panadería» con 2 días de alerta. Intente crear «panadería» otra vez → nombre repetido.
- [ ] Elimine «Granos», que tiene productos → queda **Inactiva** y no se elimina. Elimine una categoría nueva sin productos → se elimina.
- [ ] *Inventario › Bodegas*: lo mismo. La bodega con inventario se inactiva.
- [ ] *Sistema › Parámetros*: cambie `max_productos_solicitud` a `abc` → error. Cámbielo a `3` → se guarda y aparece en *Trazabilidad › Bitácora* como «Cambio de parámetro».
- [ ] Cambie `unidades_medida` agregando `arrobas`. Al donar ya aparece *Arrobas* en la lista de unidades.

## 4. Donaciones e inventario (Actividades 5, 6 y 12)

- [ ] Como `donante@sysfood.local`: *Donar* → dos productos (botón «Agregar otro producto»). Una fecha de vencimiento de hoy o pasada se rechaza; una cantidad de 0 también.
- [ ] Al guardar, el detalle muestra cada producto «En inventario» con su bodega y su vigencia.
- [ ] Edite la donación: cambie una cantidad y quite un producto → el administrador ve en el kardex el **ajuste** y la **baja** «Retiro del donante».
- [ ] Como administrador, en *Inventario* la lista está ordenada por fecha de vencimiento, con filas amarillas (próximo a vencer) y rojas (vencido). Pruebe la búsqueda y los filtros.
- [ ] *Gestionar* un producto → **Ajustar cantidad** sin motivo → error. Con motivo → queda en el kardex con la cantidad anterior y la resultante.
- [ ] En un producto con una entrega pendiente, el botón **Retirar** aparece deshabilitado con el aviso «Tiene cantidades reservadas para entregas pendientes. Cancele antes esas entregas».
- [ ] **Anónimo:** abra la donación de `empresa@sysfood.local` → «Donante anónimo». *Ver identidad* muestra la empresa y en la bitácora aparece «Consulta de identidad de donante anónimo». Como beneficiario, en el catálogo esa donación sale como «Donante anónimo».
- [ ] **Vencimientos:** la «Leche entera UHT» de la demostración vence en 4 días → aparece como *Próximo a vencer* en el panel y el donante tiene la notificación. Ejecute `python manage.py actualizar_vencimientos` y verá el resumen.

## 5. Catálogo, carrito y solicitudes (Actividades 7 y 11)

Como `beneficiario@sysfood.local`:

- [ ] El catálogo solo muestra productos vigentes con existencia. Busque por nombre y filtre por categoría.
- [ ] Agregue más cantidad de la disponible → «La cantidad supera la disponible».
- [ ] Agregue 5 productos distintos y luego un sexto → «El carrito admite máximo 5 productos distintos».
- [ ] Quite un producto, vacíe el carrito y vuelva a llenarlo. **Enviar solicitud** → queda *Pendiente*, el carrito se vacía y el administrador recibe la notificación.
- [ ] Como administrador abra la solicitud: ve los datos del beneficiario, sus productos y la disponibilidad actual. **Rechazar** exige motivo.
- [ ] **Aprobar** con modalidad *Entrega a domicilio* (pide dirección) → se genera la entrega «En revisión». En el inventario esos productos muestran la cantidad **Reservada**. El donante recibe «Sus productos fueron reservados», sin datos del beneficiario.

## 6. Entregas y seguimiento (Actividades 8 y 14)

- [ ] En la entrega: **Pasar a «En bodega»** → **«En entrega»** → **«Entregado»**. En el último paso puede indicar una cantidad entregada menor: lo no entregado vuelve a estar disponible.
- [ ] El historial muestra cada cambio con el usuario y la fecha. El kardex muestra *Reserva* y *Entrega*.
- [ ] Cancelar exige motivo; al cancelar, lo reservado vuelve al inventario. Una entrega *Entregada* ya no se puede cancelar.
- [ ] Como beneficiario: *Seguimiento* → escriba el código → ve los pasos y el avance. Con el código de otra persona → «No encontramos una entrega suya con ese código».

## 7. Notificaciones, panel y reportes (Actividades 13 y 15)

- [ ] La campana muestra las notificaciones sin leer. *Marcar todas como leídas* las limpia.
- [ ] Cada rol tiene su panel: el del administrador con indicadores y gráficos, el del donante con sus donaciones y cantidades, y el del beneficiario con su verificación, solicitudes y entregas.
- [ ] *Sistema › Reportes*: los 5 reportes, con filtros por fechas, estado, categoría, donante y bodega. **PDF** y **Excel** se descargan con tabla y gráfico.
- [ ] *Sistema › Trazabilidad*: kardex, historial de entregas y bitácora, con filtros por fecha, usuario y registro. No hay botones para editar ni eliminar.

## 8. Usabilidad y compatibilidad (Actividad 20)

- [ ] Abra el sistema en Chrome, Edge y Firefox.
- [ ] Con las herramientas de desarrollador (F12 → modo dispositivo) o en un celular real: el menú se convierte en botón ☰, las tablas se desplazan horizontalmente y los formularios ocupan todo el ancho.

- [ ] **Modo oscuro:** el botón de sol/luna de la barra cambia el tema; al recargar la página se conserva.
- [ ] **Animaciones:** al abrir el panel del administrador los números suben desde 0, las tarjetas aparecen escalonadas y los gráficos se dibujan. Con «reducir movimiento» activado en el sistema operativo todo aparece de inmediato.

## 9. Respaldo (Actividad 22)

- [ ] `python manage.py respaldo` → crea `backups/sysfood_<fecha>.zip`.
- [ ] Registre una donación nueva y luego ejecute `python manage.py restaurar backups/sysfood_<fecha>.zip` (escriba `SI`) → la donación nueva desaparece y todo vuelve al estado del respaldo, incluidos los documentos.

## 10. Puntaje y grupos de necesidad (mejora 1)

- [ ] Como administrador abra *Usuarios › María Rodríguez*: la tarjeta **Puntaje de necesidad** muestra el puntaje, el grupo con su color y una barra por criterio con sus puntos. El enlace **¿Cómo se calcula?** abre la ayuda con la fórmula, los pesos vigentes, tres ejemplos y la nota de equidad.
- [ ] *Editar* el beneficiario y cambie el estrato a 6 → el puntaje baja. En *Trazabilidad › Bitácora*, filtre por «Cálculo automático de puntaje»: aparece el puntaje anterior, el nuevo, el motivo «Cambio en los datos del beneficiario» y el desglose.
- [ ] *Sistema › Parámetros › Grupos de necesidad*: cambie `grupos_necesidad` a `Urgente|50|#b42318; Normal|0|#2b8a3e`. Al guardar, un aviso indica cuántos beneficiarios se recalcularon y la bitácora registra los cambios de grupo («Clasificación automática por grupo»). Pruebe un valor sin grupo de mínimo 0 → error.
- [ ] *Usuarios*: filtre por grupo y ordene por la columna **Necesidad**. *Solicitudes*: las pendientes salen ordenadas por puntaje (mayor primero) y se pueden filtrar por grupo.
- [ ] *Sistema › Reportes › Beneficiarios por grupo de necesidad*: gráfico con los colores de cada grupo; exporte a PDF y Excel.
- [ ] *Sistema › Tareas automáticas* → **Ejecutar ahora** en «Recálculo nocturno de puntajes». También: `python manage.py ejecutar_tareas --listar`.

## 11. Pruebas automáticas

```bash
python manage.py test
```

Deben pasar todas las pruebas (`OK`).
