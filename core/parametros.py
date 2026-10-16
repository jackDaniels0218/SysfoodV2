"""Acceso tipado a los parámetros del sistema."""
from django.core.exceptions import ValidationError

FORMATOS_VALIDOS = ("pdf", "jpg", "png")

# clave: (valor por defecto, descripción, tipo)
DEFINICIONES = {
    "max_productos_solicitud": ("5", "Máximo de productos distintos por solicitud (carrito).", "entero"),
    "dias_alerta_vencimiento": ("7", "Días generales de anticipación para la alerta de vencimiento.", "entero"),
    "tam_max_archivo_mb": ("5", "Tamaño máximo de los documentos cargados, en MB.", "entero"),
    "formatos_permitidos": ("pdf,jpg,png", "Formatos de archivo permitidos (pdf, jpg, png) separados por comas.", "formatos"),
    "intentos_ingreso": ("5", "Intentos fallidos de ingreso antes de bloquear la cuenta.", "entero"),
    "minutos_bloqueo": ("15", "Minutos que dura el bloqueo temporal de la cuenta.", "entero"),
    "vigencia_token_minutos": ("60", "Vigencia en minutos del enlace de recuperación de contraseña.", "entero"),
    "unidades_medida": (
        "kilogramos,gramos,libras,litros,mililitros,unidades,paquetes,cajas,bolsas,latas",
        "Lista de unidades de medida separadas por comas.", "lista",
    ),
    "bodega_predeterminada": ("", "Bodega donde ingresan los productos donados (identificador).", "bodega"),
}


def _obtener(clave):
    from .models import Parametro

    try:
        return Parametro.objects.get(par_clave=clave).par_valor
    except Parametro.DoesNotExist:
        return DEFINICIONES[clave][0]


def entero(clave):
    try:
        return int(_obtener(clave))
    except (TypeError, ValueError):
        return int(DEFINICIONES[clave][0])


def lista(clave):
    return [v.strip() for v in _obtener(clave).split(",") if v.strip()]


def texto(clave):
    return _obtener(clave)


def validar(clave, valor):
    """Valida y normaliza el valor de un parámetro antes de guardarlo."""
    tipo = DEFINICIONES[clave][2]
    valor = (valor or "").strip()
    if tipo == "entero":
        try:
            numero = int(valor)
        except ValueError:
            raise ValidationError("Debe ser un número entero.")
        if numero < 1:
            raise ValidationError("Debe ser mayor que cero.")
        if clave == "tam_max_archivo_mb" and numero > 25:
            raise ValidationError("El tamaño máximo permitido es 25 MB.")
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
    return valor
