from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from catalogo.models import Bodega, Categoria
from core import parametros
from core.models import FiltroGuardado
from core.permisos import solo_admin
from core.servicios import auditar
from sysfood import rnf

from . import servicios, unidades
from .forms import AjusteForm, BajaForm
from .models import Inventario


def filtrar_inventario(request, qs):
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(inv_nom__icontains=q) | Q(detalle__dd_lote__icontains=q) | Q(detalle__dd_desc__icontains=q))
    for param, campo in (
        ("categoria", "categoria_id"),
        ("bodega", "bodega_id"),
        ("estado", "inv_estado"),
        ("vigencia", "inv_est_venc"),
    ):
        valor = request.GET.get(param, "")
        if valor and (not campo.endswith("_id") or valor.isdigit()):
            qs = qs.filter(**{campo: valor})
    return qs


def indicadores():
    """KPIs del panel de inventario (sobre lo no retirado)."""
    activos = Inventario.objects.exclude(inv_estado=Inventario.RETIRADO)
    datos = activos.aggregate(
        disponibles=Count("inv_id", filter=Q(inv_cant_disp__gt=0) & ~Q(inv_est_venc=Inventario.VENCIDO)),
        proximos=Count("inv_id", filter=Q(inv_est_venc=Inventario.PROXIMO, inv_cant_disp__gt=0)),
        vencidos=Count("inv_id", filter=Q(inv_est_venc=Inventario.VENCIDO)),
        reservados=Count("inv_id", filter=Q(inv_cant_reserv__gt=0)),
        agotados=Count("inv_id", filter=Q(inv_estado=Inventario.AGOTADO)),
    )
    datos["por_revisar"] = len(unidades.no_conformes()["Inventario"])
    return datos


@solo_admin
def lista(request):
    qs = Inventario.objects.select_related("categoria", "bodega", "detalle__donacion")
    if request.GET.get("revisar") == "1":
        qs = qs.filter(pk__in=[i.pk for i in unidades.no_conformes()["Inventario"]])
    elif not request.GET.get("estado"):
        qs = qs.exclude(inv_estado=Inventario.RETIRADO) if request.GET.get("retirados") != "1" else qs
    if request.GET.get("reservado") == "1":
        qs = qs.filter(inv_cant_reserv__gt=0)
    qs = filtrar_inventario(request, qs).order_by("inv_fec_venc", "inv_nom")
    # Vista en tabla o en tarjetas: se recuerda en la sesión.
    vista = request.GET.get("vista")
    if vista in ("tabla", "tarjetas"):
        request.session["inventario_vista"] = vista
    vista = request.session.get("inventario_vista", "tabla")
    pagina = Paginator(qs, rnf.por_pagina("inventario")).get_page(request.GET.get("page"))
    dias = parametros.entero("dias_alerta_vencimiento")
    alertas = (
        Inventario.objects.filter(inv_est_venc=Inventario.PROXIMO, inv_cant_disp__gt=0)
        .exclude(inv_estado=Inventario.RETIRADO)
        .select_related("bodega")
        .order_by("inv_fec_venc")[:5]
    )
    return render(
        request,
        "inventario/lista.html",
        {
            "pagina": pagina,
            "categorias": Categoria.objects.all(),
            "bodegas": Bodega.objects.all(),
            "estados": Inventario.ESTADOS,
            "vigencias": Inventario.VIGENCIAS,
            "kpi": indicadores(),
            "alertas": alertas,
            "dias_alerta": dias,
            "vista": vista,
            "filtros": FiltroGuardado.objects.filter(usuario=request.user, fil_vista="inventario"),
            "hay_filtros": any(
                k in request.GET for k in ("q", "categoria", "bodega", "estado", "vigencia", "revisar", "reservado")
            ),
        },
    )


@solo_admin
def detalle(request, pk):
    inv = get_object_or_404(
        Inventario.objects.select_related("categoria", "bodega", "detalle__donacion__donante", "usuario_baja"), pk=pk
    )
    return render(
        request,
        "inventario/detalle.html",
        {
            "inv": inv,
            "kardex": inv.kardex.select_related("usuario", "entrega").order_by("kar_fecha", "kar_id"),
            "ajuste_form": AjusteForm(initial={"nueva_cantidad": inv.inv_cant_disp}, inventario=inv),
            "baja_form": BajaForm(),
        },
    )


@solo_admin
@require_POST
def ajustar(request, pk):
    inv = get_object_or_404(Inventario, pk=pk)
    form = AjusteForm(request.POST, inventario=inv)
    if form.is_valid():
        anterior = inv.inv_cant_disp
        try:
            inv = servicios.ajustar(inv, form.cleaned_data["nueva_cantidad"], form.cleaned_data["motivo"], request.user)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            auditar(
                request,
                "editar",
                "inventario",
                pk,
                f"Ajuste {inv.cantidad_texto(anterior)} → {inv.cantidad_texto(inv.inv_cant_disp)}: {form.cleaned_data['motivo']}",
            )
            messages.success(
                request,
                f"Ajuste registrado en el kardex: «{inv.inv_nom}» queda con {inv.cantidad_texto(inv.inv_cant_disp)}.",
            )
    else:
        errores = form.errors.get("nueva_cantidad")
        messages.error(
            request,
            errores[0]
            if errores and "unidades completas" in errores[0]
            else "El ajuste exige una cantidad válida (no negativa) y un motivo.",
        )
    siguiente = request.POST.get("siguiente", "")
    if siguiente and url_has_allowed_host_and_scheme(siguiente, {request.get_host()}, request.is_secure()):
        return redirect(siguiente)
    return redirect("inventario:detalle", pk)


@solo_admin
@require_POST
def baja(request, pk):
    inv = get_object_or_404(Inventario, pk=pk)
    form = BajaForm(request.POST)
    if form.is_valid():
        try:
            servicios.dar_baja(inv, form.cleaned_data["motivo"], form.cleaned_data["detalle"], request.user)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            auditar(
                request,
                "cambio_estado",
                "inventario",
                pk,
                f"Baja: {form.cleaned_data['motivo']} {form.cleaned_data['detalle']}".strip(),
            )
            messages.success(request, "Producto retirado del inventario.")
    else:
        for errores in form.errors.values():
            messages.error(request, errores[0])
    return redirect("inventario:detalle", pk)


@solo_admin
@require_POST
def retirar_vencidos(request):
    """Da de baja de una vez los productos vencidos marcados para retiro."""
    retirados, omitidos = 0, 0
    for inv in Inventario.objects.filter(inv_est_venc=Inventario.VENCIDO).exclude(inv_estado=Inventario.RETIRADO):
        try:
            servicios.dar_baja(inv, "vencido", "Retiro de productos vencidos", request.user)
            auditar(request, "cambio_estado", "inventario", inv.pk, "Baja por vencimiento")
            retirados += 1
        except ValidationError:
            omitidos += 1
    if retirados:
        messages.success(request, f"Se retiraron {retirados} producto(s) vencidos.")
    if omitidos:
        messages.warning(request, f"{omitidos} producto(s) tienen entregas pendientes y no se retiraron.")
    if not retirados and not omitidos:
        messages.info(request, "No hay productos vencidos pendientes de retiro.")
    return redirect("inventario:lista")
