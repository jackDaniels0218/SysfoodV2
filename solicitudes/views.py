from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalogo.models import Categoria
from core import parametros
from core.fechas import filtrar_rango
from core.permisos import beneficiario_verificado, solo_admin, solo_beneficiario
from core.servicios import auditar
from inventario.models import Inventario

from . import servicios
from .forms import AprobarForm, MotivoForm
from .models import CarritoItem, Solicitud


# ---------------------------------------------------------------- Beneficiario

@beneficiario_verificado
def catalogo(request):
    qs = Inventario.catalogo().select_related("categoria", "detalle__donacion__donante__perfil_donante")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(inv_nom__icontains=q) | Q(detalle__dd_desc__icontains=q))
    if request.GET.get("categoria", "").isdigit():
        qs = qs.filter(categoria_id=request.GET["categoria"])
    qs = qs.order_by("inv_fec_venc", "inv_nom")
    pagina = Paginator(qs, 12).get_page(request.GET.get("page"))
    en_carrito = dict(request.user.carrito.values_list("inventario_id", "car_cant"))
    return render(request, "solicitudes/catalogo.html", {
        "pagina": pagina, "categorias": Categoria.objects.filter(cat_estado="activa"), "en_carrito": en_carrito,
        "maximo": parametros.entero("max_productos_solicitud"),
    })


@beneficiario_verificado
@require_POST
def agregar(request, inv_id):
    inv = get_object_or_404(Inventario, pk=inv_id)
    try:
        servicios.agregar_al_carrito(request.user, inv, request.POST.get("cantidad", "1"))
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, f"«{inv.inv_nom}» está en su carrito.")
    destino = request.POST.get("volver") or ""
    return redirect(destino if destino.startswith("/") and not destino.startswith("//") else "solicitudes:catalogo")


@beneficiario_verificado
def carrito(request):
    items = request.user.carrito.select_related("inventario__categoria", "inventario__detalle__donacion")
    return render(request, "solicitudes/carrito.html", {"items": items, "maximo": parametros.entero("max_productos_solicitud")})


@beneficiario_verificado
@require_POST
def quitar(request, item_id):
    _guardar_para_deshacer(request, request.user.carrito.filter(pk=item_id))
    servicios.quitar_del_carrito(request.user, item_id)
    messages.info(request, "Producto quitado del carrito.", extra_tags="deshacer")
    return redirect("solicitudes:carrito")


def _guardar_para_deshacer(request, items):
    """Recuerda en la sesión lo que se quitó del carrito para poder deshacerlo."""
    request.session["carrito_deshacer"] = [[i.inventario_id, str(i.car_cant)] for i in items]


@beneficiario_verificado
@require_POST
def deshacer(request):
    """Vuelve a poner en el carrito lo último que se quitó o vació (si sigue disponible)."""
    restaurados, errores = 0, []
    for inv_id, cantidad in request.session.pop("carrito_deshacer", []):
        inv = Inventario.objects.filter(pk=inv_id).first()
        if inv is None:
            continue
        try:
            servicios.agregar_al_carrito(request.user, inv, cantidad)
            restaurados += 1
        except ValidationError as error:
            errores.append(error.messages[0])
    if restaurados:
        messages.success(request, f"Listo, se recuperaron {restaurados} producto(s) en el carrito.")
    for error in errores:
        messages.warning(request, error)
    if not restaurados and not errores:
        messages.info(request, "No hay nada que deshacer.")
    return redirect("solicitudes:carrito")


@beneficiario_verificado
@require_POST
def vaciar(request):
    _guardar_para_deshacer(request, request.user.carrito.all())
    servicios.vaciar_carrito(request.user)
    messages.info(request, "Se vació el carrito.", extra_tags="deshacer")
    return redirect("solicitudes:carrito")


@beneficiario_verificado
@require_POST
def enviar(request):
    try:
        solicitud = servicios.enviar_solicitud(request.user)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("solicitudes:carrito")
    auditar(request, "crear", "solicitud", solicitud.pk, f"Solicitud con {solicitud.detalles.count()} producto(s)")
    messages.success(request, f"Solicitud #{solicitud.pk} enviada. El administrador la revisará pronto.")
    return redirect("solicitudes:detalle", solicitud.pk)


@solo_beneficiario
def mis_solicitudes(request):
    qs = request.user.solicitudes.annotate(productos=Count("detalles")).select_related("entrega").order_by("-sol_fec_envio")
    if request.GET.get("estado"):
        qs = qs.filter(sol_estado=request.GET["estado"])
    pagina = Paginator(qs, 15).get_page(request.GET.get("page"))
    return render(request, "solicitudes/mis_solicitudes.html", {"pagina": pagina, "estados": Solicitud.ESTADOS})


@solo_beneficiario
def detalle(request, pk):
    solicitud = get_object_or_404(Solicitud, pk=pk, beneficiario=request.user)
    return render(request, "solicitudes/detalle.html", {
        "s": solicitud, "detalles": solicitud.detalles.select_related("inventario__categoria", "inventario__detalle__donacion"),
        "entrega": getattr(solicitud, "entrega", None),
    })


# ---------------------------------------------------------------- Administrador

@solo_admin
def lista_admin(request):
    qs = Solicitud.objects.select_related("beneficiario", "entrega").annotate(productos=Count("detalles"))
    estado = request.GET.get("estado", "pendiente" if "estado" not in request.GET else "")
    if estado:
        qs = qs.filter(sol_estado=estado)
    if request.GET.get("q"):
        q = request.GET["q"].strip()
        qs = qs.filter(Q(beneficiario__usu_nom__icontains=q) | Q(beneficiario__usu_ape__icontains=q) | Q(pk__iexact=q if q.isdigit() else 0))
    if request.GET.get("grupo"):
        qs = qs.filter(beneficiario__perfil_beneficiario__ben_grupo=request.GET["grupo"])
    qs = filtrar_rango(qs, "sol_fec_envio", request.GET.get("desde"), request.GET.get("hasta"))
    por_prioridad = estado == "pendiente" and parametros.booleano("solicitudes_orden_prioridad")
    if por_prioridad:
        # Orden prioritario: mayor puntaje de necesidad primero; a igual puntaje, la más antigua.
        qs = qs.order_by(F("beneficiario__perfil_beneficiario__ben_puntaje").desc(nulls_last=True), "sol_fec_envio")
    else:
        qs = qs.order_by("sol_fec_envio" if estado == "pendiente" else "-sol_fec_envio")
    qs = qs.select_related("beneficiario__perfil_beneficiario")
    pagina = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "solicitudes/admin_lista.html", {
        "pagina": pagina, "estados": Solicitud.ESTADOS, "estado": estado, "grupos": parametros.grupos(), "por_prioridad": por_prioridad,
    })


@solo_admin
def admin_detalle(request, pk):
    solicitud = get_object_or_404(Solicitud.objects.select_related("beneficiario__perfil_beneficiario", "revisor"), pk=pk)
    perfil = solicitud.beneficiario.perfil_beneficiario
    aprobar_form = AprobarForm(request.POST or None, initial={"direccion": perfil.ben_dir}, prefix="ap")
    motivo_form = MotivoForm(request.POST or None, prefix="mo")
    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "aprobar" and aprobar_form.is_valid():
                d = aprobar_form.cleaned_data
                entrega = servicios.aprobar(solicitud, request.user, d["modalidad"], d["direccion"], d["fecha_prog"], d["bodega"], d["observacion"])
                auditar(request, "cambio_estado", "solicitud", pk, f"Aprobada. Entrega {entrega.ent_cod}")
                messages.success(request, f"Solicitud aprobada. Se generó la entrega {entrega.ent_cod}.")
                return redirect("entregas:detalle", entrega.pk)
            if accion in ("rechazar", "cancelar") and motivo_form.is_valid():
                funcion = servicios.rechazar if accion == "rechazar" else servicios.cancelar
                funcion(solicitud, request.user, motivo_form.cleaned_data["observacion"])
                auditar(request, "cambio_estado", "solicitud", pk, f"{accion.capitalize()}: {motivo_form.cleaned_data['observacion']}")
                messages.success(request, f"Solicitud {'rechazada' if accion == 'rechazar' else 'cancelada'}.")
                return redirect("solicitudes:admin_detalle", pk)
            messages.error(request, "Revise los datos del formulario.")
        except ValidationError as error:
            messages.error(request, error.messages[0])
    detalles = solicitud.detalles.select_related("inventario__categoria", "inventario__bodega", "inventario__detalle__donacion__donante")
    return render(request, "solicitudes/admin_detalle.html", {
        "s": solicitud, "perfil": perfil, "detalles": detalles, "aprobar_form": aprobar_form, "motivo_form": motivo_form,
        "entrega": getattr(solicitud, "entrega", None),
        "otras": solicitud.beneficiario.solicitudes.exclude(pk=pk).order_by("-sol_fec_envio")[:5],
    })
