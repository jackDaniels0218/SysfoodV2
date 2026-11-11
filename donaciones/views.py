from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.fechas import filtrar_rango
from core.permisos import rol_requerido, solo_admin, solo_donante
from core.servicios import auditar
from usuarios.models import Usuario

from . import servicios
from .forms import CancelarForm, DetalleFormSetCrear, DetalleFormSetEditar, DonacionForm
from .models import DetalleDonacion, Donacion


def _filtrar(request, qs):
    estado = request.GET.get("estado")
    if estado:
        qs = qs.filter(dona_estado=estado)
    return filtrar_rango(qs, "dona_fec_reg", request.GET.get("desde"), request.GET.get("hasta"))


@solo_donante
def mis_donaciones(request):
    qs = _filtrar(request, request.user.donaciones.annotate(productos=Count("detalles")).order_by("-dona_fec_reg"))
    pagina = Paginator(qs, 15).get_page(request.GET.get("page"))
    return render(request, "donaciones/lista.html", {"pagina": pagina, "estados": Donacion.ESTADOS, "es_admin": False})


@solo_admin
def lista_admin(request):
    qs = (
        Donacion.objects.select_related("donante__perfil_donante")
        .annotate(productos=Count("detalles"))
        .order_by("-dona_fec_reg")
    )
    qs = _filtrar(request, qs)
    if request.GET.get("donante", "").isdigit():
        qs = qs.filter(donante_id=request.GET["donante"])
    if request.GET.get("anonima") in ("1", "0"):
        qs = qs.filter(dona_anonima=request.GET["anonima"] == "1")
    pagina = Paginator(qs, 20).get_page(request.GET.get("page"))
    donantes = Usuario.objects.filter(usu_rol=Usuario.DONANTE).order_by("usu_nom")
    return render(
        request,
        "donaciones/lista.html",
        {
            "pagina": pagina,
            "estados": Donacion.ESTADOS,
            "es_admin": True,
            "donantes": donantes,
        },
    )


@solo_donante
def nueva(request):
    perfil = request.user.perfil_donante
    donacion = Donacion(donante=request.user, dona_anonima=perfil.don_anonimo_def)
    form = DonacionForm(request.POST or None, instance=donacion)
    formset = DetalleFormSetCrear(request.POST or None, instance=donacion, prefix="productos")
    if request.method == "POST":
        if form.is_valid() & formset.is_valid():
            detalles = [f.save(commit=False) for f in formset.forms if f.cleaned_data]
            try:
                donacion = servicios.registrar(form.save(commit=False), detalles, request.user)
            except ValidationError as error:
                messages.error(request, error.messages[0])
            else:
                auditar(request, "crear", "donacion", donacion.pk, f"Donación con {len(detalles)} producto(s)")
                messages.success(
                    request, f"Donación #{donacion.pk} registrada. Sus productos ya están en el inventario."
                )
                return redirect("donaciones:detalle", donacion.pk)
        else:
            messages.error(request, "Revise los campos marcados.")
    return render(request, "donaciones/form.html", {"form": form, "formset": formset, "titulo": "Nueva donación"})


def _puede_gestionar(usuario, donacion):
    return usuario.es_admin or donacion.donante_id == usuario.pk


@rol_requerido(Usuario.DONANTE, Usuario.ADMIN)
def editar(request, pk):
    donacion = get_object_or_404(Donacion, pk=pk)
    if not _puede_gestionar(request.user, donacion):
        raise PermissionDenied
    if not donacion.editable:
        messages.error(request, "Solo se pueden editar donaciones disponibles que no tengan reservas ni entregas.")
        return redirect("donaciones:detalle", pk)
    form = DonacionForm(request.POST or None, instance=donacion)
    qs = donacion.detalles.exclude(dd_estado=DetalleDonacion.RETIRADO)
    formset = DetalleFormSetEditar(request.POST or None, instance=donacion, queryset=qs, prefix="productos")
    if request.method == "POST":
        if form.is_valid() & formset.is_valid():
            guardar, nuevos, eliminados = [], [], []
            for f in formset.forms:
                if not f.cleaned_data:
                    continue
                if f.cleaned_data.get("DELETE"):
                    if f.instance.pk:
                        eliminados.append(f.instance)
                elif f.instance.pk:
                    guardar.append(f.save(commit=False))
                else:
                    nuevos.append(f.save(commit=False))
            try:
                servicios.actualizar(form.save(commit=False), guardar, nuevos, eliminados, request.user)
            except ValidationError as error:
                messages.error(request, error.messages[0])
            else:
                auditar(request, "editar", "donacion", pk, "Edición de la donación")
                messages.success(request, "Donación actualizada.")
                return redirect("donaciones:detalle", pk)
        else:
            messages.error(request, "Revise los campos marcados.")
    return render(
        request,
        "donaciones/form.html",
        {"form": form, "formset": formset, "titulo": f"Editar donación #{pk}", "objeto": donacion},
    )


@rol_requerido(Usuario.DONANTE, Usuario.ADMIN)
@require_POST
def cancelar(request, pk):
    donacion = get_object_or_404(Donacion, pk=pk)
    if not _puede_gestionar(request.user, donacion):
        raise PermissionDenied
    form = CancelarForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Indique el motivo de la cancelación.")
        return redirect("donaciones:detalle", pk)
    try:
        servicios.cancelar(donacion, request.user, form.cleaned_data["motivo"])
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        auditar(request, "cambio_estado", "donacion", pk, f"Cancelada: {form.cleaned_data['motivo']}")
        messages.success(request, "Donación cancelada y retirada del inventario.")
    return redirect("donaciones:detalle", pk)


@login_required
def detalle(request, pk):
    donacion = get_object_or_404(Donacion.objects.select_related("donante__perfil_donante"), pk=pk)
    if not _puede_gestionar(request.user, donacion):
        raise PermissionDenied
    revelar = False
    if request.method == "POST" and request.user.es_admin and request.POST.get("accion") == "revelar":
        revelar = True
        auditar(
            request,
            "consulta_anonimo",
            "donacion",
            pk,
            f"Consulta de la identidad del donante anónimo (usuario {donacion.donante_id})",
        )
    detalles = donacion.detalles.select_related("categoria", "inventario__bodega")
    entregado = donacion.detalles.aggregate(
        total=Sum("inventario__kardex__kar_cantidad", filter=Q(inventario__kardex__kar_tipo="entrega"))
    )["total"]
    return render(
        request,
        "donaciones/detalle.html",
        {
            "d": donacion,
            "detalles": detalles,
            "revelar": revelar or not donacion.dona_anonima or request.user.pk == donacion.donante_id,
            "entregado": entregado,
            "cancelar_form": CancelarForm(),
            "nombre_donante": donacion.nombre_donante(request.user),
        },
    )
