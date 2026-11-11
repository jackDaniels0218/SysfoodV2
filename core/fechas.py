"""Filtros por rango de fechas sobre campos fecha-hora.

Se calculan los límites en Python (inicio y fin del día en la zona horaria local)
para no depender de las tablas de zonas horarias del servidor MySQL.
"""

from datetime import datetime, time, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_date


def _fecha(valor):
    try:
        return parse_date(valor.strip()) if isinstance(valor, str) else valor
    except ValueError:
        return None


def inicio_dia(valor):
    fecha = _fecha(valor)
    return timezone.make_aware(datetime.combine(fecha, time.min)) if fecha else None


def inicio_dia_siguiente(valor):
    fecha = _fecha(valor)
    return timezone.make_aware(datetime.combine(fecha + timedelta(days=1), time.min)) if fecha else None


def filtrar_rango(qs, campo, desde=None, hasta=None):
    """Filtra un campo DateTimeField por fechas (AAAA-MM-DD), ambos extremos incluidos."""
    inicio, fin = inicio_dia(desde) if desde else None, inicio_dia_siguiente(hasta) if hasta else None
    if inicio:
        qs = qs.filter(**{f"{campo}__gte": inicio})
    if fin:
        qs = qs.filter(**{f"{campo}__lt": fin})
    return qs
