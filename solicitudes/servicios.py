"""Carrito y ciclo de vida de las solicitudes."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core import parametros
from core.servicios import notificar, notificar_administradores
from inventario.models import Inventario

from .models import CarritoItem, Solicitud, SolicitudDetalle


def a_decimal(valor):
    try:
        numero = Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Ingrese una cantidad válida.") from None
    if not numero.is_finite():
        raise ValidationError("Ingrese una cantidad válida.")
    if numero <= 0:
        raise ValidationError("La cantidad debe ser mayor que cero.")
    if numero >= Decimal("10000000000"):
        raise ValidationError("La cantidad es demasiado grande.")
    return numero.quantize(Decimal("0.01"))


def _validar_producto(inv, cantidad):
    if not Inventario.catalogo().filter(pk=inv.pk).exists():
        raise ValidationError(f"«{inv.inv_nom}» ya no está disponible o está vencido.")
    inv.validar_cantidad(cantidad)
    if cantidad > inv.inv_cant_disp:
        raise ValidationError(
            f"La cantidad supera la disponible de «{inv.inv_nom}» ({inv.cantidad_texto(inv.inv_cant_disp)})."
        )


@transaction.atomic
def agregar_al_carrito(beneficiario, inv, cantidad):
    cantidad = a_decimal(cantidad)
    inv = Inventario.objects.get(pk=inv.pk)
    _validar_producto(inv, cantidad)
    item = CarritoItem.objects.filter(beneficiario=beneficiario, inventario=inv).first()
    if item is None:
        maximo = parametros.entero("max_productos_solicitud")
        if CarritoItem.objects.filter(beneficiario=beneficiario).count() >= maximo:
            raise ValidationError(f"El carrito admite máximo {maximo} productos distintos.")
        item = CarritoItem(beneficiario=beneficiario, inventario=inv, car_cant=cantidad)
    else:
        item.car_cant = cantidad
    item.save()
    return item


def quitar_del_carrito(beneficiario, item_id):
    CarritoItem.objects.filter(beneficiario=beneficiario, pk=item_id).delete()


def vaciar_carrito(beneficiario):
    CarritoItem.objects.filter(beneficiario=beneficiario).delete()


@transaction.atomic
def enviar_solicitud(beneficiario):
    items = list(CarritoItem.objects.select_for_update().filter(beneficiario=beneficiario).select_related("inventario"))
    if not items:
        raise ValidationError("El carrito está vacío.")
    maximo = parametros.entero("max_productos_solicitud")
    if len(items) > maximo:
        raise ValidationError(f"La solicitud admite máximo {maximo} productos distintos.")
    for item in items:
        _validar_producto(item.inventario, item.car_cant)
    solicitud = Solicitud.objects.create(beneficiario=beneficiario)
    SolicitudDetalle.objects.bulk_create(
        [SolicitudDetalle(solicitud=solicitud, inventario=i.inventario, sd_cant=i.car_cant) for i in items]
    )
    CarritoItem.objects.filter(beneficiario=beneficiario).delete()
    notificar_administradores(
        "solicitud",
        f"Nueva solicitud #{solicitud.pk}",
        f"{beneficiario.nombre_completo} envió una solicitud con {len(items)} producto(s).",
        reverse("solicitudes:admin_detalle", args=[solicitud.pk]),
    )
    return solicitud


@transaction.atomic
def aprobar(solicitud, admin, modalidad, direccion="", fecha_prog=None, bodega=None, observacion=""):
    """Reserva cantidades y genera la entrega. Todo o nada."""
    from entregas.models import Entrega, EntregaDetalle, HistorialEntrega
    from inventario import servicios as inv_srv

    solicitud = Solicitud.objects.select_for_update().get(pk=solicitud.pk)
    if solicitud.sol_estado != Solicitud.PENDIENTE:
        raise ValidationError("Solo se pueden aprobar solicitudes pendientes.")
    if modalidad == Entrega.DOMICILIO and not direccion.strip():
        raise ValidationError("Indique la dirección para la entrega a domicilio.")
    detalles = list(solicitud.detalles.select_related("inventario__bodega", "inventario__detalle__donacion__donante"))
    if bodega is None:
        conteo = {}
        for d in detalles:
            conteo[d.inventario.bodega] = conteo.get(d.inventario.bodega, 0) + 1
        bodega = max(conteo, key=conteo.get)
    entrega = Entrega.objects.create(
        solicitud=solicitud,
        bodega=bodega,
        responsable=admin,
        ent_modalidad=modalidad,
        ent_dir_entrega=direccion.strip() if modalidad == Entrega.DOMICILIO else "",
        ent_fec_prog=fecha_prog,
    )
    for d in detalles:
        inv_srv.reservar(d.inventario, d.sd_cant, admin, entrega)
        EntregaDetalle.objects.create(entrega=entrega, inventario=d.inventario, de_cant_asig=d.sd_cant)
    HistorialEntrega.objects.create(
        entrega=entrega,
        usuario=admin,
        his_estado_ant="",
        his_estado_nuevo=Entrega.EN_REVISION,
        his_obs="Entrega generada al aprobar la solicitud",
    )
    solicitud.sol_estado = Solicitud.APROBADA
    solicitud.revisor = admin
    solicitud.sol_obs_admin = observacion.strip()
    solicitud.sol_fec_resp = timezone.now()
    solicitud.save()

    def _avisar():
        notificar(
            solicitud.beneficiario,
            "solicitud",
            f"Solicitud #{solicitud.pk} aprobada",
            f"Su solicitud fue aprobada. Código de seguimiento de la entrega: {entrega.ent_cod}.",
            reverse("entregas:seguimiento") + f"?codigo={entrega.ent_cod}",
        )
        donantes = {}
        for d in detalles:
            donantes.setdefault(d.inventario.detalle.donacion.donante, []).append(d)
        for donante, items in donantes.items():
            nombres = ", ".join(f"{i.inventario.inv_nom} ({i.sd_cant} {i.inventario.inv_unidad})" for i in items)
            notificar(
                donante,
                "reserva",
                "Sus productos fueron reservados",
                f"Se reservaron productos de su donación para una entrega: {nombres}.",
                reverse("donaciones:mis_donaciones"),
            )

    transaction.on_commit(_avisar)
    return entrega


@transaction.atomic
def rechazar(solicitud, admin, observacion):
    if not observacion or not observacion.strip():
        raise ValidationError("El motivo es obligatorio al rechazar.")
    solicitud = Solicitud.objects.select_for_update().get(pk=solicitud.pk)
    if solicitud.sol_estado != Solicitud.PENDIENTE:
        raise ValidationError("Solo se pueden rechazar solicitudes pendientes.")
    solicitud.sol_estado = Solicitud.RECHAZADA
    solicitud.revisor = admin
    solicitud.sol_obs_admin = observacion.strip()
    solicitud.sol_fec_resp = timezone.now()
    solicitud.save()
    transaction.on_commit(
        lambda: notificar(
            solicitud.beneficiario,
            "solicitud",
            f"Solicitud #{solicitud.pk} rechazada",
            f"Su solicitud fue rechazada. Motivo: {solicitud.sol_obs_admin}",
            reverse("solicitudes:mis_solicitudes"),
        )
    )
    return solicitud


@transaction.atomic
def cancelar(solicitud, admin, observacion):
    """Cancela una solicitud pendiente o aprobada. Si tiene entrega, la cancela y libera lo reservado."""
    from entregas import servicios as ent_srv

    if not observacion or not observacion.strip():
        raise ValidationError("El motivo es obligatorio al cancelar.")
    solicitud = Solicitud.objects.select_for_update().get(pk=solicitud.pk)
    if solicitud.sol_estado not in (Solicitud.PENDIENTE, Solicitud.APROBADA):
        raise ValidationError("La solicitud ya fue cerrada.")
    entrega = getattr(solicitud, "entrega", None)
    if entrega is not None:
        if entrega.ent_estado == entrega.ENTREGADO:
            raise ValidationError("La entrega ya se realizó; la solicitud no puede cancelarse.")
        if entrega.ent_estado != entrega.CANCELADO:
            ent_srv.cancelar(entrega, admin, observacion, cancelar_solicitud=False)
    solicitud.sol_estado = Solicitud.CANCELADA
    solicitud.revisor = admin
    solicitud.sol_obs_admin = observacion.strip()
    solicitud.sol_fec_resp = timezone.now()
    solicitud.save()
    transaction.on_commit(
        lambda: notificar(
            solicitud.beneficiario,
            "solicitud",
            f"Solicitud #{solicitud.pk} cancelada",
            f"Su solicitud fue cancelada. Motivo: {solicitud.sol_obs_admin}",
            reverse("solicitudes:mis_solicitudes"),
        )
    )
    return solicitud
