"""Registro, edición y cancelación de donaciones."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse

from core.servicios import notificar_administradores
from inventario import servicios as inv_srv
from inventario import unidades
from inventario.models import Inventario

from .models import DetalleDonacion, Donacion


@transaction.atomic
def registrar(donacion, detalles, usuario):
    """Guarda la donación y sus productos e ingresa todo al inventario."""
    if not detalles:
        raise ValidationError("La donación debe tener al menos un producto.")
    for det in detalles:
        unidades.validar(det.dd_cantidad, det.dd_unidad)
    bodega = inv_srv.bodega_de_ingreso()
    donacion.save()
    for det in detalles:
        det.donacion = donacion
        det.save()
        inv_srv.ingresar_detalle(det, usuario, bodega)
    donacion.recalcular_estado()
    transaction.on_commit(lambda: notificar_administradores(
        "donacion", f"Nueva donación #{donacion.pk}",
        f"Se registró una donación con {len(detalles)} producto(s) de {donacion.nombre_publico}.",
        reverse("donaciones:detalle", args=[donacion.pk]),
    ))
    return donacion


@transaction.atomic
def actualizar(donacion, guardar, nuevos, eliminados, usuario):
    """Aplica la edición del donante. Solo si la donación no está reservada ni entregada."""
    actual = Donacion.objects.select_for_update().get(pk=donacion.pk)
    if not actual.editable:
        raise ValidationError("Solo se pueden editar donaciones disponibles que no tengan reservas ni entregas.")
    for det in [*guardar, *nuevos]:
        unidades.validar(det.dd_cantidad, det.dd_unidad)
    for det in eliminados:
        inv = getattr(det, "inventario", None)
        if inv and inv.inv_estado != Inventario.RETIRADO:
            inv_srv.dar_baja(inv, "retiro_donante", "Producto quitado de la donación por el donante", usuario)
        else:
            det.dd_estado = DetalleDonacion.RETIRADO
            det.save(update_fields=["dd_estado"])
    for det in guardar:
        det.save()
        if hasattr(det, "inventario"):
            inv_srv.sincronizar_detalle(det, usuario)
    if nuevos:
        bodega = inv_srv.bodega_de_ingreso()
        for det in nuevos:
            det.donacion = donacion
            det.save()
            inv_srv.ingresar_detalle(det, usuario, bodega)
    if not donacion.detalles.exclude(dd_estado=DetalleDonacion.RETIRADO).exists():
        raise ValidationError("La donación debe conservar al menos un producto. Si desea retirarla, cancélela.")
    donacion.save()
    donacion.recalcular_estado()
    return donacion


@transaction.atomic
def cancelar(donacion, usuario, motivo=""):
    donacion = Donacion.objects.select_for_update().get(pk=donacion.pk)
    if donacion.dona_estado in (Donacion.RESERVADA, Donacion.ENTREGADA) or donacion.tiene_movimientos_de_salida():
        raise ValidationError("No se puede cancelar una donación reservada o entregada.")
    if donacion.dona_estado == Donacion.CANCELADA:
        raise ValidationError("La donación ya está cancelada.")
    for det in donacion.detalles.all():
        inv = getattr(det, "inventario", None)
        if inv and inv.inv_estado != Inventario.RETIRADO:
            inv_srv.dar_baja(inv, "retiro_donante", motivo or "Donación cancelada", usuario)
        det.dd_estado = DetalleDonacion.RETIRADO
        det.save(update_fields=["dd_estado"])
    donacion.dona_estado = Donacion.CANCELADA
    if motivo:
        donacion.dona_obs = (donacion.dona_obs + f"\nCancelada: {motivo}").strip()
    donacion.save()
    return donacion
