"""Ubicación de los beneficiarios: geocodificación automática y datos del mapa.

Privacidad: solo el administrador consulta el mapa; cada consulta y cada
exportación quedan en la bitácora; al exportar, los puntos se desplazan al azar
(parámetro mapa_desplazamiento_m) y no se incluyen nombres ni documentos.
"""
import logging
import math
import random
import threading
from decimal import Decimal

from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from core import parametros
from core.fechas import inicio_dia, inicio_dia_siguiente
from core.geocodificacion import ErrorGeocodificacion, geocodificar
from core.servicios import auditar, notificar_administradores

from .models import PerfilBeneficiario as Perfil

log = logging.getLogger("sysfood")


# ---------------------------------------------------------------- Geocodificación del beneficiario

def geocodificar_beneficiario(perfil_id, motivo):
    """Intenta ubicar al beneficiario. Nunca lanza excepciones: registra el resultado."""
    perfil = Perfil.objects.filter(pk=perfil_id).first()
    if perfil is None or perfil.ben_geo_estado == Perfil.GEO_MANUAL:
        return None
    maximo = parametros.entero("geo_max_intentos")
    ahora = timezone.now()
    try:
        resultado = geocodificar(perfil.ben_dir)
        error = None if resultado.encontrada else "La dirección no se encontró en el mapa."
    except ErrorGeocodificacion as exc:
        resultado, error = None, str(exc)
    except Exception as exc:  # Cualquier otro fallo también se reintenta.
        log.exception("Error inesperado al geocodificar al beneficiario %s", perfil_id)
        resultado, error = None, f"Error inesperado: {exc}"

    if error is None:
        Perfil.objects.filter(pk=perfil.pk).update(
            ben_lat=resultado.lat, ben_lng=resultado.lng, ben_zona=resultado.zona, ben_geo_estado=Perfil.GEO_OK,
            ben_geo_intentos=perfil.ben_geo_intentos + 1, ben_geo_fecha=ahora, ben_geo_detalle=f"Ubicado ({resultado.fuente})",
        )
        auditar(None, "geocodificacion", "beneficiario", perfil.pk,
                f"Ubicado automáticamente en {resultado.lat}, {resultado.lng}"
                f"{' · zona ' + resultado.zona if resultado.zona else ''} · fuente {resultado.fuente}. Motivo: {motivo}.")
        return Perfil.GEO_OK

    intentos = perfil.ben_geo_intentos + 1
    estado = Perfil.GEO_REVISION if intentos >= maximo else Perfil.GEO_REINTENTAR
    Perfil.objects.filter(pk=perfil.pk).update(
        ben_geo_estado=estado, ben_geo_intentos=intentos, ben_geo_fecha=ahora, ben_geo_detalle=error[:255],
    )
    auditar(None, "geocodificacion", "beneficiario", perfil.pk,
            f"Intento {intentos} de {maximo} fallido: {error} "
            f"{'Se marca para revisión del administrador.' if estado == Perfil.GEO_REVISION else 'Se reintentará automáticamente.'} Motivo: {motivo}.")
    if estado == Perfil.GEO_REVISION:
        notificar_administradores(
            "cuenta", "Dirección por revisar",
            f"No fue posible ubicar en el mapa la dirección de {perfil.usuario.nombre_completo} tras {intentos} intentos. "
            "Corríjala o ubíquela manualmente.",
            reverse("usuarios:revisar_usuario", args=[perfil.pk]) + "#ubicacion",
        )
    return estado


def programar(perfil_id, motivo):
    """Geocodifica sin demorar la respuesta: en un hilo tras confirmar la transacción.
    En las pruebas (GEOCODIFICACION_EN_HILO=False) se ejecuta de inmediato."""
    if not getattr(settings, "GEOCODIFICACION_EN_HILO", True):
        geocodificar_beneficiario(perfil_id, motivo)
        return

    def lanzar():
        def correr():
            try:
                geocodificar_beneficiario(perfil_id, motivo)
            finally:
                close_old_connections()

        threading.Thread(target=correr, name="sysfood-geo", daemon=True).start()

    transaction.on_commit(lanzar)


def marcar_cambio_direccion(perfil, motivo):
    """La dirección cambió: se borra la ubicación anterior y se programa una nueva."""
    Perfil.objects.filter(pk=perfil.pk).update(
        ben_lat=None, ben_lng=None, ben_zona="", ben_geo_estado=Perfil.GEO_PENDIENTE, ben_geo_intentos=0, ben_geo_detalle="",
    )
    programar(perfil.pk, motivo)


def ubicar_manualmente(perfil, lat, lng, admin, request=None):
    Perfil.objects.filter(pk=perfil.pk).update(
        ben_lat=lat, ben_lng=lng, ben_geo_estado=Perfil.GEO_MANUAL, ben_geo_fecha=timezone.now(),
        ben_geo_detalle=f"Ubicado manualmente por {admin.nombre_completo}",
    )
    auditar(request, "geocodificacion", "beneficiario", perfil.pk, f"Ubicación manual en {lat}, {lng}.", usuario=admin)


def tarea_geocodificacion():
    """Tarea horaria: reintenta los pendientes y los fallidos (no los marcados para revisión)."""
    resumen = {"ubicados": 0, "fallidos": 0, "para_revision": 0}
    ids = list(Perfil.objects.filter(ben_geo_estado__in=[Perfil.GEO_PENDIENTE, Perfil.GEO_REINTENTAR]).values_list("pk", flat=True)[:200])
    for pk in ids:
        estado = geocodificar_beneficiario(pk, "Reintento programado")
        if estado == Perfil.GEO_OK:
            resumen["ubicados"] += 1
        elif estado == Perfil.GEO_REVISION:
            resumen["para_revision"] += 1
        else:
            resumen["fallidos"] += 1
    return resumen


# ---------------------------------------------------------------- Datos del mapa

def _filtros_validos(datos):
    filtros = {}
    grupos = {g["clave"] for g in parametros.grupos()}
    if datos.get("grupo") in grupos:
        filtros["grupo"] = datos["grupo"]
    if datos.get("verif") in dict(Perfil.ESTADOS_VERIF):
        filtros["verif"] = datos["verif"]
    for clave in ("desde", "hasta"):
        valor = (datos.get(clave) or "").strip()
        if valor and inicio_dia(valor):
            filtros[clave] = valor
    return filtros


def puntos(datos_filtro):
    """Lista de puntos con su peso de calor. Las fechas filtran las solicitudes que se cuentan:
    con un rango, solo aparecen beneficiarios con solicitudes en ese periodo."""
    from solicitudes.models import Solicitud

    filtros = _filtros_validos(datos_filtro)
    qs = Perfil.objects.filter(ben_lat__isnull=False, ben_lng__isnull=False).select_related("usuario")
    if "grupo" in filtros:
        qs = qs.filter(ben_grupo=filtros["grupo"])
    if "verif" in filtros:
        qs = qs.filter(ben_estado_verif=filtros["verif"])
    vigentes = [k for k, _ in Solicitud.ESTADOS if k != Solicitud.CANCELADA]
    condicion = Q(usuario__solicitudes__sol_estado__in=vigentes)
    if "desde" in filtros:
        condicion &= Q(usuario__solicitudes__sol_fec_envio__gte=inicio_dia(filtros["desde"]))
    if "hasta" in filtros:
        condicion &= Q(usuario__solicitudes__sol_fec_envio__lt=inicio_dia_siguiente(filtros["hasta"]))
    qs = qs.annotate(n_solicitudes=Count("usuario__solicitudes", filter=condicion, distinct=True))
    if "desde" in filtros or "hasta" in filtros:
        qs = qs.filter(n_solicitudes__gt=0)

    pesos = {k: parametros.entero(f"calor_peso_{k}") for k in ("puntaje", "solicitudes", "personas")}
    suma = sum(pesos.values()) or 1
    tope_sol = parametros.entero("calor_tope_solicitudes")
    tope_per = parametros.entero("puntaje_personas_tope")
    grupos = {g["clave"]: g for g in parametros.grupos()}
    resultado = []
    for p in qs:
        componentes = {
            "puntaje": float(p.ben_puntaje or 0) / 100,
            "solicitudes": min(p.n_solicitudes, tope_sol) / tope_sol,
            "personas": min(p.ben_num_personas, tope_per) / tope_per,
        }
        peso = sum(pesos[k] * componentes[k] for k in pesos) / suma
        grupo = grupos.get(p.ben_grupo) or {"nombre": "Sin grupo", "color": "#8a9a91"}
        resultado.append({
            "id": p.pk, "nombre": p.usuario.nombre_completo, "lat": float(p.ben_lat), "lng": float(p.ben_lng),
            "puntaje": float(p.ben_puntaje or 0), "grupo": grupo["nombre"], "color": grupo["color"], "zona": p.ben_zona,
            "verif": p.get_ben_estado_verif_display(), "solicitudes": p.n_solicitudes, "personas": p.ben_num_personas,
            "peso": round(peso, 3), "url": reverse("usuarios:revisar_usuario", args=[p.pk]),
        })
    return resultado, filtros


def desplazar(lat, lng, metros, azar=random):
    """Desplaza un punto una distancia aleatoria de hasta `metros` en una dirección aleatoria."""
    if metros <= 0:
        return lat, lng
    distancia = metros * math.sqrt(azar.random())  # Distribución uniforme en el círculo.
    angulo = azar.uniform(0, 2 * math.pi)
    dlat = distancia * math.cos(angulo) / 111_320
    dlng = distancia * math.sin(angulo) / (111_320 * max(math.cos(math.radians(lat)), 0.01))
    return round(lat + dlat, 5), round(lng + dlng, 5)


def puntos_para_exportar(lista):
    """Versión anónima y desplazada: sin nombres, documentos ni enlaces."""
    metros = parametros.entero("mapa_desplazamiento_m")
    azar = random.SystemRandom()
    exportados = []
    for p in lista:
        lat, lng = desplazar(p["lat"], p["lng"], metros, azar)
        exportados.append({"lat": lat, "lng": lng, "grupo": p["grupo"], "puntaje": p["puntaje"], "zona": p["zona"],
                           "solicitudes": p["solicitudes"], "personas": p["personas"], "peso_calor": p["peso"]})
    return exportados, metros


def resumen_geo():
    conteo = dict(Perfil.objects.values_list("ben_geo_estado").annotate(n=Count("pk")).values_list("ben_geo_estado", "n"))
    return [(k, v, conteo.get(k, 0)) for k, v in Perfil.ESTADOS_GEO]


def configuracion_mapa():
    lat, lng = parametros.coordenadas("mapa_centro")
    return {
        "tiles": parametros.texto("mapa_tiles_url"), "atribucion": parametros.texto("mapa_atribucion"),
        "centro": [lat, lng], "zoom": parametros.entero("mapa_zoom"),
    }


def coordenada(valor, minimo, maximo):
    try:
        numero = Decimal(str(valor).replace(",", ".")).quantize(Decimal("0.000001"))
    except Exception:
        return None
    return numero if minimo <= numero <= maximo else None
