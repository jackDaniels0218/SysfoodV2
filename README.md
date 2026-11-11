# SysFood V2

Sistema de información web para la gestión de donaciones de alimentos.
Conecta a **donantes** (personas naturales o jurídicas, públicos o anónimos) con **beneficiarios** en condición de vulnerabilidad, bajo la supervisión de un **administrador**.

- **Tecnología:** Python 3.10+ · Django 5.2 · MySQL 8 · Bootstrap 5 · Chart.js
- **Funciona en:** Windows, Linux y macOS · Chrome, Edge y Firefox · computador, tableta y celular
- **Interfaz:** en español

![Página de bienvenida](docs/capturas/bienvenida.png)

| Panel del administrador (modo claro) | Panel del administrador (modo oscuro) |
| --- | --- |
| ![Panel claro](docs/capturas/panel_admin.png) | ![Panel oscuro](docs/capturas/panel_admin_oscuro.png) |

### Diseño de la interfaz

Estilo propio «Cosecha»: crema cálido, verde bosque y naranja cítrico, con tipografía editorial (Fraunces y Plus Jakarta Sans, incluidas en el proyecto: no necesita internet).

- **Modo claro y oscuro** con un botón en la barra; recuerda su elección y respeta la preferencia del sistema.
- **Animaciones:** fondo aurora en movimiento, barra de navegación de cristal flotante, aparición escalonada de las tarjetas al hacer scroll, contadores que suben hasta su valor, gráficos que se dibujan, brillo que sigue al cursor, ondas en los botones, avisos que entran y se retiran solos, y pasos de entrega con pulso.
- **Accesible:** si el sistema operativo tiene activado «reducir movimiento», las animaciones se desactivan.
- Funciona en computador, tableta y celular.

---

## Inicio rápido (sin configurar nada)

Elija **una** de estas dos opciones. Las dos crean la base de datos, cargan los datos de demostración y dejan el sistema en **http://localhost:8000**.
Para ingresar, use `admin@sysfood.local` con la contraseña `Sysfood2025*` (más cuentas en la [sección 2](#2-cuentas-de-demostración)).

### Opción A: Docker (recomendada, incluye PostgreSQL)

Solo necesita [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado y abierto.

```bash
git clone https://github.com/jackDaniels0218/SysfoodV2.git
cd SysfoodV2
docker compose up
```

La primera vez tarda unos minutos mientras descarga PostgreSQL y prepara todo. Cuando aparezca `SysFood listo en el puerto 8000`, abra http://localhost:8000.
Para detenerlo use `Ctrl+C`; para volver a iniciarlo, `docker compose up`. Los datos se conservan. Si quiere empezar desde cero, ejecute `docker compose down -v`.

### Opción B: Sin Docker (solo Python)

Solo necesita [Python 3.10 o superior](https://www.python.org/downloads/). En Windows marque «Add Python to PATH» al instalarlo.

- **Windows:** haga doble clic en **`iniciar.bat`**.
- **Linux / macOS:** ejecute `./iniciar.sh` en una terminal.

La primera vez instala las dependencias; las siguientes solo arranca. Esta opción usa **SQLite**, una base de datos en un archivo, para no exigir un servidor de base de datos. Para trabajar con PostgreSQL, siga la instalación completa.

---

## 1. Instalación completa (con PostgreSQL local)

PostgreSQL es el motor recomendado: es el mismo que usa el despliegue en Render (sección 9). El proyecto también funciona con MySQL 8 (`DB_ENGINE=mysql`) y con SQLite para pruebas rápidas (`DB_ENGINE=sqlite`).

### Requisitos

| Programa | Versión | Descarga |
| --- | --- | --- |
| Python | 3.10 o superior | https://www.python.org/downloads/ (en Windows marque «Add Python to PATH») |
| PostgreSQL | 14 o superior | https://www.postgresql.org/download/ (guarde la contraseña del usuario `postgres`) |
| Git | cualquiera | https://git-scm.com/downloads |

### Paso a paso

**1. Clonar el repositorio**

```bash
git clone https://github.com/jackDaniels0218/SysfoodV2.git
cd SysfoodV2
```

**2. Crear la base de datos.** Con pgAdmin o con la consola `psql -U postgres`:

```sql
CREATE DATABASE sysfood ENCODING 'UTF8' TEMPLATE template0;
```

En Windows, `psql` está en `C:\Program Files\PostgreSQL\<versión>\bin\psql.exe`.

**3. Crear el entorno virtual e instalar dependencias**

Windows (PowerShell o CMD):

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

**4. Completar el archivo `.env`.** Escriba la contraseña de PostgreSQL en `DB_PASSWORD`. Los demás valores sirven tal como vienen para una instalación local.

```ini
DB_ENGINE=postgresql
DB_NAME=sysfood
DB_USER=postgres
DB_PASSWORD=la-contraseña-de-postgres
DB_HOST=127.0.0.1
DB_PORT=5432
```

**5. Crear las tablas y cargar los datos de demostración**

```bash
python manage.py migrate
python manage.py cargar_demo
```

**6. Iniciar el servidor**

```bash
python manage.py runserver
```

Abra **http://127.0.0.1:8000** en el navegador.

> Para las pruebas automáticas, el usuario de PostgreSQL debe poder crear la base `test_sysfood`. El usuario `postgres` ya puede hacerlo.

---

## 2. Cuentas de demostración

Todas usan la contraseña **`Sysfood2025*`**.

| Correo | Rol | Qué tiene |
| --- | --- | --- |
| `admin@sysfood.local` | Administrador | Acceso a todo |
| `donante@sysfood.local` | Donante (persona natural) | Una donación pública con 3 productos (uno próximo a vencer) |
| `empresa@sysfood.local` | Donante (persona jurídica) | Una donación **anónima** con 3 productos |
| `beneficiario@sysfood.local` | Beneficiario **verificado** | Una solicitud pendiente |
| `nuevo@sysfood.local` | Beneficiario **en revisión** | Documentos cargados esperando aprobación |
| `vecino1@sysfood.local` … `vecino12@sysfood.local` | Beneficiarios ubicados en barrios de Facatativá | Alimentan el mapa de calor; varios con solicitudes |

Si solo quiere el administrador, sin datos de prueba: `python manage.py cargar_demo --solo-admin`.

---

## 3. Cómo probarlo paso a paso

La guía completa, requerimiento por requerimiento, está en **[docs/GUIA_DE_PRUEBAS.md](docs/GUIA_DE_PRUEBAS.md)**. Este es el recorrido principal (unos 10 minutos):

1. **Donante:** ingrese como `donante@sysfood.local` → **Donar** → agregue dos productos con «Agregar otro producto» → **Guardar**. Los productos entran solos al inventario.
2. **Registro de beneficiario:** cierre sesión → **Registrarse** → elija «Beneficiario» → llene sus datos y acepte la política de datos. Quedará en estado *Pendiente*.
3. **Documentos:** cargue el documento de identidad, el certificado de Sisbén y el soporte de residencia (PDF, JPG o PNG de máximo 5 MB; en el celular puede usar **Tomar foto con la cámara**). La cuenta pasa a *En revisión*. Mientras tanto el catálogo está bloqueado.
4. **Administrador:** ingrese como `admin@sysfood.local` → **Usuarios › Documentos por revisar** → apruebe los tres documentos. El beneficiario queda *Verificado* y recibe una notificación.
5. **Carrito:** ingrese con el beneficiario → **Catálogo** → agregue productos (máximo 5 distintos y sin superar lo disponible) → **Carrito › Enviar solicitud**.
6. **Aprobación:** como administrador → **Solicitudes** → abra la solicitud → elija la modalidad (recogida o domicilio) → **Aprobar**. Se reservan las cantidades y se genera la entrega con un código `SF-XXXXXXXX`.
7. **Entrega:** en la entrega pulse **Pasar a «En bodega»**, luego **«En entrega»** y luego **«Entregado»**. Al final se descuenta definitivamente del inventario.
8. **Seguimiento:** como beneficiario → **Seguimiento** → escriba el código y verá el avance.
9. **Trazabilidad y reportes:** como administrador → **Sistema › Trazabilidad** (kardex, historial de entregas y bitácora) y **Sistema › Reportes** (gráficos y exportación a **PDF** y **Excel**).
10. **Donante anónimo:** como administrador abra la donación de `empresa@sysfood.local`: aparece «Donante anónimo». El botón **Ver identidad** la muestra y deja el registro en la bitácora.

---

## 3.1 ¿Cómo se calcula el puntaje de necesidad?

Cada beneficiario tiene un **puntaje de 0 a 100** que el sistema calcula solo. Es una **suma ponderada** de seis criterios: un algoritmo transparente que cualquiera puede repetir con lápiz y papel. El mismo texto, con los parámetros vigentes y ejemplos calculados en vivo, está dentro del sistema en **Usuarios › (beneficiario) › ¿Cómo se calcula?** (`/cuentas/ayuda/puntaje/`).

> **Nota de equidad.** El puntaje **apoya** la decisión del administrador y **no la reemplaza**. Sirve para ordenar la atención y detectar casos urgentes, pero cada solicitud la revisa una persona, que puede aprobar o rechazar con su criterio y deja el motivo. Solo se usan datos que el beneficiario declaró y documentó; nunca sexo, etnia, religión ni opiniones.

**Fórmula**

```
puntaje = Σ (peso_i × valor_i) ÷ Σ peso_i          valor_i ∈ [0, 100]
puntos del criterio i = peso_i × valor_i ÷ Σ peso_i   (los puntos suman el puntaje)
```

| Criterio | Peso por defecto | Cómo se convierte en 0–100 (parámetro) |
| --- | --- | --- |
| Nivel de Sisbén | 25 | A: 100, B: 70, C: 35, D: 10, no registrado: 50 (`puntaje_escala_sisben`) |
| Estrato social | 20 | 1: 100, 2: 80, 3: 50, 4: 25, 5 y 6: 0 (`puntaje_escala_estrato`) |
| Personas en el hogar | 20 | personas ÷ 8 × 100, con tope en 100 (`puntaje_personas_tope`) |
| Discapacidad | 15 | No: 0; sí con certificado aprobado: 100; sí sin certificado aprobado: 50 (`puntaje_discapacidad_sin_soporte`) |
| Solicitudes recientes | 5 | solicitudes de los últimos 90 días ÷ 4 × 100, sin contar canceladas (necesidad activa) |
| Tiempo sin recibir ayuda | 15 | días desde la última entrega ÷ 60 × 100; si nunca ha recibido, 100 (equilibra para no concentrar la ayuda) |

Los pesos suman 100, pero no es obligatorio: el sistema divide por su suma. Todos los pesos y escalas se editan en **Sistema › Parámetros › Puntaje de necesidad**.

**Ejemplos (parámetros por defecto)**

| Caso | Sisbén | Estrato | Personas | Discapacidad | Solicitudes | Sin ayuda | Puntaje | Grupo |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Hogar de 6 personas, Sisbén A, estrato 1, discapacidad certificada, 1 solicitud, nunca ha recibido | 25×100 | 20×100 | 20×75 | 15×100 | 5×25 | 15×100 | (2500+2000+1500+1500+125+1500) ÷ 100 = **91,25** | Prioridad crítica |
| Familia de 4, Sisbén C, estrato 2, 2 solicitudes, última entrega hace 20 días | 25×35 | 20×80 | 20×50 | 15×0 | 5×50 | 15×33,3 | (875+1600+1000+0+250+500) ÷ 100 = **42,25** | Prioridad media |
| Persona sola, Sisbén D, estrato 3, 3 solicitudes, atendida hace 5 días | 25×10 | 20×50 | 20×12,5 | 15×0 | 5×75 | 15×8,3 | (250+1000+250+0+375+125) ÷ 100 = **20,0** | Prioridad baja |

**Grupos.** Según el puntaje, el beneficiario queda en un grupo (`grupos_necesidad`, formato `Nombre|mínimo|#color`): *Prioridad crítica* desde 75, *Alta* desde 55, *Media* desde 35 y *Baja* desde 0, cada uno con su color. El grupo se reasigna solo cuando cambia el puntaje. Se usa para:

- filtrar en **Usuarios** y en **Solicitudes**, y ordenar la lista de usuarios por necesidad;
- ordenar las **solicitudes pendientes**: mayor puntaje primero y, a igual puntaje, la más antigua (`solicitudes_orden_prioridad`);
- el reporte **Beneficiarios por grupo de necesidad**, exportable a PDF y Excel.

**Cuándo se recalcula.** Al registrarse el beneficiario; al cambiar sus datos o sus documentos (por ejemplo, cuando se aprueba el certificado de discapacidad); al enviar una solicitud o recibir una entrega; cada noche con la tarea *Recálculo nocturno de puntajes*; y al cambiar cualquier peso, escala o grupo en Parámetros. Cada cambio de puntaje queda en la **bitácora** («Cálculo automático de puntaje») con el valor anterior, el nuevo, el motivo, la fecha y el desglose. Cada cambio de grupo queda como «Clasificación automática por grupo».

---

## 3.2 Mapa de beneficiarios y mapa de calor

En el **panel del administrador** hay un mapa de calor y en **Sistema › Mapa de beneficiarios** (`/reportes/mapa/`) está el mapa completo:

- **Geocodificación automática.** Al registrarse un beneficiario o cambiar su dirección, el sistema obtiene sus coordenadas sin que nadie intervenga: usa [Nominatim](https://nominatim.org/) (OpenStreetMap, gratuito) en segundo plano y guarda cada dirección en una **caché** (`geo_cache`) para no repetir consultas. Respeta la política de uso del servicio: una consulta por segundo y un agente de usuario propio. Solo envía la dirección.
- **Si falla**, la tarea horaria *Geocodificación de direcciones* reintenta. Tras `geo_max_intentos` intentos el caso queda **en revisión**, los administradores reciben un aviso y el beneficiario aparece en «Direcciones por revisar». El administrador puede corregir la dirección, pulsar **Ubicar de nuevo** o hacer clic en el mapa para fijar el punto a mano.
- **Capas conmutables:** marcadores agrupados (clusters) con el color del grupo de necesidad, y mapa de calor.
- **Calor ponderado por la concurrencia de necesidad:** `peso = (60·puntaje/100 + 25·min(solicitudes/5, 1) + 15·min(personas/8, 1)) ÷ 100`. Pesos y topes en *Parámetros › Mapa y geocodificación*.
- **Filtros:** grupo de necesidad, estado de verificación y fechas. Las fechas cuentan solo las solicitudes enviadas en ese periodo, y con un rango solo aparecen los beneficiarios que solicitaron en él.
- **Librerías locales:** Leaflet 1.9.4, Leaflet.markercluster 1.5.3 y Leaflet.heat 0.2.0 en `static/vendor/leaflet`. Las teselas del mapa base vienen de OpenStreetMap (`mapa_tiles_url`), así que necesitan internet; sin conexión los puntos se siguen viendo sobre un fondo vacío.

**Privacidad.** Solo el administrador ve el mapa: donantes y beneficiarios reciben *Acceso denegado*, y los datos se sirven con `Cache-Control: private, no-store`. Cada consulta queda en la bitácora («Consulta del mapa de beneficiarios»), con el número de puntos y los filtros. Las exportaciones (**GeoJSON** y **CSV**) **no incluyen nombres, documentos ni enlaces**. Además, cada punto se **desplaza al azar** hasta `mapa_desplazamiento_m` metros (300 por defecto), de manera uniforme dentro de un círculo. Cada exportación también queda en la bitácora.

---

## 3.3 Carga y verificación automática de documentos

**Carga (celular y escritorio).** En *Documentos* el beneficiario arrastra y suelta el archivo, lo elige o toma una foto con la cámara trasera. Antes de enviar ve una **vista previa** y el sistema valida el formato y el tamaño. Las fotos grandes del celular se reducen solas a JPEG de máximo 2.200 px, porque antes superaban los 5 MB y se rechazaban. Durante el envío hay una **barra de progreso** y al final un mensaje claro con lo que decidió el sistema. Un indicador muestra el avance: «Paso 1 de 3: cargar documentos», con cuántos están cargados y aprobados. Sin JavaScript el formulario sigue funcionando como antes.

Correcciones al flujo anterior: la cámara copiaba el archivo con `DataTransfer`, que falla en Safari para iOS antiguos. Ahora la foto se envía directamente, y sin JavaScript la cámara también funciona. Las imágenes dañadas que solo tenían la firma correcta ahora se rechazan.

**Calidad de imagen (inmediata).** Al recibir una foto, el sistema mide la **nitidez** (magnitud del laplaciano en el percentil 99,8, de 0 a 256), la resolución, el brillo y el contraste. Si la imagen está borrosa, es muy pequeña o está oscura, la rechaza al instante y pide repetirla con el motivo, por ejemplo: «la imagen está borrosa; sostenga el celular firme y enfoque el documento». Esta revisión solo usa Pillow y funciona siempre.

**Lectura con OCR y semáforo.** Si Tesseract está disponible (incluido en Docker con `tesseract-ocr-spa` y `poppler-utils`), el sistema lee el documento (las dos primeras páginas en los PDF) y compara lo leído con los datos registrados:

| Documento | Qué compara (peso) |
| --- | --- |
| Identidad | número de documento (3), nombres y apellidos (2), fecha de expedición (1) |
| Sisbén | número (3), nombres (2), grupo de Sisbén A/B/C/D (1) |
| Residencia | nombres (2), dirección (2), estrato (1) |
| Discapacidad | número (3), nombres (2) |

Las búsquedas toleran errores típicos del OCR: puntos en el número, letras confundidas y meses escritos en texto.

```
confianza = 100 × Σ(peso × coincidencia) ÷ Σ peso × (0,7 + 0,3 × legibilidad_OCR ÷ 100)
```

| Semáforo | Condición (parámetros) | Acción automática |
| --- | --- | --- |
| 🟢 Alta | confianza ≥ `ocr_umbral_alto` (85) | **Pre-aprobado**: se aprueba, se marca como «Decisión automática» y se avisa al titular |
| 🟡 Media | entre los umbrales | Queda en la **cola del administrador**, primero que los demás, con las discrepancias resaltadas |
| 🔴 Baja o ilegible | confianza < `ocr_umbral_bajo` (40), o sin texto legible | **Rechazado** con el motivo (qué no coincidió o por qué es ilegible); el titular puede recargarlo |

En *Documentos por revisar* el administrador ve, junto a la imagen, **lo que el sistema leyó**: la confianza, una tabla con lo registrado, lo leído y si coincide, la calidad y el texto completo. Puede **revertir** cualquier decisión automática, también una pre-aprobación. Debajo aparecen las decisiones automáticas de los últimos 30 días para auditarlas. El resultado y la confianza se guardan en el documento, y cada decisión queda en la bitácora («Verificación automática de documento»).

**El flujo manual siempre funciona.** Si el OCR está desactivado (`ocr_activo`), Tesseract no está instalado, la lectura falla o el resultado no es concluyente, el documento queda *Cargado* y el administrador aprueba o rechaza como siempre. La tarea horaria *Lectura automática de documentos* reintenta las lecturas fallidas, hasta 3 intentos. Los documentos de donantes se revisan siempre a mano.

> Sin Docker: instale Tesseract ([Windows](https://github.com/UB-Mannheim/tesseract/wiki) o `apt install tesseract-ocr tesseract-ocr-spa poppler-utils`) para activar la lectura. Sin él, todo funciona con revisión manual.

## 3.4 Asistente de ayuda (chat)

En todas las páginas, también antes de ingresar, aparece un botón verde abajo a la derecha (atajo **Alt+A**) que abre el asistente. Responde preguntas sobre cómo usar SysFood y **sabe dónde está el usuario**: ofrece preguntas sugeridas según la página y el rol. Si el usuario ingresó, también responde sobre **sus propios datos**: el estado de sus solicitudes, entregas, documentos, donaciones o su puntaje.

**Cómo decide la respuesta** (`asistente/motor.py`):

1. **Privacidad primero.** Si la pregunta pide datos de otras personas, listados de usuarios o la identidad de un donante anónimo, se niega siempre, también en el modo con Claude y también para el administrador.
2. **Reglas:** saludos, «hablar con una persona» y «¿qué hago en esta página?».
3. **Datos propios:** solo consulta los registros del usuario que pregunta.
4. **Búsqueda** en la base de conocimiento, con similitud ponderada por la rareza de cada palabra y tolerante a plurales y conjugaciones. Si la similitud no llega a `chat_umbral` (35), **ofrece enviar la pregunta al administrador**.

**Base de conocimiento generada sola** (`asistente/conocimiento.py`): artículos de uso con los valores **vigentes** de los parámetros (si cambia el máximo de productos, la respuesta cambia), una ficha por cada parámetro (los públicos para todos y todos para el administrador) y la ayuda de cada pantalla. Cada artículo dice qué roles pueden verlo.

**Escribir al administrador.** Cuando no sabe, o si la respuesta no le sirvió (👎), el usuario envía su consulta. A un visitante se le pide un correo o teléfono para responderle. Los administradores reciben una notificación y un correo, y la acción queda en la bitácora («Consulta del asistente enviada al administrador»). En **Sistema › Consultas del asistente** el administrador ve indicadores de 30 días (consultas, sin respuesta, enviadas, calificaciones) y filtra las pendientes, las que no tuvieron respuesta o las que no les sirvieron, para mejorar los artículos.

**Datos mínimos.** Antes de guardar una pregunta se enmascaran los números largos y los correos. Las consultas se borran solas después de `chat_retencion_dias` (180) con la tarea diaria `limpieza_chat`. Hay un límite de `chat_max_por_hora` preguntas por sesión.

**Modo opcional con la API de Claude.** Defina `ANTHROPIC_API_KEY` en `.env` (y opcionalmente `CHAT_CLAUDE_MODELO`, por defecto `claude-opus-5-5`), y ponga `chat_modo = claude` en *Parámetros › Asistente de ayuda*. Claude redacta la respuesta usando **solo** los artículos encontrados y el contexto de la página. Las reglas de privacidad y los datos propios se siguen resolviendo sin Claude. Si la API falla, no hay clave o se niega, el asistente responde con la búsqueda. El panel muestra qué modo está activo.

**WhatsApp (opcional, sin probar con credenciales reales).** El webhook `/asistente/whatsapp/` acepta dos proveedores. Por WhatsApp el asistente responde como a un visitante: el teléfono no se asocia a ninguna cuenta, así que nunca entrega datos personales.

| Proveedor | Variables de entorno | Configuración en el proveedor |
| --- | --- | --- |
| WhatsApp Cloud API (Meta) | `WHATSAPP_PROVEEDOR=meta`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID` | URL de devolución `https://su-dominio/asistente/whatsapp/`, token de verificación igual a `WHATSAPP_VERIFY_TOKEN`, suscripción a `messages` |
| Twilio | `WHATSAPP_PROVEEDOR=twilio`, `TWILIO_AUTH_TOKEN` | «When a message comes in»: `https://su-dominio/asistente/whatsapp/` (POST) |

Se verifican las firmas de ambos proveedores (`X-Hub-Signature-256` y `X-Twilio-Signature`), y cualquier mensaje sin firma válida se rechaza. Las pruebas automáticas cubren la verificación del webhook, las firmas y el formato de los mensajes con datos simulados. **No se probó contra Meta ni Twilio reales**, porque eso requiere cuentas y un dominio público con HTTPS.

## 3.5 Inventario con cantidades coherentes

**Unidades contables y divisibles.** Las unidades de peso y volumen (`unidades_divisibles`: kilogramos, gramos, libras, litros y mililitros) admiten hasta dos decimales. Las demás (latas, cajas, unidades, paquetes, bolsas) **solo admiten enteros**: no se pueden registrar 24,5 latas. La regla se aplica en tres niveles:

1. **Formulario:** al elegir la unidad, el campo de cantidad cambia su paso a 1 o a 0,01 y avisa antes de enviar.
2. **Servidor:** se valida al donar, al editar una donación, en los ajustes de inventario, en el carrito y la solicitud, y en la cantidad entregada. El mensaje propone el entero más cercano: «“latas” se cuenta en unidades completas: escriba 24 o 25, no 24,5».
3. **Base de datos:** cada producto guarda si su unidad era divisible al registrarse (`dd_divisible`, `inv_divisible`), y las restricciones `CHECK` `dd_contable_entero` e `inv_contable_entero` rechazan decimales en los contables.

**Formato.** Las cantidades se muestran según su unidad: «50 kg», «24 latas», «1 lata», «2,5 L», «1.500 g». Las abreviaturas se configuran en `unidades_abreviaturas`. El formato se usa en el inventario, el catálogo, el carrito, las solicitudes, las entregas, los paneles y los reportes.

**Datos anteriores.** La migración marca cada registro según su unidad. Si un registro contable ya tenía decimales, lo conserva sin perder datos y lo reporta: `python manage.py revisar_cantidades` lista esos registros, y el panel de inventario muestra el indicador «Cantidades por revisar» con un filtro para corregirlos con un ajuste.

**Panel de inventario rediseñado:**

- **Indicadores** que filtran al pulsarlos: disponibles, próximos a vencer, vencidos por retirar, con reservas y cantidades por revisar.
- **Alerta de vencimientos** con los cinco productos que vencen primero, su cantidad, bodega y días restantes.
- Vista en **tabla o tarjetas**; la elección se recuerda.
- **Ajuste rápido** desde la lista, en una ventana con la cantidad actual y el motivo. Respeta la regla de la unidad y vuelve a la misma lista.
- **Filtros guardados:** cada usuario guarda con un nombre la combinación de filtros actual y la vuelve a aplicar con un clic (modelo `FiltroGuardado`, reutilizable en otras listas).
- **Estados vacíos útiles**, que distinguen un inventario vacío de unos filtros que no encuentran nada.

## 3.6 Reportes y estadísticas

Todas las estadísticas se declaran en un **registro único** (`reportes/consultas.py › ESTADISTICAS`) con su título, grupo, descripción, filtros admitidos y función. De él salen la página de reportes, el catálogo **Todas las estadísticas**, las exportaciones y los envíos por correo. El inventario completo está en **[docs/ESTADISTICAS.md](docs/ESTADISTICAS.md)**.

- **Diez estadísticas**, cuatro de ellas nuevas: *Beneficiarios por zona* (la versión en tabla del mapa de calor), *Verificaciones automáticas y manuales*, *Tiempo promedio de verificación* y *Consultas del asistente de ayuda*. La distribución por grupo de necesidad ya existía desde la mejora 1.
- **Filtros según cada estadística:** solo se muestran y aceptan los filtros que la estadística admite. Sin fechas elegidas se aplica `reportes_dias_por_defecto` (0 = todo el historial).
- **Exportación** a PDF, Excel, **CSV** (separador configurable) y cada gráfico como imagen **PNG**. Cada exportación queda en la bitácora.
- **Envíos programados por correo:** desde cualquier reporte, «Programar envío» con frecuencia diaria, semanal o mensual, formato y destinatarios. Puede cubrir solo el último periodo. La tarea horaria `reportes_programados` envía desde `reportes_hora_envio`. En *Envíos programados* se puede enviar ahora, pausar o eliminar.

## 3.7 Usabilidad

Antes de cambiar nada se auditaron los flujos principales: **[docs/AUDITORIA_USABILIDAD.md](docs/AUDITORIA_USABILIDAD.md)** registra cada problema y su corrección. Resumen:

- **Búsqueda global** (<kbd>/</kbd> o <kbd>Ctrl</kbd>+<kbd>K</kbd>, o la lupa de la barra): páginas, personas, productos, `#solicitud` y códigos de entrega. Cada rol busca solo en lo que puede ver, y la búsqueda nunca revela a un donante anónimo.
- **Atajos de teclado:** <kbd>?</kbd> muestra la lista; <kbd>g</kbd> + letra lleva a cada sección; <kbd>t</kbd> cambia el tema.
- **Guía «Primeros pasos»** en el panel de cada rol, con el avance y el siguiente paso calculados con los datos reales.
- **Asistente de donación en tres pasos**, con resumen antes de guardar.
- **Confirmaciones** en una ventana propia y accesible, y **deshacer** al quitar productos del carrito o vaciarlo.
- **Estados vacíos útiles**, que distinguen «aún no hay nada» de «los filtros no encuentran nada» y ofrecen la siguiente acción.
- **Esqueletos de carga** en gráficos y búsqueda.
- **Accesibilidad:** «Saltar al contenido», foco visible, página actual marcada, avisos anunciados por lectores de pantalla y filtros con etiqueta. Todo respeta el modo oscuro y «reducir movimiento».

---

## 4. Pruebas automáticas

El proyecto incluye **256 pruebas** que cubren los 22 requerimientos y las mejoras: funcionales, seguridad, rendimiento, integridad y respaldo.

```bash
python manage.py test
```

Resultado esperado: `Ran 256 tests ... OK`.

Además se verificó:

- **Navegador real (Chrome headless):** recorrido completo de registro → donación → documentos → aprobación → carrito → solicitud → entrega → seguimiento → reportes PDF/Excel, en escritorio y en celular (390 px), sin errores de JavaScript.
- **Carga:** 100 usuarios concurrentes con `waitress`: 1.101 peticiones, 0 errores, mediana 1,1 s y percentil 95 de 1,3 s.
- **Entradas inválidas:** se enviaron valores corruptos a todos los filtros y formularios sin ningún error 500.

---

## 5. Tareas programadas

### Procesos automáticos

El sistema decide y actúa solo. Todas las tareas están en un único registro (`core/tareas.py`) y se ven en **Sistema › Tareas automáticas**, con su última ejecución, su resultado y un botón **Ejecutar ahora**:

| Tarea | Frecuencia | Qué hace |
| --- | --- | --- |
| `control_vencimientos` | diaria | Vigencia del inventario, documentos vencidos y avisos (Actividad 12) |
| `recalculo_puntajes` | diaria (nocturna) | Recalcula el puntaje y el grupo de todos los beneficiarios |
| `geocodificacion` | horaria | Ubica a los beneficiarios pendientes y reintenta los fallidos |
| `verificacion_documentos` | horaria | Lee con OCR los documentos que quedaron sin leer y aplica el semáforo |
| `reportes_programados` | horaria | Envía por correo los reportes programados que ya cumplieron su periodo |
| `limpieza_chat` | diaria | Borra las consultas del asistente más antiguas que `chat_retencion_dias` |

Cada tarea corre **una sola vez por periodo**, aunque varias fuentes intenten lanzarla. Se ejecutan de tres formas:

1. **Docker:** el contenedor ejecuta `python manage.py ejecutar_tareas` cada hora. No hay que configurar nada.
2. **Sistema operativo** (recomendado sin Docker), cada hora:
   - **Linux / macOS** (`crontab -e`): `0 * * * * cd /ruta/SysfoodV2 && .venv/bin/python manage.py ejecutar_tareas`
   - **Windows:** Programador de tareas → Crear tarea → Desencadenador diario, repetir cada 1 hora → Programa: `C:\ruta\SysfoodV2\.venv\Scripts\python.exe`, Argumentos: `manage.py ejecutar_tareas`, Iniciar en: `C:\ruta\SysfoodV2`
3. **Respaldo:** si no se programó nada, el control de vencimientos corre con la primera visita del día y las demás tareas en segundo plano mientras alguien navega (`TAREAS_AUTOMATICAS=1`).

Opciones: `ejecutar_tareas --listar` muestra el estado; `--tarea recalculo_puntajes --forzar` ejecuta una sola aunque ya haya corrido. `actualizar_vencimientos` sigue funcionando como antes.

### Respaldo y restauración (Actividad 22)

```bash
python manage.py respaldo                          # crea backups/sysfood_AAAAMMDD_HHMMSS.zip (datos + documentos)
python manage.py restaurar backups/archivo.zip     # REEMPLAZA los datos actuales (pide confirmación)
```

Programe `respaldo` a diario de la misma forma que el control de vencimientos. La restauración está cubierta por una prueba automática (`RespaldoTests`).

---

## 6. Correo electrónico (SMTP)

Si `EMAIL_HOST` está vacío, los correos (notificaciones y recuperación de contraseña) se **muestran en la consola** donde corre el servidor. Así puede copiar el enlace de recuperación mientras prueba.

Para enviar correos reales, por ejemplo con Gmail (requiere una [contraseña de aplicación](https://myaccount.google.com/apppasswords)):

```ini
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=su_correo@gmail.com
EMAIL_HOST_PASSWORD=contraseña_de_aplicacion
EMAIL_USE_TLS=1
DEFAULT_FROM_EMAIL=SysFood <su_correo@gmail.com>
```

---

## 7. Puesta en producción (HTTPS)

1. En `.env`: `DJANGO_DEBUG=0`, una `DJANGO_SECRET_KEY` larga y aleatoria, `DJANGO_ALLOWED_HOSTS=su-dominio.com`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://su-dominio.com` y `DJANGO_HTTPS=1`. Esta última activa la redirección a HTTPS, las cookies seguras y HSTS.
2. `python manage.py collectstatic`
3. Servidor de aplicación (funciona en Windows y Linux): `waitress-serve --listen=127.0.0.1:8000 --threads=24 sysfood.wsgi:application`
4. Ponga delante un proxy con certificado TLS (Nginx, Caddy o IIS) que sirva `/static/` desde `staticfiles/` y reenvíe el resto a waitress con la cabecera `X-Forwarded-Proto`.
5. **Nunca** publique la carpeta `protegido/`: ahí están los documentos de validación. El sistema los entrega solo a su titular y al administrador.

---

## 8. Estructura del proyecto

```
sysfood/        Configuración de Django (settings, urls)
core/           Parámetros, notificaciones, bitácora, trazabilidad, control diario, respaldo
usuarios/       Usuarios, registro, autenticación, recuperación, documentos de validación
catalogo/       Categorías y bodegas
donaciones/     Donaciones y sus productos
inventario/     Inventario, kardex, ajustes, bajas y vencimientos
solicitudes/    Catálogo, carrito y solicitudes
entregas/       Entregas, estados, historial y seguimiento
reportes/       Paneles por rol, reportes, exportación PDF/Excel, mapa
asistente/      Asistente de ayuda (chat): motor, base de conocimiento, WhatsApp
templates/      Interfaz (Bootstrap 5)
static/         CSS, JS y librerías locales (Bootstrap, iconos, Chart.js)
protegido/      Documentos cargados (no público; excluido de Git)
backups/        Respaldos (excluido de Git)
docs/           Modelo de datos, trazabilidad de requerimientos y guía de pruebas
```

Modelo de datos y diagramas: **[docs/MODELO_DE_DATOS.md](docs/MODELO_DE_DATOS.md)**.
Inventario de estadísticas: **[docs/ESTADISTICAS.md](docs/ESTADISTICAS.md)**.
Auditoría de usabilidad: **[docs/AUDITORIA_USABILIDAD.md](docs/AUDITORIA_USABILIDAD.md)**.
Dónde quedó cada uno de los 22 requerimientos: **[docs/REQUERIMIENTOS.md](docs/REQUERIMIENTOS.md)**.

---

## 9. Despliegue en Render

El repositorio incluye **`render.yaml`**, que crea en un solo paso la base **PostgreSQL** y el **servicio web**. El servicio web se construye con Docker e incluye Tesseract para el OCR.

1. Suba el código a GitHub, que ya es este repositorio.
2. En [Render](https://dashboard.render.com), vaya a **New + › Blueprint**, elija el repositorio y pulse **Apply**.
3. Espere a que termine el despliegue (unos 5 a 8 minutos la primera vez). Al arrancar, el contenedor espera la base de datos, ejecuta `migrate` y carga la demostración (`CARGAR_DEMO=1`).
4. Abra `https://<nombre-del-servicio>.onrender.com`, ingrese con `admin@sysfood.local` / `Sysfood2025*` y **cambie esa contraseña de inmediato**.

**Qué configura `render.yaml`**

| Variable | Valor |
| --- | --- |
| `DATABASE_URL` | La conexión a la base `sysfood-db` (Render la entrega; tiene prioridad sobre `DB_*`) |
| `DJANGO_SECRET_KEY` | Generada por Render |
| `DJANGO_DEBUG` / `DJANGO_HTTPS` | `0` / `1`: modo producción, HTTPS obligatorio y cookies seguras |
| `CARGAR_DEMO` | `1` carga la demostración la primera vez; `0` crea solo el administrador |
| `EMAIL_*`, `ANTHROPIC_API_KEY` | Opcionales: se completan en el panel de Render |

El dominio de Render se autoriza solo, con `RENDER_EXTERNAL_HOSTNAME`, y se usa en los enlaces de los correos (`RENDER_EXTERNAL_URL`).

**Límites del plan gratuito**

- La base PostgreSQL gratuita **vence a los 30 días**. Para producción, cambie a un plan pago en `render.yaml` (`plan: basic-256mb`, por ejemplo).
- El servicio se **duerme** tras 15 minutos sin visitas y tarda unos segundos en despertar. Mientras duerme no corren las tareas automáticas: se ponen al día al despertar.
- El disco es **temporal**: los documentos cargados se pierden en cada despliegue. Con un plan pago, descomente el bloque `disk` de `render.yaml` para guardarlos en `/app/protegido`.

**Pasar los datos locales a Render.** Genere un respaldo con `python manage.py respaldo` y restáurelo en Render desde la consola *Shell* del servicio con `python manage.py restaurar <archivo.zip>`. También puede usar `pg_dump` y `pg_restore` con la *External Database URL* que muestra Render.

