"""Acceso tipado a los parámetros del sistema.

Cada parámetro se declara una sola vez en DEFINICIONES. Al ejecutar `migrate`
se crean automáticamente los que falten (ver core.apps), de modo que agregar un
parámetro nuevo es solo declararlo aquí. El administrador los edita en
Sistema › Parámetros, agrupados por sección, y cada cambio queda en la bitácora.
"""
import re
from collections import OrderedDict, namedtuple

from django.core.exceptions import ValidationError
from django.utils.text import slugify

FORMATOS_VALIDOS = ("pdf", "jpg", "png")

Definicion = namedtuple("Definicion", "valor desc tipo grupo minimo maximo")


def _p(valor, desc, tipo="texto", grupo="General", minimo=None, maximo=None):
    return Definicion(valor, desc, tipo, grupo, minimo, maximo)


# Secciones en el orden en que se muestran en Sistema › Parámetros.
GRUPOS = OrderedDict([
    ("General", "Reglas generales del sistema"),
    ("Seguridad", "Ingreso, bloqueo y recuperación de contraseña"),
    ("Documentos", "Carga de documentos de validación"),
    ("Inventario", "Unidades, bodegas y vencimientos"),
    ("Puntaje de necesidad", "Pesos y escalas del puntaje automático de beneficiarios"),
    ("Grupos de necesidad", "Clasificación automática según el puntaje"),
    ("Mapa y geocodificación", "Ubicación automática de los beneficiarios, mapa y mapa de calor"),
    ("Verificación automática", "Lectura de documentos con OCR, calidad de imagen y decisión por semáforo"),
])

# Valores permitidos de los parámetros de tipo «opcion».
OPCIONES = {
    "geo_proveedor": [("nominatim", "Nominatim (OpenStreetMap, gratuito)"), ("desactivado", "Desactivado")],
}

DEFINICIONES = OrderedDict([
    # --- General
    ("max_productos_solicitud", _p("5", "Máximo de productos distintos por solicitud (carrito).", "entero", "General", 1, 50)),
    # --- Seguridad
    ("intentos_ingreso", _p("5", "Intentos fallidos de ingreso antes de bloquear la cuenta.", "entero", "Seguridad", 1, 20)),
    ("minutos_bloqueo", _p("15", "Minutos que dura el bloqueo temporal de la cuenta.", "entero", "Seguridad", 1, 1440)),
    ("vigencia_token_minutos", _p("60", "Vigencia en minutos del enlace de recuperación de contraseña.", "entero", "Seguridad", 5, 1440)),
    # --- Documentos
    ("tam_max_archivo_mb", _p("5", "Tamaño máximo de los documentos cargados, en MB.", "entero", "Documentos", 1, 25)),
    ("formatos_permitidos", _p("pdf,jpg,png", "Formatos de archivo permitidos (pdf, jpg, png) separados por comas.", "formatos", "Documentos")),
    # --- Inventario
    ("dias_alerta_vencimiento", _p("7", "Días generales de anticipación para la alerta de vencimiento.", "entero", "Inventario", 1, 365)),
    ("unidades_medida", _p(
        "kilogramos,gramos,libras,litros,mililitros,unidades,paquetes,cajas,bolsas,latas",
        "Lista de unidades de medida separadas por comas.", "lista", "Inventario",
    )),
    ("bodega_predeterminada", _p("", "Bodega donde ingresan los productos donados (identificador).", "bodega", "Inventario")),
    # --- Puntaje de necesidad: pesos (se normalizan: no es obligatorio que sumen 100)
    ("puntaje_peso_sisben", _p("25", "Peso del nivel de Sisbén en el puntaje (0 lo desactiva).", "entero", "Puntaje de necesidad", 0, 100)),
    ("puntaje_peso_estrato", _p("20", "Peso del estrato social en el puntaje.", "entero", "Puntaje de necesidad", 0, 100)),
    ("puntaje_peso_personas", _p("20", "Peso del número de personas en el hogar.", "entero", "Puntaje de necesidad", 0, 100)),
    ("puntaje_peso_discapacidad", _p("15", "Peso de la condición de discapacidad.", "entero", "Puntaje de necesidad", 0, 100)),
    ("puntaje_peso_solicitudes", _p("5", "Peso de las solicitudes recientes (necesidad activa).", "entero", "Puntaje de necesidad", 0, 100)),
    ("puntaje_peso_tiempo", _p("15", "Peso del tiempo sin recibir ayuda.", "entero", "Puntaje de necesidad", 0, 100)),
    # --- Puntaje de necesidad: escalas
    ("puntaje_escala_sisben", _p(
        "A:100, B:70, C:35, D:10, NR:50",
        "Escala 0-100 por nivel de Sisbén (A pobreza extrema … D no pobre; NR no registrado).", "escala", "Puntaje de necesidad",
    )),
    ("puntaje_escala_estrato", _p(
        "1:100, 2:80, 3:50, 4:25, 5:0, 6:0", "Escala 0-100 por estrato social.", "escala", "Puntaje de necesidad",
    )),
    ("puntaje_personas_tope", _p("8", "Personas en el hogar a partir de las cuales el criterio vale 100.", "entero", "Puntaje de necesidad", 1, 30)),
    ("puntaje_discapacidad_sin_soporte", _p(
        "50", "Valor (0-100) de la discapacidad declarada mientras el certificado no esté aprobado.", "entero", "Puntaje de necesidad", 0, 100,
    )),
    ("puntaje_dias_solicitudes", _p("90", "Ventana en días para contar las solicitudes recientes.", "entero", "Puntaje de necesidad", 1, 730)),
    ("puntaje_solicitudes_tope", _p("4", "Solicitudes recientes a partir de las cuales el criterio vale 100.", "entero", "Puntaje de necesidad", 1, 50)),
    ("puntaje_dias_sin_ayuda_tope", _p(
        "60", "Días sin recibir una entrega a partir de los cuales el criterio vale 100 (quien nunca ha recibido vale 100).",
        "entero", "Puntaje de necesidad", 1, 730,
    )),
    # --- Grupos de necesidad
    ("grupos_necesidad", _p(
        "Prioridad crítica|75|#b42318; Prioridad alta|55|#d9480f; Prioridad media|35|#b07d05; Prioridad baja|0|#2b8a3e",
        "Grupos «Nombre|puntaje mínimo|color» separados por punto y coma. Debe existir uno con mínimo 0.",
        "grupos", "Grupos de necesidad",
    )),
    ("solicitudes_orden_prioridad", _p(
        "si", "Ordenar las solicitudes pendientes por puntaje de necesidad (si) o solo por fecha de envío (no).", "booleano", "Grupos de necesidad",
    )),
    # --- Mapa y geocodificación
    ("geo_proveedor", _p("nominatim", "Servicio que convierte direcciones en coordenadas.", "opcion", "Mapa y geocodificación")),
    ("geo_url", _p("https://nominatim.openstreetmap.org/search", "Dirección del servicio de geocodificación (compatible con Nominatim).", "url", "Mapa y geocodificación")),
    ("geo_contexto", _p("Facatativá, Cundinamarca, Colombia", "Municipio, departamento y país que se agregan a las direcciones para ubicarlas.", "texto", "Mapa y geocodificación")),
    ("geo_pais", _p("co", "Códigos de país (ISO) donde se buscan las direcciones, separados por comas.", "texto", "Mapa y geocodificación")),
    ("geo_max_intentos", _p("5", "Intentos automáticos de geocodificación antes de marcar el caso para revisión.", "entero", "Mapa y geocodificación", 1, 20)),
    ("mapa_tiles_url", _p("https://tile.openstreetmap.org/{z}/{x}/{y}.png", "Plantilla de las teselas del mapa base (proveedor gratuito).", "url", "Mapa y geocodificación")),
    ("mapa_atribucion", _p("© colaboradores de OpenStreetMap", "Texto de atribución del mapa base.", "texto", "Mapa y geocodificación")),
    ("mapa_centro", _p("4.8143,-74.3546", "Centro inicial del mapa (latitud,longitud).", "coordenadas", "Mapa y geocodificación")),
    ("mapa_zoom", _p("13", "Acercamiento inicial del mapa (1 a 18).", "entero", "Mapa y geocodificación", 1, 18)),
    ("mapa_desplazamiento_m", _p(
        "300", "Desplazamiento aleatorio máximo, en metros, de los puntos al exportar el mapa (protege la ubicación exacta).",
        "entero", "Mapa y geocodificación", 0, 5000,
    )),
    ("calor_peso_puntaje", _p("60", "Peso del puntaje de necesidad en la intensidad del mapa de calor.", "entero", "Mapa y geocodificación", 0, 100)),
    ("calor_peso_solicitudes", _p("25", "Peso del número de solicitudes en la intensidad del mapa de calor.", "entero", "Mapa y geocodificación", 0, 100)),
    ("calor_peso_personas", _p("15", "Peso de las personas en el hogar en la intensidad del mapa de calor.", "entero", "Mapa y geocodificación", 0, 100)),
    ("calor_tope_solicitudes", _p("5", "Solicitudes a partir de las cuales ese componente del calor es máximo.", "entero", "Mapa y geocodificación", 1, 100)),
    # --- Verificación automática de documentos (OCR)
    ("ocr_activo", _p("si", "Leer automáticamente los documentos cargados (si) o dejar todo a la revisión manual (no).", "booleano", "Verificación automática")),
    ("ocr_umbral_alto", _p(
        "85", "Confianza (0-100) desde la cual el documento queda pre-aprobado automáticamente (semáforo verde).",
        "entero", "Verificación automática", 1, 100,
    )),
    ("ocr_umbral_bajo", _p(
        "40", "Confianza por debajo de la cual el documento se rechaza automáticamente (semáforo rojo). Entre ambos umbrales va a la cola del administrador.",
        "entero", "Verificación automática", 0, 99,
    )),
    ("ocr_auto_aprobar", _p("si", "Pre-aprobar automáticamente los documentos de confianza alta.", "booleano", "Verificación automática")),
    ("ocr_auto_rechazar", _p("si", "Rechazar automáticamente los documentos de confianza baja o ilegibles, con el motivo.", "booleano", "Verificación automática")),
    ("ocr_nitidez_minima", _p(
        "45", "Nitidez mínima (0-256) de una foto; por debajo se pide repetirla de inmediato por borrosa.", "entero", "Verificación automática", 0, 256,
    )),
    ("ocr_resolucion_minima", _p("500", "Lado menor mínimo de la imagen, en píxeles.", "entero", "Verificación automática", 100, 4000)),
    ("ocr_idioma", _p("spa", "Idioma de Tesseract (spa = español).", "texto", "Verificación automática")),
    ("ocr_tiempo_maximo", _p("40", "Segundos máximos de lectura por documento.", "entero", "Verificación automática", 5, 300)),
])

TIPOS_AYUDA = {
    "escala": "Formato: clave:valor separados por comas, con valores de 0 a 100. Ejemplo: A:100, B:70.",
    "grupos": "Formato: Nombre|mínimo|#color separados por punto y coma. Ejemplo: Alta|60|#d9480f; Baja|0|#2b8a3e.",
    "booleano": "Escriba si o no.",
    "lista": "Valores separados por comas.",
    "coordenadas": "Formato: latitud,longitud con punto decimal. Ejemplo: 4.8143,-74.3546.",
    "url": "Dirección completa que empieza por https://.",
}


def definicion(clave):
    return DEFINICIONES.get(clave) or _p("", "", "texto", "General")


# ---------------------------------------------------------------- Lectura

def _obtener(clave):
    from .models import Parametro

    try:
        return Parametro.objects.get(par_clave=clave).par_valor
    except Parametro.DoesNotExist:
        return DEFINICIONES[clave].valor


def todos():
    """Todos los valores en un diccionario (una sola consulta), para cálculos por lotes."""
    from .models import Parametro

    valores = {clave: d.valor for clave, d in DEFINICIONES.items()}
    valores.update(dict(Parametro.objects.filter(par_clave__in=list(DEFINICIONES)).values_list("par_clave", "par_valor")))
    return valores


def _valor(clave, cache=None):
    return cache[clave] if cache is not None and clave in cache else _obtener(clave)


def entero(clave, cache=None):
    try:
        return int(_valor(clave, cache))
    except (TypeError, ValueError):
        return int(DEFINICIONES[clave].valor)


def lista(clave, cache=None):
    return [v.strip() for v in _valor(clave, cache).split(",") if v.strip()]


def texto(clave, cache=None):
    return _valor(clave, cache)


def booleano(clave, cache=None):
    return str(_valor(clave, cache)).strip().lower() in ("si", "sí", "1", "true", "s")


def escala(clave, cache=None):
    try:
        return _parse_escala(_valor(clave, cache))
    except ValidationError:
        return _parse_escala(DEFINICIONES[clave].valor)


def coordenadas(clave, cache=None):
    try:
        return _parse_coordenadas(_valor(clave, cache))
    except ValidationError:
        return _parse_coordenadas(DEFINICIONES[clave].valor)


def _parse_coordenadas(valor):
    try:
        lat, lng = (float(v) for v in (valor or "").split(","))
    except ValueError:
        raise ValidationError("Use el formato latitud,longitud. Ejemplo: 4.8143,-74.3546.")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValidationError("Las coordenadas están fuera de rango.")
    return lat, lng


def grupos(clave="grupos_necesidad", cache=None):
    """Lista de grupos ordenada de mayor a menor umbral: [{clave, nombre, minimo, color}]."""
    try:
        return _parse_grupos(_valor(clave, cache))
    except ValidationError:
        return _parse_grupos(DEFINICIONES[clave].valor)


# ---------------------------------------------------------------- Formatos compuestos

def _parse_escala(valor):
    resultado = OrderedDict()
    for parte in (valor or "").split(","):
        if not parte.strip():
            continue
        if ":" not in parte:
            raise ValidationError(f"«{parte.strip()}» no tiene el formato clave:valor.")
        clave, numero = (p.strip() for p in parte.split(":", 1))
        try:
            numero = float(numero.replace(",", "."))
        except ValueError:
            raise ValidationError(f"El valor de «{clave}» debe ser un número.")
        if not 0 <= numero <= 100:
            raise ValidationError(f"El valor de «{clave}» debe estar entre 0 y 100.")
        resultado[clave.upper()] = numero
    if not resultado:
        raise ValidationError("La escala no puede quedar vacía.")
    return resultado


COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _parse_grupos(valor):
    grupos_ = []
    for parte in (valor or "").split(";"):
        if not parte.strip():
            continue
        trozos = [t.strip() for t in parte.split("|")]
        if len(trozos) != 3:
            raise ValidationError(f"«{parte.strip()}» debe tener el formato Nombre|mínimo|#color.")
        nombre, minimo, color = trozos
        if not nombre:
            raise ValidationError("Cada grupo necesita un nombre.")
        try:
            minimo = float(minimo.replace(",", "."))
        except ValueError:
            raise ValidationError(f"El mínimo del grupo «{nombre}» debe ser un número.")
        if not 0 <= minimo <= 100:
            raise ValidationError(f"El mínimo del grupo «{nombre}» debe estar entre 0 y 100.")
        if not COLOR.match(color):
            raise ValidationError(f"El color del grupo «{nombre}» debe tener el formato #RRGGBB.")
        grupos_.append({"clave": slugify(nombre)[:30], "nombre": nombre, "minimo": minimo, "color": color.lower()})
    if not grupos_:
        raise ValidationError("Defina al menos un grupo.")
    claves = [g["clave"] for g in grupos_]
    if len(set(claves)) != len(claves):
        raise ValidationError("Los nombres de los grupos no pueden repetirse.")
    if len({g["minimo"] for g in grupos_}) != len(grupos_):
        raise ValidationError("Dos grupos no pueden tener el mismo puntaje mínimo.")
    if not any(g["minimo"] == 0 for g in grupos_):
        raise ValidationError("Debe existir un grupo con mínimo 0 para que todo beneficiario quede clasificado.")
    return sorted(grupos_, key=lambda g: -g["minimo"])


# ---------------------------------------------------------------- Validación

def validar(clave, valor):
    """Valida y normaliza el valor de un parámetro antes de guardarlo."""
    d = definicion(clave)
    tipo = d.tipo
    valor = (valor or "").strip()
    if tipo == "entero":
        try:
            numero = int(valor)
        except ValueError:
            raise ValidationError("Debe ser un número entero.")
        minimo = 1 if d.minimo is None else d.minimo
        if numero < minimo:
            raise ValidationError("Debe ser mayor que cero." if minimo == 1 else f"Debe ser mayor o igual a {minimo}.")
        if clave == "tam_max_archivo_mb" and numero > 25:
            raise ValidationError("El tamaño máximo permitido es 25 MB.")
        if d.maximo is not None and numero > d.maximo:
            raise ValidationError(f"Debe ser menor o igual a {d.maximo}.")
        if clave in ("ocr_umbral_alto", "ocr_umbral_bajo"):
            alto = numero if clave == "ocr_umbral_alto" else entero("ocr_umbral_alto")
            bajo = numero if clave == "ocr_umbral_bajo" else entero("ocr_umbral_bajo")
            if bajo >= alto:
                raise ValidationError("El umbral bajo debe ser menor que el umbral alto.")
        if clave.startswith("puntaje_peso_") and numero == 0:
            otros = sum(entero(c) for c in DEFINICIONES if c.startswith("puntaje_peso_") and c != clave)
            if otros == 0:
                raise ValidationError("Al menos un criterio del puntaje debe tener peso mayor que cero.")
        return str(numero)
    if tipo == "formatos":
        formatos = [f.strip().lower().lstrip(".") for f in valor.split(",") if f.strip()]
        if not formatos:
            raise ValidationError("Indique al menos un formato.")
        invalidos = [f for f in formatos if f not in FORMATOS_VALIDOS]
        if invalidos:
            raise ValidationError("Solo se admiten los formatos PDF, JPG y PNG.")
        return ",".join(dict.fromkeys(formatos))
    if tipo == "lista":
        elementos = [e.strip().lower() for e in valor.split(",") if e.strip()]
        if not elementos:
            raise ValidationError("La lista no puede quedar vacía.")
        return ",".join(dict.fromkeys(elementos))
    if tipo == "bodega":
        if valor == "":
            return ""
        from catalogo.models import Bodega

        if not Bodega.objects.filter(pk=valor, bod_estado="activa").exists():
            raise ValidationError("Seleccione una bodega activa.")
        return valor
    if tipo == "booleano":
        if valor.lower() in ("si", "sí", "1", "true", "s"):
            return "si"
        if valor.lower() in ("no", "0", "false", "n"):
            return "no"
        raise ValidationError("Escriba si o no.")
    if tipo == "escala":
        escala_ = _parse_escala(valor)
        if clave == "puntaje_escala_sisben":
            faltan = [k for k in ("A", "B", "C", "D", "NR") if k not in escala_]
            if faltan:
                raise ValidationError("Faltan los niveles: " + ", ".join(faltan) + ".")
        if clave == "puntaje_escala_estrato":
            faltan = [str(k) for k in range(1, 7) if str(k) not in escala_]
            if faltan:
                raise ValidationError("Faltan los estratos: " + ", ".join(faltan) + ".")
        return ", ".join(f"{k}:{_numero(v)}" for k, v in escala_.items())
    if tipo == "opcion":
        permitidos = [k for k, _ in OPCIONES.get(clave, [])]
        if valor not in permitidos:
            raise ValidationError("Elija una de las opciones: " + ", ".join(permitidos) + ".")
        return valor
    if tipo == "coordenadas":
        lat, lng = _parse_coordenadas(valor)
        return f"{lat},{lng}"
    if tipo == "url":
        if not re.match(r"^https?://[^\s]+$", valor):
            raise ValidationError("Escriba una dirección completa que empiece por http:// o https://.")
        return valor
    if tipo == "grupos":
        grupos_ = _parse_grupos(valor)
        return "; ".join(f"{g['nombre']}|{_numero(g['minimo'])}|{g['color']}" for g in grupos_)
    return valor


def _numero(v):
    return str(int(v)) if float(v).is_integer() else str(v)


# ---------------------------------------------------------------- Reacciones a los cambios

_REACCIONES = []


def al_cambiar(prefijo):
    """Decorador: registra una función que se ejecuta cuando cambia un parámetro con ese prefijo."""

    def registrar(funcion):
        _REACCIONES.append((prefijo, funcion))
        return funcion

    return registrar


def notificar_cambio(clave, usuario=None):
    """Ejecuta las reacciones automáticas (por ejemplo, recalcular puntajes). Devuelve sus resúmenes."""
    resultados = []
    for prefijo, funcion in _REACCIONES:
        if clave.startswith(prefijo):
            resultado = funcion(clave, usuario)
            if resultado:
                resultados.append(resultado)
    return resultados


def sincronizar(Parametro=None):
    """Crea los parámetros declarados que aún no existan (se llama después de migrate)."""
    if Parametro is None:
        from .models import Parametro
    existentes = set(Parametro.objects.values_list("par_clave", flat=True))
    nuevos = [
        Parametro(par_clave=clave, par_valor=d.valor, par_desc=d.desc)
        for clave, d in DEFINICIONES.items() if clave not in existentes
    ]
    Parametro.objects.bulk_create(nuevos)
    return len(nuevos)
