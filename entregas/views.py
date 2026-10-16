from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.fechas import filtrar_rango
from core.permisos import solo_admin, solo_beneficiario
from core.servicios import auditar

from . import servicios
from .forms import DatosEntregaForm
from .models import Entrega


@solo_admin
def lista(request):
    qs = Entrega.objects.select_related("solicitud__beneficiario", "bodega", "responsable")
    if request.GET.get("estado"):
        qs = qs.filter(ent_estado=request.GET["estado"])
    if request.GET.get("modalidad"):
        qs = qs.filter(ent_modalidad=request.GET["modalidad"])
    if request.GET.get("q"):
        q = request.GET["q"].strip()
        qs = qs.filter(Q(ent_cod__icontains=q) | Q(solicitud__beneficiario__usu_nom__icontains=q) | Q(solicitud__beneficiario__usu_ape__icontains=q))
    qs = filtrar_rango(qs, "ent_fec_crea", request.GET.get("desde"), request.GET.get("hasta"))
    pagina = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "entregas/lista.html", {"pagina": pagina, "estados": Entrega.ESTADOS, "modalidades": Entrega.MODALIDADES})


@solo_admin
def detalle(request, pk):
    entrega = get_object_or_404(Entrega.objects.select_related("solicitud__beneficiario__perfil_beneficiario", "bodega", "responsable"), pk=pk)
    form = DatosEntregaForm(instance=entrega)
    return render(request, "entregas/detalle.html", {
        "e": entrega, "detalles": entrega.detalles.select_related("inventario__categoria"),
        "historial": entrega.historial.select_related("usuario"), "form": form,
        "siguiente": dict(Entrega.ESTADOS).get(entrega.siguiente_estado), "pasos": Entrega.ESTADOS[:4],
    })


@solo_admin
@require_POST
def avanzar(request, pk):
    entrega = get_object_or_404(Entrega, pk=pk)
    cantidades = {}
    try:
        for det in entrega.detalles.all():
            valor = request.POST.get(f"entregada_{det.pk}")
            if valor not in (None, ""):
                cantidades[det.pk] = Decimal(valor.replace(",", "."))
        anterior = entrega.get_ent_estado_display()
        entrega = servicios.avanzar(entrega, request.user, request.POST.get("observacion", "").strip(), cantidades)
    except (ValidationError, InvalidOperation) as error:
        messages.error(request, error.messages[0] if isinstance(error, ValidationError) else "Cantidad inválida.")
    else:
        auditar(request, "cambio_estado", "entrega", pk, f"{anterior} → {entrega.get_ent_estado_display()}")
        messages.success(request, f"La entrega pasó a «{entrega.get_ent_estado_display()}».")
    return redirect("entregas:detalle", pk)


@solo_admin
@require_POST
def cancelar(request, pk):
    entrega = get_object_or_404(Entrega, pk=pk)
    motivo = request.POST.get("motivo", "").strip()
    try:
        servicios.cancelar(entrega, request.user, motivo)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        auditar(request, "cambio_estado", "entrega", pk, f"Cancelada: {motivo}")
        messages.success(request, "Entrega cancelada. Las cantidades reservadas volvieron al inventario.")
    return redirect("entregas:detalle", pk)


@solo_admin
@require_POST
def actualizar(request, pk):
    entrega = get_object_or_404(Entrega, pk=pk)
    form = DatosEntregaForm(request.POST, instance=Entrega.objects.get(pk=pk))
    if form.is_valid():
        d = form.cleaned_data
        try:
            servicios.actualizar_datos(entrega, request.user, d["ent_modalidad"], d["ent_dir_entrega"], d["ent_fec_prog"], d["responsable"], d["ent_obs"])
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            auditar(request, "editar", "entrega", pk, "Actualización de datos de la entrega")
            messages.success(request, "Datos de la entrega actualizados.")
    else:
        for errores in form.errors.values():
            messages.error(request, errores[0])
    return redirect("entregas:detalle", pk)


@solo_beneficiario
def seguimiento(request):
    """El beneficiario consulta el avance de su entrega con el código de seguimiento."""
    codigo = request.GET.get("codigo", "").strip().upper()
    entrega = None
    if codigo:
        entrega = Entrega.objects.filter(ent_cod=codigo, solicitud__beneficiario=request.user).select_related("bodega").first()
        if entrega is None:
            messages.error(request, "No encontramos una entrega suya con ese código.")
    mias = Entrega.objects.filter(solicitud__beneficiario=request.user).order_by("-ent_fec_crea")
    return render(request, "entregas/seguimiento.html", {
        "codigo": codigo, "e": entrega, "mias": mias, "pasos": Entrega.ESTADOS[:4],
        "historial": entrega.historial.all() if entrega else [],
        "detalles": entrega.detalles.select_related("inventario") if entrega else [],
    })
