"""Geocodificación de direcciones con caché.

Proveedor por defecto: Nominatim (OpenStreetMap), gratuito. Se respeta su política
de uso: un agente de usuario propio, como máximo una consulta por segundo y caché
local para no repetir consultas. No se envían datos personales: solo la dirección.
"""

import json
import logging
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal

from sysfood import rnf

from . import parametros

log = logging.getLogger("sysfood")
AGENTE = "SysFoodV2/2.0 (gestion de donaciones de alimentos)"
_candado = threading.Lock()
_ultima_consulta = [0.0]


class ErrorGeocodificacion(Exception):
    """Fallo temporal (red, servicio caído): se debe reintentar después."""


@dataclass
class Resultado:
    encontrada: bool
    lat: Decimal = None
    lng: Decimal = None
    zona: str = ""
    fuente: str = ""


def normalizar(direccion):
    """Texto canónico para la caché: minúsculas, sin tildes ni signos repetidos."""
    texto = unicodedata.normalize("NFKD", direccion or "").encode("ascii", "ignore").decode().lower()
    texto = texto.replace("#", " no ").replace("n°", " no ").replace("nº", " no ")
    texto = re.sub(r"[^a-z0-9 ,.-]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip(" ,.")[:255]


def consulta_completa(direccion):
    contexto = parametros.texto("geo_contexto").strip()
    if contexto and normalizar(contexto.split(",")[0]) not in normalizar(direccion):
        return f"{direccion}, {contexto}"
    return direccion


def _zona(direccion_osm):
    for clave in (
        "neighbourhood",
        "suburb",
        "quarter",
        "hamlet",
        "village",
        "city_district",
        "town",
        "city",
        "municipality",
    ):
        if direccion_osm.get(clave):
            return str(direccion_osm[clave])[:80]
    return ""


def _nominatim(consulta):
    url = (
        parametros.texto("geo_url")
        + "?"
        + urllib.parse.urlencode(
            {
                "q": consulta,
                "format": "jsonv2",
                "limit": 1,
                "addressdetails": 1,
                "countrycodes": parametros.texto("geo_pais"),
                "accept-language": "es",
            }
        )
    )
    with _candado:  # Política de uso: máximo una consulta por segundo.
        espera = 1.1 - (time.monotonic() - _ultima_consulta[0])
        if espera > 0:
            time.sleep(espera)
        _ultima_consulta[0] = time.monotonic()
    peticion = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(peticion, timeout=rnf.TIEMPO_ESPERA_GEOCODIFICACION_S) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        raise ErrorGeocodificacion(f"El servicio de mapas no respondió: {error}") from error
    if not datos:
        return Resultado(False, fuente="nominatim")
    primero = datos[0]
    return Resultado(
        True,
        Decimal(primero["lat"]).quantize(Decimal("0.000001")),
        Decimal(primero["lon"]).quantize(Decimal("0.000001")),
        _zona(primero.get("address") or {}),
        "nominatim",
    )


PROVEEDORES = {"nominatim": _nominatim}


def geocodificar(direccion):
    """Devuelve un Resultado. Usa la caché; lanza ErrorGeocodificacion si el fallo es temporal."""
    from .models import GeoCache

    clave = normalizar(direccion)
    if not clave:
        return Resultado(False, fuente="vacía")
    cache = GeoCache.objects.filter(geo_direccion=clave).first()
    if cache is not None:
        return Resultado(
            cache.geo_encontrada, cache.geo_lat, cache.geo_lng, cache.geo_zona, f"caché ({cache.geo_proveedor})"
        )
    proveedor = parametros.texto("geo_proveedor")
    if proveedor not in PROVEEDORES:
        raise ErrorGeocodificacion("La geocodificación automática está desactivada en Parámetros.")
    resultado = PROVEEDORES[proveedor](consulta_completa(direccion))
    if not resultado.encontrada:
        return resultado  # Lo no encontrado no se guarda: el reintento vuelve a consultar.
    GeoCache.objects.update_or_create(
        geo_direccion=clave,
        defaults={
            "geo_encontrada": resultado.encontrada,
            "geo_lat": resultado.lat,
            "geo_lng": resultado.lng,
            "geo_zona": resultado.zona,
            "geo_proveedor": proveedor,
        },
    )
    return resultado
