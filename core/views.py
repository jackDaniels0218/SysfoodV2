from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from entregas.models import HistorialEntrega
from inventario.models import Kardex
from usuarios.models import Usuario

from . import parametros, tareas
from .fechas import filtrar_rango
from .forms import ParametroForm
from .models import Bitacora, Notificacion, Parametro
from .permisos import solo_admin
from .servicios import auditar


def inicio(request):
    if not request.user.is_authenticated:
        return render(request, "core/bienvenida.html")
    return redirect("reportes:dashboard")


def politica_datos(request):
    return render(request, "core/politica_datos.html")


# ---------------------------------------------------------------- Notificaciones


@login_required
def notificaciones(request):
    qs = request.user.notificaciones.all()
    if request.GET.get("filtro") == "no_leidas":
        qs = qs.filter(not_leida=False)
    pagina = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "core/notificaciones.html", {"pagina": pagina})


@login_required
@require_POST
def notificacion_leer(request, pk):
    noti = get_object_or_404(Notificacion, pk=pk, destinatario=request.user)
    noti.not_leida = True
    noti.save(update_fields=["not_leida"])
    if request.POST.get("abrir") and noti.not_url.startswith("/"):
        return redirect(noti.not_url)
    return redirect("core:notificaciones")


@login_required
@require_POST
def notificaciones_leer_todas(request):
    request.user.notificaciones.filter(not_leida=False).update(not_leida=True)
    messages.success(request, "Todas las notificaciones quedaron como leídas.")
    return redirect("core:notificaciones")


# ---------------------------------------------------------------- Parámetros


@solo_admin
def parametros_lista(request):
    por_clave = {p.par_clave: p for p in Parametro.objects.select_related("usuario_mod")}
    secciones = []
    for grupo, descripcion in parametros.GRUPOS.items():
        items = [por_clave[c] for c, d in parametros.DEFINICIONES.items() if d.grupo == grupo and c in por_clave]
        if items:
            secciones.append({"nombre": grupo, "descripcion": descripcion, "items": items})
    otros = [p for c, p in por_clave.items() if c not in parametros.DEFINICIONES]
    if otros:
        secciones.append({"nombre": "Otros", "descripcion": "", "items": otros})
    return render(request, "core/parametros.html", {"secciones": secciones})


@solo_admin
def parametro_editar(request, pk):
    parametro = get_object_or_404(Parametro, pk=pk)
    form = ParametroForm(parametro, request.POST or None, initial={"par_valor": parametro.par_valor})
    if request.method == "POST" and form.is_valid():
        anterior = parametro.par_valor
        parametro.par_valor = form.cleaned_data["par_valor"]
        parametro.usuario_mod = request.user
        parametro.save()
        auditar(
            request, "cambio_parametro", "parametro", parametro.par_clave, f"«{anterior}» → «{parametro.par_valor}»"
        )
        messages.success(request, f"Parámetro «{parametro.par_clave}» actualizado.")
        if anterior != parametro.par_valor:
            for resumen in parametros.notificar_cambio(parametro.par_clave, request.user):
                messages.info(request, resumen)
        return redirect(reverse("core:parametros") + f"#{slugify(parametros.definicion(parametro.par_clave).grupo)}")
    return render(
        request,
        "core/parametro_form.html",
        {"form": form, "p": parametro, "definicion": parametros.definicion(parametro.par_clave)},
    )


# ---------------------------------------------------------------- Tareas automáticas


@solo_admin
def tareas_lista(request):
    if request.method == "POST":
        nombre = request.POST.get("tarea")
        if nombre not in tareas.REGISTRO:
            raise Http404
        try:
            resultado = tareas.ejecutar(nombre, forzar=True)
        except Exception as error:  # Se informa al administrador sin romper la página.
            messages.error(request, f"La tarea falló: {error}")
        else:
            auditar(request, "tarea_programada", "tarea", nombre, f"Ejecución manual: {tareas._resumen(resultado)}")
            messages.success(request, f"«{tareas.REGISTRO[nombre].titulo}» ejecutada: {tareas._resumen(resultado)}.")
        return redirect("core:tareas")
    return render(request, "core/tareas.html", {"filas": tareas.estado()})


# ---------------------------------------------------------------- Trazabilidad (solo consulta)


def _rango(request, qs, campo):
    qs = filtrar_rango(qs, campo, request.GET.get("desde"), request.GET.get("hasta"))
    if request.GET.get("usuario", "").isdigit():
        qs = qs.filter(usuario_id=request.GET["usuario"])
    return qs


@solo_admin
def trazabilidad(request):
    vista = request.GET.get("vista", "bitacora")
    registro = request.GET.get("registro", "").strip()
    if vista == "kardex":
        qs = _rango(request, Kardex.objects.select_related("inventario", "usuario", "entrega"), "kar_fecha")
        if request.GET.get("tipo"):
            qs = qs.filter(kar_tipo=request.GET["tipo"])
        if registro:
            qs = qs.filter(
                Q(inventario_id=registro if registro.isdigit() else 0)
                | Q(inventario__inv_nom__icontains=registro)
                | Q(entrega__ent_cod__iexact=registro)
            )
        tipos = Kardex.TIPOS
    elif vista == "entregas":
        qs = _rango(request, HistorialEntrega.objects.select_related("entrega", "usuario"), "his_fecha").order_by(
            "-his_fecha", "-his_id"
        )
        if registro:
            qs = qs.filter(
                Q(entrega__ent_cod__icontains=registro) | Q(entrega_id=registro if registro.isdigit() else 0)
            )
        tipos = []
    else:
        vista = "bitacora"
        qs = _rango(request, Bitacora.objects.select_related("usuario"), "bit_fecha")
        if request.GET.get("tipo"):
            qs = qs.filter(bit_accion=request.GET["tipo"])
        if registro:
            qs = qs.filter(
                Q(bit_registro=registro) | Q(bit_entidad__icontains=registro) | Q(bit_detalle__icontains=registro)
            )
        tipos = Bitacora.ACCIONES
    pagina = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(
        request,
        "core/trazabilidad.html",
        {
            "vista": vista,
            "pagina": pagina,
            "tipos": tipos,
            "usuarios": Usuario.objects.order_by("usu_nom"),
        },
    )


@login_required
@require_POST
def filtro_guardar(request):
    """Guarda (o reemplaza) los filtros actuales de una lista con un nombre."""
    from urllib.parse import urlencode

    from .models import FiltroGuardado

    vista = request.POST.get("vista", "")
    if vista not in FiltroGuardado.VISTAS:
        raise Http404
    destino = reverse(FiltroGuardado.VISTAS[vista])
    nombre = request.POST.get("nombre", "").strip()[:60]
    # Solo se guardan los parámetros de filtro, nunca la página.
    pares = [(k, v) for k, v in request.POST.items() if k.startswith("f_") and v.strip()]
    consulta = urlencode([(k[2:], v.strip()) for k, v in pares if k[2:] != "page"])[:500]
    if not nombre:
        messages.error(request, "Escriba un nombre para el filtro.")
    elif not consulta:
        messages.error(request, "Aplique al menos un filtro antes de guardarlo.")
    else:
        FiltroGuardado.objects.update_or_create(
            usuario=request.user,
            fil_vista=vista,
            fil_nombre=nombre,
            defaults={"fil_consulta": consulta},
        )
        messages.success(request, f"Filtro «{nombre}» guardado. Lo encuentra en «Filtros guardados».")
    return redirect(f"{destino}?{consulta}" if consulta else destino)


@login_required
@require_POST
def filtro_eliminar(request, pk):
    from .models import FiltroGuardado

    filtro = get_object_or_404(FiltroGuardado, pk=pk, usuario=request.user)
    destino = reverse(FiltroGuardado.VISTAS.get(filtro.fil_vista, "core:inicio"))
    filtro.delete()
    messages.success(request, f"Filtro «{filtro.fil_nombre}» eliminado.")
    return redirect(destino)


@login_required
def buscar(request):
    """Búsqueda global. Devuelve JSON para la paleta (Ctrl+K) y HTML sin JavaScript."""
    from . import busqueda

    consulta = request.GET.get("q", "").strip()
    grupos = busqueda.buscar(request.user, consulta)
    if request.headers.get("Accept", "").startswith("application/json") or request.GET.get("formato") == "json":
        respuesta = JsonResponse({"consulta": consulta, "grupos": [{"nombre": g, "resultados": r} for g, r in grupos]})
        respuesta["Cache-Control"] = "private, no-store"
        return respuesta
    return render(request, "core/buscar.html", {"consulta": consulta, "grupos": grupos})
