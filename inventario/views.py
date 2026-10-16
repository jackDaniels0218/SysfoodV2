from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalogo.models import Bodega, Categoria
from core.permisos import solo_admin
from core.servicios import auditar

from . import servicios
from .forms import AjusteForm, BajaForm
from .models import Inventario


def filtrar_inventario(request, qs):
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(inv_nom__icontains=q) | Q(detalle__dd_lote__icontains=q) | Q(detalle__dd_desc__icontains=q))
    for param, campo in (("categoria", "categoria_id"), ("bodega", "bodega_id"), ("estado", "inv_estado"), ("vigencia", "inv_est_venc")):
        valor = request.GET.get(param, "")
        if valor and (not campo.endswith("_id") or valor.isdigit()):
            qs = qs.filter(**{campo: valor})
    return qs


@solo_admin
def lista(request):
    qs = Inventario.objects.select_related("categoria", "bodega", "detalle__donacion")
    if not request.GET.get("estado"):
        qs = qs.exclude(inv_estado=Inventario.RETIRADO) if request.GET.get("retirados") != "1" else qs
    qs = filtrar_inventario(request, qs).order_by("inv_fec_venc", "inv_nom")
    pagina = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "inventario/lista.html", {
        "pagina": pagina, "categorias": Categoria.objects.all(), "bodegas": Bodega.objects.all(),
        "estados": Inventario.ESTADOS, "vigencias": Inventario.VIGENCIAS,
    })


@solo_admin
def detalle(request, pk):
    inv = get_object_or_404(Inventario.objects.select_related("categoria", "bodega", "detalle__donacion__donante", "usuario_baja"), pk=pk)
    return render(request, "inventario/detalle.html", {
        "inv": inv, "kardex": inv.kardex.select_related("usuario", "entrega").order_by("kar_fecha", "kar_id"),
        "ajuste_form": AjusteForm(initial={"nueva_cantidad": inv.inv_cant_disp}), "baja_form": BajaForm(),
    })


@solo_admin
@require_POST
def ajustar(request, pk):
    inv = get_object_or_404(Inventario, pk=pk)
    form = AjusteForm(request.POST)
    if form.is_valid():
        anterior = inv.inv_cant_disp
        try:
            inv = servicios.ajustar(inv, form.cleaned_data["nueva_cantidad"], form.cleaned_data["motivo"], request.user)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            auditar(request, "editar", "inventario", pk, f"Ajuste {anterior} → {inv.inv_cant_disp}: {form.cleaned_data['motivo']}")
            messages.success(request, "Ajuste registrado en el kardex.")
    else:
        messages.error(request, "El ajuste exige una cantidad válida (no negativa) y un motivo.")
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
            auditar(request, "cambio_estado", "inventario", pk, f"Baja: {form.cleaned_data['motivo']} {form.cleaned_data['detalle']}".strip())
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
