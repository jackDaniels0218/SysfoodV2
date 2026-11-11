import csv
import io
import json
from collections import OrderedDict
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Count, Sum
from django.http import Http404, HttpResponse, JsonResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalogo.models import Bodega, Categoria
from core import parametros
from core.fechas import inicio_dia
from core.permisos import solo_admin
from core.servicios import auditar
from core.tareas import ultima_ejecucion
from donaciones.models import Donacion
from entregas.models import Entrega
from inventario.models import Inventario
from solicitudes.models import Solicitud
from usuarios import ubicacion
from usuarios.models import DocumentoValidacion, PerfilBeneficiario, Usuario

from . import consultas, exportar, programados
from .models import ReporteProgramado


def _conteo(qs, campo, opciones):
    datos = dict(qs.values_list(campo).annotate(n=Count("pk")).values_list(campo, "n"))
    return OrderedDict((etiqueta, datos.get(clave, 0)) for clave, etiqueta in opciones)


def _grafico(conteo):
    return json.dumps({"etiquetas": list(conteo.keys()), "datos": list(conteo.values())})


@login_required
def dashboard(request):
    from core import guia

    request.guia = guia.resumen(request.user)
    u = request.user
    if u.es_admin:
        return _dashboard_admin(request)
    if u.es_donante:
        return _dashboard_donante(request)
    return _dashboard_beneficiario(request)


def _dashboard_admin(request):
    activo = Inventario.objects.exclude(inv_estado=Inventario.RETIRADO)
    usuarios_rol = OrderedDict()
    for rol, nombre in Usuario.ROLES:
        usuarios_rol[nombre] = _conteo(Usuario.objects.filter(usu_rol=rol), "usu_estado", Usuario.ESTADOS)
    contexto = {
        "usuarios_rol": usuarios_rol,
        "donaciones": _conteo(Donacion.objects.all(), "dona_estado", Donacion.ESTADOS),
        "inventario": {
            "disponible": Inventario.catalogo().count(),
            "proximo": activo.filter(inv_est_venc=Inventario.PROXIMO).count(),
            "vencido": activo.filter(inv_est_venc=Inventario.VENCIDO).count(),
            "reservado": activo.filter(inv_cant_reserv__gt=0).count(),
        },
        "docs_pendientes": DocumentoValidacion.objects.filter(docv_estado=DocumentoValidacion.CARGADO).count(),
        "ben_en_revision": PerfilBeneficiario.objects.filter(ben_estado_verif=PerfilBeneficiario.EN_REVISION).count(),
        "sol_pendientes": Solicitud.objects.filter(sol_estado=Solicitud.PENDIENTE).count(),
        "entregas": _conteo(Entrega.objects.all(), "ent_estado", Entrega.ESTADOS),
        "proximos": activo.filter(inv_est_venc=Inventario.PROXIMO)
        .select_related("categoria")
        .order_by("inv_fec_venc")[:8],
        "ultima_ejecucion": ultima_ejecucion(),
        "mapa_config": ubicacion.configuracion_mapa(),
        "geo_revision": PerfilBeneficiario.objects.filter(ben_geo_estado=PerfilBeneficiario.GEO_REVISION).count(),
    }
    contexto["g_donaciones"] = _grafico(contexto["donaciones"])
    contexto["g_entregas"] = _grafico(contexto["entregas"])
    contexto["g_inventario"] = json.dumps(
        {
            "etiquetas": ["Vigente", "Próximo a vencer", "Vencido"],
            "datos": [
                activo.filter(inv_est_venc=Inventario.VIGENTE).count(),
                contexto["inventario"]["proximo"],
                contexto["inventario"]["vencido"],
            ],
        }
    )
    contexto["guia"] = request.guia
    return render(request, "reportes/dashboard_admin.html", contexto)


def _dashboard_donante(request):
    mias = request.user.donaciones.all()
    inventario = Inventario.objects.filter(detalle__donacion__donante=request.user)
    cantidades = (
        inventario.values("inv_unidad")
        .annotate(donado=Sum("inv_cant_inicial"), disponible=Sum("inv_cant_disp"))
        .order_by("inv_unidad")
    )
    entregado = dict(
        inventario.filter(kardex__kar_tipo="entrega")
        .values("inv_unidad")
        .annotate(t=Sum("kardex__kar_cantidad"))
        .values_list("inv_unidad", "t")
    )
    por_estado = _conteo(mias, "dona_estado", Donacion.ESTADOS)
    return render(
        request,
        "reportes/dashboard_donante.html",
        {
            "por_estado": por_estado,
            "g_estado": _grafico(por_estado),
            "total": mias.count(),
            "cantidades": [dict(c, entregado=entregado.get(c["inv_unidad"], 0)) for c in cantidades],
            "proximos": inventario.filter(inv_est_venc=Inventario.PROXIMO)
            .exclude(inv_estado=Inventario.RETIRADO)
            .order_by("inv_fec_venc"),
            "recientes": mias.annotate(n=Count("detalles")).order_by("-dona_fec_reg")[:5],
            "guia": request.guia,
        },
    )


def _dashboard_beneficiario(request):
    perfil = request.user.perfil_beneficiario
    solicitudes = request.user.solicitudes.all()
    return render(
        request,
        "reportes/dashboard_beneficiario.html",
        {
            "perfil": perfil,
            "disponibles": Inventario.catalogo().count() if perfil.verificado else None,
            "solicitudes": _conteo(solicitudes, "sol_estado", Solicitud.ESTADOS),
            "entregas": Entrega.objects.filter(solicitud__beneficiario=request.user).order_by("-ent_fec_crea")[:5],
            "recientes": solicitudes.select_related("entrega")[:5],
            "guia": request.guia,
        },
    )


def _filtros(request, estadistica=None, datos=None):
    """Toma solo filtros válidos y admitidos por la estadística: fechas AAAA-MM-DD e identificadores numéricos.

    Sin fechas elegidas, aplica el rango por defecto (`reportes_dias_por_defecto`, 0 = todo el historial).
    """
    datos = request.GET if datos is None else datos
    admitidos = estadistica.filtros if estadistica else consultas.TODOS_LOS_FILTROS
    filtros = {}
    for clave in ("desde", "hasta"):
        valor = datos.get(clave, "").strip()
        if clave in admitidos and valor and inicio_dia(valor):
            filtros[clave] = valor
    for clave in ("categoria", "donante", "bodega"):
        valor = datos.get(clave, "").strip()
        if clave in admitidos and valor.isdigit():
            filtros[clave] = valor
    if "estado" in admitidos and datos.get("estado", "").strip():
        filtros["estado"] = datos["estado"].strip()[:30]
    dias = parametros.entero("reportes_dias_por_defecto")
    if (
        dias
        and "desde" in admitidos
        and not filtros.get("desde")
        and not filtros.get("hasta")
        and not datos.get("todo")
    ):
        filtros["desde"] = (timezone.localdate() - timedelta(days=dias)).isoformat()
    return filtros


def _texto_filtros(f):
    nombres = {
        "desde": "Desde",
        "hasta": "Hasta",
        "estado": "Estado",
        "categoria": "Categoría",
        "donante": "Donante",
        "bodega": "Bodega",
    }
    valores = dict(f)
    if "categoria" in f:
        valores["categoria"] = (
            Categoria.objects.filter(pk=f["categoria"]).values_list("cat_nom", flat=True).first() or f["categoria"]
        )
    if "bodega" in f:
        valores["bodega"] = (
            Bodega.objects.filter(pk=f["bodega"]).values_list("bod_nom", flat=True).first() or f["bodega"]
        )
    if "donante" in f:
        valores["donante"] = f"ID {f['donante']}"
    return "Filtros: " + (", ".join(f"{nombres[k]}: {v}" for k, v in valores.items()) if valores else "ninguno") + "."


def _estadistica(request):
    tipo = request.GET.get("tipo", "donaciones")
    if tipo not in consultas.ESTADISTICAS:
        raise Http404
    return consultas.ESTADISTICAS[tipo]


@solo_admin
def reportes(request):
    est = _estadistica(request)
    filtros = _filtros(request, est)
    datos = consultas.generar(est.clave, filtros)
    consulta = QueryDict(mutable=True)
    consulta.update({k: v for k, v in filtros.items()})
    consulta["tipo"] = est.clave
    return render(
        request,
        "reportes/reportes.html",
        {
            "grupos": consultas.por_grupo(),
            "tipo": est.clave,
            "est": est,
            "d": datos,
            "filtros": filtros,
            "texto_filtros": _texto_filtros(filtros),
            "g1": json.dumps(datos["grafico"]),
            "g2": json.dumps(datos.get("grafico2")) if datos.get("grafico2") else "",
            "categorias": Categoria.objects.all(),
            "bodegas": Bodega.objects.all(),
            "donantes": consultas.donantes_para_filtro(),
            "query": consulta.urlencode(),
            "formatos": exportar.FORMATOS,
            "frecuencias": ReporteProgramado.FRECUENCIAS,
            "programados": ReporteProgramado.objects.filter(rep_estadistica=est.clave).count(),
            "dias_por_defecto": parametros.entero("reportes_dias_por_defecto"),
        },
    )


@solo_admin
def exportar_reporte(request, formato):
    est = _estadistica(request)
    if formato not in exportar.FORMATOS:
        raise Http404
    filtros = _filtros(request, est)
    datos = consultas.generar(est.clave, filtros)
    texto = _texto_filtros(filtros)
    nombre = f"sysfood_{est.clave}_{timezone.localtime():%Y%m%d_%H%M}"
    respuesta = HttpResponse(
        exportar.generar_archivo(datos, formato, texto), content_type=exportar.FORMATOS[formato][0]
    )
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}.{formato}"'
    auditar(request, "crear", "reporte", est.clave, f"Exportación {formato.upper()}. {texto}")
    return respuesta


@solo_admin
def catalogo(request):
    """Inventario de todas las estadísticas del sistema, generado desde el registro único."""
    grupos = OrderedDict(
        (grupo, [dict(e._asdict(), filtros_texto=consultas.filtros_texto(e)) for e in lista])
        for grupo, lista in consultas.por_grupo().items()
    )
    return render(request, "reportes/catalogo.html", {"grupos": grupos, "paneles": consultas.EN_PANELES})


# ---------------------------------------------------------------- Envíos programados por correo


@solo_admin
@require_POST
def programar(request):
    est = consultas.ESTADISTICAS.get(request.POST.get("tipo", ""))
    if est is None:
        raise Http404
    destinatarios = [c.strip() for c in request.POST.get("destinatarios", "").replace(";", ",").split(",") if c.strip()]
    invalidos = []
    for correo in destinatarios:
        try:
            validate_email(correo)
        except ValidationError:
            invalidos.append(correo)
    frecuencia = request.POST.get("frecuencia", "")
    formato = request.POST.get("formato", "")
    volver = reverse("reportes:reportes") + "?" + request.POST.get("query", f"tipo={est.clave}")
    if not destinatarios or invalidos:
        messages.error(
            request, "Revise los correos: " + (", ".join(invalidos) if invalidos else "escriba al menos uno") + "."
        )
        return redirect(volver)
    if frecuencia not in dict(ReporteProgramado.FRECUENCIAS) or formato not in dict(ReporteProgramado.FORMATOS):
        messages.error(request, "Elija la frecuencia y el formato.")
        return redirect(volver)
    filtros = _filtros(request, est, request.POST)
    relativo = request.POST.get("relativo") == "1"
    if relativo:
        filtros.pop("desde", None)
        filtros.pop("hasta", None)
    reporte = ReporteProgramado.objects.create(
        creador=request.user,
        rep_estadistica=est.clave,
        rep_filtros=filtros,
        rep_relativo=relativo,
        rep_frecuencia=frecuencia,
        rep_formato=formato,
        rep_destinatarios=", ".join(destinatarios)[:500],
    )
    auditar(
        request,
        "crear",
        "reporte_programado",
        reporte.pk,
        f"{est.titulo}, {reporte.get_rep_frecuencia_display().lower()}, {formato.upper()}, a {reporte.rep_destinatarios}",
    )
    messages.success(
        request,
        f"Listo: «{est.titulo}» se enviará {reporte.get_rep_frecuencia_display().lower()} a {len(destinatarios)} correo(s).",
    )
    return redirect("reportes:programados")


@solo_admin
def programados_lista(request):
    return render(
        request,
        "reportes/programados.html",
        {
            "reportes": ReporteProgramado.objects.select_related("creador"),
            "hora": parametros.entero("reportes_hora_envio"),
            "nombres_filtros": programados.NOMBRES_FILTROS,
        },
    )


@solo_admin
@require_POST
def programado_accion(request, pk, accion):
    reporte = get_object_or_404(ReporteProgramado, pk=pk)
    if accion == "enviar":
        ok, mensaje = programados.enviar(reporte, usuario=request.user)
        (messages.success if ok else messages.error)(request, mensaje)
    elif accion == "pausar":
        reporte.rep_activo = not reporte.rep_activo
        reporte.save(update_fields=["rep_activo"])
        auditar(request, "editar", "reporte_programado", pk, "Activado" if reporte.rep_activo else "Pausado")
        messages.success(request, f"Envío {'activado' if reporte.rep_activo else 'pausado'}.")
    elif accion == "eliminar":
        auditar(request, "eliminar", "reporte_programado", pk, f"{reporte.titulo} a {reporte.rep_destinatarios}")
        reporte.delete()
        messages.success(request, "Envío programado eliminado.")
    else:
        raise Http404
    return redirect("reportes:programados")


# ---------------------------------------------------------------- Mapa de beneficiarios (solo administrador)


def _texto_filtros_mapa(filtros):
    if not filtros:
        return "sin filtros"
    nombres = {g["clave"]: g["nombre"] for g in parametros.grupos()}
    partes = []
    if "grupo" in filtros:
        partes.append(f"grupo {nombres.get(filtros['grupo'], filtros['grupo'])}")
    if "verif" in filtros:
        partes.append(f"verificación {dict(PerfilBeneficiario.ESTADOS_VERIF)[filtros['verif']]}")
    if "desde" in filtros:
        partes.append(f"desde {filtros['desde']}")
    if "hasta" in filtros:
        partes.append(f"hasta {filtros['hasta']}")
    return ", ".join(partes)


@solo_admin
def mapa(request):
    return render(
        request,
        "reportes/mapa.html",
        {
            "grupos": parametros.grupos(),
            "verifs": PerfilBeneficiario.ESTADOS_VERIF,
            "config": ubicacion.configuracion_mapa(),
            "resumen_geo": ubicacion.resumen_geo(),
            "revision": PerfilBeneficiario.objects.filter(
                ben_geo_estado__in=[PerfilBeneficiario.GEO_REVISION, PerfilBeneficiario.GEO_REINTENTAR]
            ).select_related("usuario")[:20],
            "desplazamiento": parametros.entero("mapa_desplazamiento_m"),
        },
    )


@solo_admin
def mapa_datos(request):
    puntos, filtros = ubicacion.puntos(request.GET)
    origen = "panel" if request.GET.get("origen") == "panel" else "mapa"
    auditar(
        request,
        "consulta_mapa",
        "mapa",
        "",
        f"Consulta del mapa ({origen}): {len(puntos)} punto(s), {_texto_filtros_mapa(filtros)}.",
    )
    respuesta = JsonResponse({"puntos": puntos, "total": len(puntos)})
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta


@solo_admin
def mapa_exportar(request, formato):
    if formato not in ("geojson", "csv"):
        raise Http404
    puntos, filtros = ubicacion.puntos(request.GET)
    anonimos, metros = ubicacion.puntos_para_exportar(puntos)
    nombre = f"sysfood_mapa_{timezone.localtime():%Y%m%d_%H%M}"
    if formato == "geojson":
        contenido = json.dumps(
            {
                "type": "FeatureCollection",
                "properties": {
                    "aviso": f"Ubicaciones desplazadas al azar hasta {metros} m para proteger la privacidad.",
                    "filtros": _texto_filtros_mapa(filtros),
                },
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [p["lng"], p["lat"]]},
                        "properties": {k: v for k, v in p.items() if k not in ("lat", "lng")},
                    }
                    for p in anonimos
                ],
            },
            ensure_ascii=False,
        )
        respuesta = HttpResponse(contenido, content_type="application/geo+json; charset=utf-8")
    else:
        salida = io.StringIO()
        salida.write("﻿")
        escritor = csv.writer(salida)
        escritor.writerow(["latitud", "longitud", "grupo", "puntaje", "zona", "solicitudes", "personas", "peso_calor"])
        for p in anonimos:
            escritor.writerow(
                [
                    p["lat"],
                    p["lng"],
                    p["grupo"],
                    p["puntaje"],
                    p["zona"],
                    p["solicitudes"],
                    p["personas"],
                    p["peso_calor"],
                ]
            )
        respuesta = HttpResponse(salida.getvalue(), content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}.{formato}"'
    auditar(
        request,
        "exportacion_mapa",
        "mapa",
        formato,
        f"Exportación {formato.upper()} de {len(anonimos)} punto(s) desplazados hasta {metros} m, sin nombres. "
        f"Filtros: {_texto_filtros_mapa(filtros)}.",
    )
    return respuesta
