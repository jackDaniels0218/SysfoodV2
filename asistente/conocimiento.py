"""Base de conocimiento del asistente.

Se arma sola en cada consulta a partir de tres fuentes, de modo que nunca queda
desactualizada:

1. ARTICULOS: respuestas redactadas sobre cómo usar el sistema. Los valores
   configurables se escriben como {clave_del_parametro} y se reemplazan por el
   valor vigente en Sistema › Parámetros.
2. PAGINAS: qué se hace en cada pantalla y para qué rol (también da la ayuda
   según la página donde está el usuario).
3. Los parámetros marcados como públicos: cada uno genera un artículo con su
   descripción y su valor actual.

Cada artículo indica qué roles pueden verlo. «publico» incluye a quien no ha
ingresado. Ningún artículo contiene datos de personas.
"""

from collections import namedtuple

from django.urls import NoReverseMatch, reverse

from core import parametros

Articulo = namedtuple("Articulo", "clave titulo texto palabras roles url")

PUBLICO, ADMIN, DONANTE, BENEFICIARIO = "publico", "administrador", "donante", "beneficiario"
TODOS = (PUBLICO, ADMIN, DONANTE, BENEFICIARIO)
CON_CUENTA = (ADMIN, DONANTE, BENEFICIARIO)


def _a(clave, titulo, texto, palabras="", roles=TODOS, url=""):
    return Articulo(clave, titulo, texto, palabras, tuple(roles), url)


ARTICULOS = [
    # --- Cuenta
    _a(
        "que_es",
        "¿Qué es SysFood?",
        "SysFood conecta a donantes de alimentos con beneficiarios en condición de vulnerabilidad. "
        "Los donantes registran lo que donan, el administrador lo recibe en bodega y los beneficiarios "
        "verificados lo solicitan desde el catálogo y siguen su entrega.",
        "sysfood sistema plataforma para que sirve funciona",
    ),
    _a(
        "registro",
        "Cómo crear una cuenta",
        "Pulse «Registrarse», elija si será donante o beneficiario, complete sus datos y acepte la "
        "política de tratamiento de datos. Luego ingrese con su correo y contraseña. La contraseña debe "
        "tener al menos 8 caracteres, con mayúsculas, minúsculas, números y un símbolo.",
        "registrarme registro crear cuenta inscribirme nuevo usuario contraseña requisitos",
        url="usuarios:registro",
    ),
    _a(
        "ingreso",
        "Cómo ingresar",
        "Pulse «Ingresar» y escriba su correo y contraseña. Después de {intentos_ingreso} intentos fallidos "
        "la cuenta se bloquea {minutos_bloqueo} minutos por seguridad.",
        "ingresar entrar login iniciar sesion bloqueada bloqueo intentos",
        url="usuarios:login",
    ),
    _a(
        "recuperar",
        "Olvidé mi contraseña",
        "En la pantalla de ingreso pulse «¿Olvidó su contraseña?» y escriba su correo. Le llegará un enlace "
        "para crear una nueva, válido por {vigencia_token_minutos} minutos.",
        "olvide contraseña clave recuperar restablecer cambiar perdi",
        url="usuarios:recuperar",
    ),
    _a(
        "datos_personales",
        "Actualizar mis datos",
        "En el menú de su nombre, «Mis datos», puede actualizar su teléfono, dirección y demás información. "
        "Si es beneficiario y cambia la dirección, el sistema la vuelve a ubicar en el mapa y recalcula su puntaje.",
        "actualizar cambiar mis datos perfil telefono direccion correo",
        CON_CUENTA,
        "usuarios:perfil",
    ),
    _a(
        "politica",
        "Tratamiento de datos personales",
        "SysFood trata sus datos según la Ley 1581 de 2012: solo se usan para gestionar las donaciones y "
        "entregas, los documentos se guardan en una carpeta protegida y solo el administrador los revisa. "
        "Los donantes anónimos nunca se muestran a otros usuarios.",
        "privacidad datos personales ley 1581 politica proteccion habeas data",
        url="core:politica_datos",
    ),
    _a(
        "tema",
        "Modo oscuro",
        "Use el botón del sol o la luna en la barra superior para cambiar entre modo claro y oscuro. El sistema "
        "recuerda su elección.",
        "modo oscuro claro tema colores noche",
    ),
    _a(
        "notificaciones",
        "Notificaciones",
        "La campana de la barra superior muestra los avisos del sistema: documentos revisados, solicitudes "
        "aprobadas, entregas en camino y vencimientos. También llegan a su correo.",
        "notificaciones avisos campana correo alertas mensajes",
        CON_CUENTA,
        "core:notificaciones",
    ),
    # --- Beneficiarios
    _a(
        "documentos_requeridos",
        "Documentos que debe cargar un beneficiario",
        "Para verificar su cuenta cargue: documento de identidad, certificado de Sisbén y soporte de residencia o "
        "estrato. Si declaró discapacidad, también el certificado de discapacidad. Formatos permitidos: "
        "{formatos_permitidos}; tamaño máximo {tam_max_archivo_mb} MB por archivo.",
        "documentos requisitos cargar subir cedula sisben residencia estrato discapacidad certificado verificar cuenta",
        (PUBLICO, BENEFICIARIO, ADMIN),
        "usuarios:documentos",
    ),
    _a(
        "cargar_documento",
        "Cómo cargar un documento o una foto",
        "En «Documentos» elija el tipo, arrastre el archivo o pulse «Tomar foto con la cámara» desde el celular. "
        "Verá una vista previa antes de enviar. Las fotos grandes se reducen solas. Si la foto sale borrosa u "
        "oscura el sistema le pide repetirla de inmediato: apoye el documento en una mesa con buena luz.",
        "cargar subir foto camara celular archivo borrosa error documento no carga pdf imagen",
        (BENEFICIARIO, DONANTE),
        "usuarios:documentos",
    ),
    _a(
        "verificacion",
        "Cuánto tarda la verificación",
        "Al cargar un documento el sistema lo lee automáticamente y lo compara con sus datos. Si todo coincide "
        "queda aprobado al instante; si hay dudas lo revisa el administrador, normalmente en uno o dos días "
        "hábiles. Recibirá una notificación con el resultado y, si se rechaza, el motivo para corregirlo.",
        "verificacion verificado tarda cuanto demora aprobado rechazado revision cuenta pendiente",
        (BENEFICIARIO, PUBLICO),
        "usuarios:documentos",
    ),
    _a(
        "rechazo_documento",
        "Me rechazaron un documento",
        "Lea el motivo en «Documentos» o en la notificación, corrija lo indicado (por ejemplo, una foto más "
        "nítida o un documento vigente) y vuelva a cargarlo. Puede reemplazarlo las veces que necesite.",
        "rechazado rechazaron documento motivo corregir volver cargar",
        (BENEFICIARIO, DONANTE),
        "usuarios:documentos",
    ),
    _a(
        "catalogo",
        "Cómo pedir alimentos",
        "Con la cuenta verificada entre a «Catálogo», agregue los productos al carrito con la cantidad que necesita "
        "y pulse «Enviar solicitud». Puede pedir hasta {max_productos_solicitud} productos distintos por solicitud. "
        "El administrador la aprueba y prepara la entrega.",
        "pedir pido solicitar alimentos comida mercado catalogo carrito productos solicitud enviar cuantos",
        (BENEFICIARIO, PUBLICO),
        "solicitudes:catalogo",
    ),
    _a(
        "estados_solicitud",
        "Estados de una solicitud",
        "Pendiente: la está revisando el administrador. Aprobada: se generó una entrega con código de seguimiento. "
        "Rechazada: el administrador indica el motivo. Cancelada: se anuló y lo reservado volvió al inventario.",
        "estados solicitud pendiente aprobada rechazada cancelada significa",
        (BENEFICIARIO, ADMIN),
        "solicitudes:mis_solicitudes",
    ),
    _a(
        "seguimiento",
        "Seguimiento de la entrega",
        "Cuando su solicitud se aprueba recibe un código de seguimiento. En «Seguimiento» lo escribe y ve el paso "
        "actual: en revisión, en bodega, en entrega y entregado. La entrega puede ser recogida en bodega o a domicilio.",
        "seguimiento entrega codigo donde esta pedido llega domicilio recoger bodega cuando",
        (BENEFICIARIO, ADMIN),
        "entregas:seguimiento",
    ),
    _a(
        "prioridad",
        "Cómo se decide la prioridad",
        "Cada beneficiario tiene un puntaje de necesidad de 0 a 100 calculado automáticamente con el Sisbén, el "
        "estrato, las personas del hogar, la discapacidad, las solicitudes recientes y el tiempo sin recibir ayuda. "
        "Las solicitudes pendientes de mayor puntaje se atienden primero. El cálculo es público y se explica paso "
        "a paso en la página de ayuda.",
        "puntaje prioridad necesidad grupo orden primero quien recibe criterio calcula",
        TODOS,
        "usuarios:ayuda_puntaje",
    ),
    # --- Donantes
    _a(
        "donar",
        "Cómo registrar una donación",
        "Ingrese como donante y pulse «Donar». Agregue cada producto con su categoría, cantidad, unidad y fecha de "
        "vencimiento. Puede marcar la donación como anónima. Cuando el administrador la recibe en bodega queda "
        "disponible en el catálogo.",
        "donar dono donacion regalar dar alimentos comida mercado registrar productos donante como",
        (DONANTE, PUBLICO),
        "donaciones:nueva",
    ),
    _a(
        "anonimo",
        "Donar de forma anónima",
        "Al registrar la donación marque «Donación anónima» (o déjelo como opción predeterminada en sus datos). "
        "Su nombre no se mostrará a beneficiarios ni en reportes; solo el administrador puede consultarlo y esa "
        "consulta queda registrada en la bitácora.",
        "anonimo anonima anonimato ocultar nombre privado",
        (DONANTE, PUBLICO),
        "donaciones:nueva",
    ),
    _a(
        "editar_donacion",
        "Editar o cancelar una donación",
        "En «Mis donaciones» abra la donación. Puede editarla o cancelarla mientras ningún producto haya salido "
        "en una entrega; para cancelar debe indicar el motivo.",
        "editar modificar cancelar anular donacion error cambiar",
        (DONANTE,),
        "donaciones:mis_donaciones",
    ),
    _a(
        "juridica",
        "Donantes empresa (persona jurídica)",
        "Si dona como empresa, regístrese como persona jurídica con NIT y razón social, y cargue la Cámara de "
        "Comercio y el RUT en «Documentos».",
        "empresa juridica nit camara comercio rut razon social",
        (DONANTE, PUBLICO),
        "usuarios:documentos",
    ),
    _a(
        "unidades",
        "Unidades de medida",
        "Las cantidades se registran en estas unidades: {unidades_medida}.",
        "unidades medida kilos kilogramos litros cantidad",
        (DONANTE, ADMIN),
    ),
    # --- Administración
    _a(
        "adm_documentos",
        "Revisar documentos (administrador)",
        "En Usuarios › Documentos por revisar aparecen primero los de confianza media. Junto a la imagen ve lo que "
        "el sistema leyó y las discrepancias; puede aprobar, rechazar con motivo o revertir una decisión automática.",
        "revisar aprobar rechazar documentos cola pendientes ocr verificacion",
        (ADMIN,),
        "usuarios:documentos_pendientes",
    ),
    _a(
        "adm_solicitudes",
        "Atender solicitudes (administrador)",
        "En Solicitudes se listan las pendientes ordenadas por puntaje de necesidad. Al aprobar se reservan los "
        "productos y se crea la entrega; al rechazar debe escribir el motivo.",
        "atender aprobar solicitudes pendientes rechazar orden",
        (ADMIN,),
        "solicitudes:lista_admin",
    ),
    _a(
        "adm_entregas",
        "Gestionar entregas (administrador)",
        "En Entregas avance cada una por sus pasos (en revisión, en bodega, en entrega, entregado) o cancélela "
        "indicando el motivo; cada cambio notifica al beneficiario y queda en el historial.",
        "entregas avanzar estado cancelar despachar",
        (ADMIN,),
        "entregas:lista",
    ),
    _a(
        "adm_inventario",
        "Inventario y vencimientos (administrador)",
        "En Inventario ve las existencias por bodega, su vigencia y el kardex. El sistema avisa {dias_alerta_vencimiento} "
        "días antes de que un producto venza y permite retirar los vencidos de una vez.",
        "inventario existencias vencimiento vencidos kardex bodega ajustar baja",
        (ADMIN,),
        "inventario:lista",
    ),
    _a(
        "adm_parametros",
        "Cambiar la configuración (administrador)",
        "En Sistema › Parámetros están todas las reglas configurables agrupadas por sección. Cada cambio se valida, "
        "queda en la bitácora y, si afecta el puntaje, recalcula a los beneficiarios automáticamente.",
        "parametros configuracion configurar cambiar reglas ajustes",
        (ADMIN,),
        "core:parametros",
    ),
    _a(
        "adm_mapa",
        "Mapa de beneficiarios (administrador)",
        "En Sistema › Mapa de beneficiarios ve dónde viven, con capas de puntos y de calor y filtros por grupo, "
        "verificación y fechas. Las direcciones se ubican solas; las que no se encuentran quedan para revisión "
        "manual. Cada consulta queda en la bitácora.",
        "mapa calor ubicacion direcciones geocodificacion barrios zonas",
        (ADMIN,),
        "reportes:mapa",
    ),
    _a(
        "adm_reportes",
        "Reportes (administrador)",
        "En Sistema › Reportes elija el reporte, filtre por fechas y descárguelo en PDF o Excel.",
        "reportes estadisticas informes exportar excel pdf graficas",
        (ADMIN,),
        "reportes:reportes",
    ),
    _a(
        "adm_bitacora",
        "Auditoría (administrador)",
        "En Sistema › Trazabilidad y auditoría está la bitácora con cada acción manual y automática, quién la hizo, "
        "cuándo y desde qué IP.",
        "bitacora auditoria trazabilidad historial quien hizo registro",
        (ADMIN,),
        "core:trazabilidad",
    ),
    _a(
        "adm_tareas",
        "Tareas automáticas (administrador)",
        "En Sistema › Tareas automáticas ve los procesos programados (vencimientos, recálculo de puntajes, "
        "geocodificación, lectura de documentos, limpieza del chat), su última ejecución y puede ejecutarlos ahora.",
        "tareas automaticas programadas cron nocturno ejecutar",
        (ADMIN,),
        "core:tareas",
    ),
    _a(
        "adm_chat",
        "Consultas del asistente (administrador)",
        "En Sistema › Consultas del asistente ve las preguntas que el asistente no supo responder y las que los "
        "usuarios le enviaron. Úselas para mejorar la base de conocimiento.",
        "chat asistente consultas preguntas sin respuesta escaladas",
        (ADMIN,),
        "asistente:panel",
    ),
]

# Qué se hace en cada pantalla (nombre de URL → descripción, sugerencias).
PAGINAS = {
    "core:inicio": (
        "la página de inicio",
        ["¿Cómo me registro?", "¿Cómo dono alimentos?", "¿Qué documentos necesito?"],
    ),
    "usuarios:login": (
        "la pantalla de ingreso",
        ["Olvidé mi contraseña", "Mi cuenta está bloqueada", "¿Cómo me registro?"],
    ),
    "usuarios:registro": (
        "el registro de una cuenta nueva",
        ["¿Qué requisitos tiene la contraseña?", "¿Qué documentos necesito?", "¿Cómo protegen mis datos?"],
    ),
    "usuarios:documentos": (
        "sus documentos de validación",
        ["¿Cómo cargo una foto?", "¿Cuánto tarda la verificación?", "¿Cuál es el estado de mis documentos?"],
    ),
    "usuarios:perfil": ("sus datos personales", ["¿Cómo cambio mi dirección?", "¿Cómo protegen mis datos?"]),
    "solicitudes:catalogo": (
        "el catálogo de alimentos disponibles",
        ["¿Cuántos productos puedo pedir?", "¿Cómo se decide la prioridad?"],
    ),
    "solicitudes:carrito": ("su carrito", ["¿Cómo envío la solicitud?", "¿Cuántos productos puedo pedir?"]),
    "solicitudes:mis_solicitudes": (
        "sus solicitudes",
        ["¿Cuál es el estado de mi solicitud?", "¿Qué significa cada estado?"],
    ),
    "entregas:seguimiento": ("el seguimiento de entregas", ["¿Dónde está mi entrega?", "¿Qué significa cada paso?"]),
    "donaciones:nueva": (
        "el registro de una donación",
        ["¿Puedo donar de forma anónima?", "¿Qué unidades puedo usar?"],
    ),
    "donaciones:mis_donaciones": (
        "sus donaciones",
        ["¿Cómo edito una donación?", "¿Cuál es el estado de mis donaciones?"],
    ),
    "reportes:dashboard": ("su panel", None),
    "usuarios:documentos_pendientes": (
        "la cola de documentos por revisar",
        ["¿Cómo funciona la verificación automática?", "¿Cómo reviso documentos?"],
    ),
    "solicitudes:lista_admin": (
        "las solicitudes de los beneficiarios",
        ["¿En qué orden se atienden?", "¿Cómo apruebo una solicitud?"],
    ),
    "inventario:lista": ("el inventario", ["¿Cómo funcionan las alertas de vencimiento?"]),
    "core:parametros": ("los parámetros del sistema", ["¿Cómo cambio la configuración?"]),
    "reportes:mapa": ("el mapa de beneficiarios", ["¿Cómo funciona el mapa de calor?"]),
}

SUGERENCIAS_ROL = {
    PUBLICO: ["¿Cómo me registro?", "¿Cómo dono alimentos?", "¿Qué documentos necesito?"],
    BENEFICIARIO: [
        "¿Cuál es el estado de mi solicitud?",
        "¿Cuál es el estado de mis documentos?",
        "¿Cómo pido alimentos?",
    ],
    DONANTE: [
        "¿Cómo registro una donación?",
        "¿Cuál es el estado de mis donaciones?",
        "¿Puedo donar de forma anónima?",
    ],
    ADMIN: ["¿Cómo reviso documentos?", "¿En qué orden se atienden las solicitudes?", "¿Dónde veo la auditoría?"],
}

# Parámetros cuyo valor puede conocer cualquiera (los demás solo el administrador).
PARAMETROS_PUBLICOS = {
    "max_productos_solicitud",
    "intentos_ingreso",
    "minutos_bloqueo",
    "vigencia_token_minutos",
    "tam_max_archivo_mb",
    "formatos_permitidos",
    "unidades_medida",
}


def _valor_legible(clave, valores):
    valor = valores.get(clave, "")
    if clave in ("formatos_permitidos",):
        return ", ".join(v.strip().upper() for v in valor.split(",") if v.strip())
    if clave == "unidades_medida":
        return ", ".join(v.strip() for v in valor.split(",") if v.strip())
    return valor


class _Valores(dict):
    def __missing__(self, clave):
        return "{" + clave + "}"


def _enlace(nombre_url):
    if not nombre_url:
        return ""
    try:
        return reverse(nombre_url)
    except NoReverseMatch:
        return ""


def articulos(rol):
    """Artículos visibles para el rol, con los valores de los parámetros ya reemplazados."""
    valores = parametros.todos()
    legibles = _Valores({clave: _valor_legible(clave, valores) for clave in valores})
    resultado = []
    for art in ARTICULOS:
        if rol in art.roles:
            resultado.append(art._replace(texto=art.texto.format_map(legibles), url=_enlace(art.url)))
    for clave, d in parametros.DEFINICIONES.items():
        if clave in PARAMETROS_PUBLICOS or rol == ADMIN:
            valor = legibles[clave] or "(sin definir)"
            texto = f"{d.desc} Valor actual: {valor}."
            if rol == ADMIN:
                texto += " Se cambia en Sistema › Parámetros."
            resultado.append(
                Articulo(
                    f"param:{clave}",
                    f"Parámetro: {d.desc.rstrip('.')}",
                    texto,
                    f"{clave.replace('_', ' ')} {d.grupo} parametro valor configurado limite maximo minimo",
                    (rol,),
                    _enlace("core:parametros") if rol == ADMIN else "",
                )
            )
    return resultado


def pagina(nombre_url):
    return PAGINAS.get(nombre_url)


def sugerencias(rol, nombre_url=None):
    datos = PAGINAS.get(nombre_url)
    if datos and datos[1]:
        return datos[1]
    return SUGERENCIAS_ROL.get(rol, SUGERENCIAS_ROL[PUBLICO])
