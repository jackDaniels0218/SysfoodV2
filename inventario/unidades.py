"""Unidades de medida contables y divisibles.

- Divisibles (kg, g, lb, L, mL): admiten decimales, por ejemplo 2,5 L.
- Contables (latas, cajas, unidades…): solo números enteros, por ejemplo 24 latas.

Qué unidades son divisibles se configura en el parámetro `unidades_divisibles`;
todas las demás de `unidades_medida` son contables. Cada producto guarda si su
unidad era divisible al registrarse (dd_divisible, inv_divisible) y la base de
datos rechaza decimales en los contables (restricciones CHECK).
"""

import time
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError

from core import formato, parametros

_cache = {"hasta": 0.0, "valor": None}


def _config():
    """(divisibles, abreviaturas), con caché de 30 s que se borra al cambiar los parámetros."""
    ahora = time.monotonic()
    if _cache["valor"] is None or ahora > _cache["hasta"] or getattr(settings, "TESTING", False):
        valores = parametros.todos()
        divisibles = {u.lower() for u in parametros.lista("unidades_divisibles", valores)}
        _cache["valor"] = (divisibles, parametros.pares("unidades_abreviaturas", valores))
        _cache["hasta"] = ahora + 30
    return _cache["valor"]


@parametros.al_cambiar("unidades_")
def _limpiar(clave=None, usuario=None):
    _cache["valor"] = None


def es_divisible(unidad):
    return (unidad or "").strip().lower() in _config()[0]


def a_decimal(valor):
    if isinstance(valor, Decimal):
        return valor
    try:
        return Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Ingrese una cantidad válida.")


def es_entero(cantidad):
    cantidad = a_decimal(cantidad)
    return cantidad == cantidad.to_integral_value()


def validar(cantidad, unidad, divisible=None):
    """Lanza ValidationError si la cantidad tiene decimales y la unidad es contable."""
    cantidad = a_decimal(cantidad)
    if divisible is None:
        divisible = es_divisible(unidad)
    if divisible:
        if cantidad != cantidad.quantize(Decimal("0.01"), rounding=ROUND_FLOOR):
            raise ValidationError(f"Use máximo dos decimales en {unidad}.")
        return cantidad
    if not es_entero(cantidad):
        abajo = cantidad.to_integral_value(ROUND_FLOOR)
        arriba = cantidad.to_integral_value(ROUND_CEILING)
        opciones = f"{formato.numero(abajo)} o {formato.numero(arriba)}" if abajo > 0 else formato.numero(arriba)
        raise ValidationError(
            f"«{unidad}» se cuenta en unidades completas: escriba {opciones}, no {formato.numero(cantidad)}."
        )
    return cantidad


def paso(unidad=None, divisible=None):
    """Atributo step del campo numérico."""
    if divisible is None:
        divisible = es_divisible(unidad)
    return "0.01" if divisible else "1"


def singular(unidad):
    u = (unidad or "").strip()
    if len(u) > 4 and u.endswith("es") and u[-3] in "dlrnzj":
        return u[:-2]
    if len(u) > 3 and u.endswith("s"):
        return u[:-1]
    return u


def etiqueta(cantidad, unidad):
    """Nombre de la unidad para mostrar junto a la cantidad: abreviatura o singular/plural."""
    abreviatura = _config()[1].get((unidad or "").strip().lower())
    if abreviatura:
        return abreviatura
    try:
        uno = a_decimal(cantidad) == 1
    except ValidationError:
        uno = False
    return singular(unidad) if uno else unidad


def formatear(cantidad, unidad):
    """50 kilogramos → «50 kg»; 24 latas → «24 latas»; 1 lata → «1 lata»; 2.50 litros → «2,5 L»."""
    if cantidad is None or cantidad == "":
        return ""
    return f"{formato.numero(cantidad, 2)} {etiqueta(cantidad, unidad)}".strip()


def mapa_unidades():
    """{unidad: True si es divisible} para los formularios (el JS ajusta el paso del campo)."""
    divisibles = _config()[0]
    return {u: u.lower() in divisibles for u in parametros.lista("unidades_medida")}


def no_conformes():
    """Registros con decimales en una unidad contable (según el parámetro vigente), por tabla."""
    from donaciones.models import DetalleDonacion
    from entregas.models import EntregaDetalle
    from inventario.models import Inventario
    from solicitudes.models import CarritoItem, SolicitudDetalle

    divisibles = _config()[0]

    def contables(qs, campo_unidad):
        return [o for o in qs if (_valor(o, campo_unidad) or "").lower() not in divisibles]

    def con_decimales(objetos, *campos):
        return [o for o in objetos if any(_valor(o, c) is not None and not es_entero(_valor(o, c)) for c in campos)]

    return {
        "Productos donados": con_decimales(contables(DetalleDonacion.objects.all(), "dd_unidad"), "dd_cantidad"),
        "Inventario": con_decimales(
            contables(Inventario.objects.exclude(inv_estado=Inventario.RETIRADO), "inv_unidad"),
            "inv_cant_inicial",
            "inv_cant_disp",
            "inv_cant_reserv",
        ),
        "Carritos": con_decimales(
            contables(CarritoItem.objects.select_related("inventario"), "inventario.inv_unidad"), "car_cant"
        ),
        "Solicitudes": con_decimales(
            contables(
                SolicitudDetalle.objects.select_related("inventario").filter(solicitud__sol_estado="pendiente"),
                "inventario.inv_unidad",
            ),
            "sd_cant",
        ),
        "Entregas": con_decimales(
            contables(EntregaDetalle.objects.select_related("inventario"), "inventario.inv_unidad"),
            "de_cant_asig",
            "de_cant_entregada",
        ),
    }


def _valor(objeto, ruta):
    for parte in ruta.split("."):
        objeto = getattr(objeto, parte, None)
    return objeto
