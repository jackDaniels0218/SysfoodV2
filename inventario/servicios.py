"""Movimientos de inventario. Toda variación de cantidades pasa por aquí y queda en el kardex."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Bodega
from core import parametros
from core.servicios import notificar, notificar_administradores

from .models import Inventario, Kardex

CERO = Decimal("0")


def bodega_de_ingreso():
    valor = parametros.texto("bodega_predeterminada")
    bodega = None
    if valor:
        bodega = Bodega.objects.filter(pk=valor, bod_estado="activa").first()
    if bodega is None:
        bodega = Bodega.objects.filter(bod_estado="activa").order_by("bod_id").first()
    if bodega is None:
        raise ValidationError("No hay bodegas activas para recibir la donación. Contacte al administrador.")
    return bodega


def _bloquear(inv):
    return Inventario.objects.select_for_update().select_related("categoria").get(pk=inv.pk)


def _registrar(inv, tipo, cantidad, usuario, motivo, disp_ant, reserv_ant, entrega=None):
    if inv.inv_cant_disp < 0 or inv.inv_cant_reserv < 0:
        raise ValidationError("La operación dejaría cantidades negativas en el inventario.")
    inv.inv_estado = inv.calcular_estado()
    inv.save()
    Kardex.objects.create(
        inventario=inv,
        usuario=usuario,
        entrega=entrega,
        kar_tipo=tipo,
        kar_cantidad=cantidad,
        kar_cant_anterior=disp_ant,
        kar_cant_resultante=inv.inv_cant_disp,
        kar_reserv_anterior=reserv_ant,
        kar_reserv_resultante=inv.inv_cant_reserv,
        kar_motivo=motivo[:255],
    )
    inv.detalle.donacion.recalcular_estado()
    return inv


@transaction.atomic
def ingresar_detalle(detalle, usuario, bodega=None):
    """Ingreso automático al inventario de un producto donado."""
    from donaciones.models import DetalleDonacion

    bodega = bodega or bodega_de_ingreso()
    inv = Inventario(
        detalle=detalle,
        bodega=bodega,
        categoria=detalle.categoria,
        inv_nom=detalle.dd_nom,
        inv_unidad=detalle.dd_unidad,
        inv_divisible=detalle.dd_divisible,
        inv_cant_inicial=detalle.dd_cantidad,
        inv_cant_disp=detalle.dd_cantidad,
        inv_fec_venc=detalle.dd_fec_venc,
    )
    inv.inv_est_venc = inv.calcular_vigencia()
    inv.save()
    detalle.dd_estado = DetalleDonacion.EN_INVENTARIO
    detalle.save(update_fields=["dd_estado"])
    if inv.inv_est_venc == Inventario.PROXIMO:
        transaction.on_commit(lambda: _avisar_proximo(inv))
    return _registrar(
        inv, Kardex.INGRESO, detalle.dd_cantidad, usuario, f"Ingreso por donación #{detalle.donacion_id}", CERO, CERO
    )


def _avisar_proximo(inv):
    donacion = inv.detalle.donacion
    notificar(
        donacion.donante,
        "vencimiento",
        "Producto próximo a vencer",
        f"Su producto «{inv.inv_nom}» vence el {inv.inv_fec_venc:%d/%m/%Y} y se priorizará en las entregas.",
        reverse("donaciones:detalle", args=[donacion.pk]),
    )
    notificar_administradores(
        "vencimiento",
        "Producto próximo a vencer",
        f"«{inv.inv_nom}» ({inv.cantidad_texto(inv.inv_cant_disp)}) vence el {inv.inv_fec_venc:%d/%m/%Y}. Entrega prioritaria.",
        reverse("inventario:detalle", args=[inv.pk]),
    )


@transaction.atomic
def sincronizar_detalle(detalle, usuario):
    """Actualiza el inventario cuando el donante edita un producto de su donación."""
    inv = _bloquear(detalle.inventario)
    disp_ant, reserv_ant = inv.inv_cant_disp, inv.inv_cant_reserv
    diferencia = detalle.dd_cantidad - inv.inv_cant_inicial
    inv.inv_nom = detalle.dd_nom
    inv.inv_unidad = detalle.dd_unidad
    inv.inv_divisible = detalle.dd_divisible
    inv.categoria = detalle.categoria
    inv.inv_fec_venc = detalle.dd_fec_venc
    inv.inv_est_venc = inv.calcular_vigencia()
    if diferencia:
        inv.inv_cant_inicial = detalle.dd_cantidad
        inv.inv_cant_disp += diferencia
    if not inv.inv_divisible:
        for cantidad in (inv.inv_cant_inicial, inv.inv_cant_disp, inv.inv_cant_reserv):
            inv.validar_cantidad(cantidad)
    if diferencia:
        return _registrar(
            inv, Kardex.AJUSTE, diferencia, usuario, "Edición de la donación por el donante", disp_ant, reserv_ant
        )
    inv.save()
    return inv


@transaction.atomic
def ajustar(inv, nueva_disponible, motivo, usuario):
    if not motivo or not motivo.strip():
        raise ValidationError("El ajuste exige un motivo.")
    inv = _bloquear(inv)
    if inv.inv_estado == Inventario.RETIRADO:
        raise ValidationError("No se puede ajustar un producto retirado.")
    nueva_disponible = Decimal(nueva_disponible)
    if nueva_disponible < 0:
        raise ValidationError("La cantidad no puede ser negativa.")
    inv.validar_cantidad(nueva_disponible)
    disp_ant, reserv_ant = inv.inv_cant_disp, inv.inv_cant_reserv
    inv.inv_cant_disp = nueva_disponible
    return _registrar(inv, Kardex.AJUSTE, nueva_disponible - disp_ant, usuario, motivo.strip(), disp_ant, reserv_ant)


@transaction.atomic
def dar_baja(inv, motivo, detalle, usuario):
    from donaciones.models import DetalleDonacion

    inv = _bloquear(inv)
    if inv.inv_estado == Inventario.RETIRADO:
        raise ValidationError("El producto ya fue retirado.")
    if motivo not in dict(Inventario.MOTIVOS_BAJA):
        raise ValidationError("Seleccione un motivo de baja válido.")
    if inv.inv_cant_reserv > 0:
        raise ValidationError(
            "El producto tiene solicitudes aprobadas pendientes de entrega. Cancele antes esas entregas."
        )
    disp_ant, reserv_ant = inv.inv_cant_disp, inv.inv_cant_reserv
    inv.inv_cant_disp = CERO
    inv.inv_estado = Inventario.RETIRADO
    inv.inv_mot_baja = motivo
    inv.inv_det_baja = (detalle or "").strip()[:255]
    inv.inv_fec_baja = timezone.now()
    inv.usuario_baja = usuario
    inv.detalle.dd_estado = DetalleDonacion.RETIRADO
    inv.detalle.save(update_fields=["dd_estado"])
    texto = dict(Inventario.MOTIVOS_BAJA)[motivo] + (f": {inv.inv_det_baja}" if inv.inv_det_baja else "")
    inv.inv_estado = Inventario.RETIRADO
    if inv.inv_cant_disp < 0:
        raise ValidationError("Cantidad inválida.")
    inv.save()
    Kardex.objects.create(
        inventario=inv,
        usuario=usuario,
        kar_tipo=Kardex.BAJA,
        kar_cantidad=-disp_ant,
        kar_cant_anterior=disp_ant,
        kar_cant_resultante=CERO,
        kar_reserv_anterior=reserv_ant,
        kar_reserv_resultante=inv.inv_cant_reserv,
        kar_motivo=texto[:255],
    )
    inv.detalle.donacion.recalcular_estado()
    return inv


@transaction.atomic
def reservar(inv, cantidad, usuario, entrega):
    inv = _bloquear(inv)
    if inv.inv_estado == Inventario.RETIRADO or inv.calcular_vigencia() == Inventario.VENCIDO:
        raise ValidationError(f"«{inv.inv_nom}» ya no está disponible (retirado o vencido).")
    inv.validar_cantidad(cantidad)
    if cantidad > inv.inv_cant_disp:
        raise ValidationError(
            f"No hay cantidad suficiente de «{inv.inv_nom}»: disponible {inv.cantidad_texto(inv.inv_cant_disp)}."
        )
    disp_ant, reserv_ant = inv.inv_cant_disp, inv.inv_cant_reserv
    inv.inv_cant_disp -= cantidad
    inv.inv_cant_reserv += cantidad
    return _registrar(
        inv,
        Kardex.RESERVA,
        cantidad,
        usuario,
        f"Reserva para la entrega {entrega.ent_cod}",
        disp_ant,
        reserv_ant,
        entrega,
    )


@transaction.atomic
def liberar(inv, cantidad, usuario, entrega, motivo):
    inv = _bloquear(inv)
    if cantidad > inv.inv_cant_reserv:
        raise ValidationError("No se puede liberar más de lo reservado.")
    disp_ant, reserv_ant = inv.inv_cant_disp, inv.inv_cant_reserv
    inv.inv_cant_reserv -= cantidad
    if inv.inv_estado != Inventario.RETIRADO:
        inv.inv_cant_disp += cantidad
    return _registrar(inv, Kardex.LIBERACION, cantidad, usuario, motivo, disp_ant, reserv_ant, entrega)


@transaction.atomic
def entregar(inv, asignada, entregada, usuario, entrega):
    """Descuenta definitivamente lo reservado. Lo no entregado vuelve a estar disponible."""
    inv = _bloquear(inv)
    if entregada < 0 or entregada > asignada:
        raise ValidationError("La cantidad entregada debe estar entre 0 y la cantidad asignada.")
    inv.validar_cantidad(entregada)
    if asignada > inv.inv_cant_reserv:
        raise ValidationError("La reserva del producto no coincide con la entrega.")
    disp_ant, reserv_ant = inv.inv_cant_disp, inv.inv_cant_reserv
    inv.inv_cant_reserv -= entregada
    _registrar(inv, Kardex.ENTREGA, entregada, usuario, f"Entrega {entrega.ent_cod}", disp_ant, reserv_ant, entrega)
    sobrante = asignada - entregada
    if sobrante > 0:
        liberar(inv, sobrante, usuario, entrega, f"Sobrante no entregado de {entrega.ent_cod}")
    return inv


def controlar_vencimientos(hoy=None):
    """Proceso diario (Actividad 12): asigna la vigencia y notifica."""
    from donaciones.models import Donacion
    from solicitudes.models import CarritoItem

    hoy = hoy or timezone.localdate()
    proximos, vencidos, donaciones = [], [], set()
    pendientes = Inventario.objects.exclude(inv_estado=Inventario.RETIRADO).select_related(
        "categoria", "detalle__donacion__donante"
    )
    for inv in pendientes:
        nueva = inv.calcular_vigencia(hoy)
        if nueva == inv.inv_est_venc:
            continue
        Inventario.objects.filter(pk=inv.pk).update(inv_est_venc=nueva)
        inv.inv_est_venc = nueva
        donaciones.add(inv.detalle.donacion_id)
        donante = inv.detalle.donacion.donante
        if nueva == Inventario.PROXIMO:
            proximos.append(inv)
            notificar(
                donante,
                "vencimiento",
                "Producto próximo a vencer",
                f"Su producto «{inv.inv_nom}» vence el {inv.inv_fec_venc:%d/%m/%Y} y se priorizará en las entregas.",
                reverse("donaciones:detalle", args=[inv.detalle.donacion_id]),
            )
        elif nueva == Inventario.VENCIDO:
            vencidos.append(inv)
            CarritoItem.objects.filter(inventario=inv).delete()
            notificar(
                donante,
                "vencimiento",
                "Producto vencido",
                f"Su producto «{inv.inv_nom}» venció el {inv.inv_fec_venc:%d/%m/%Y} y será retirado del inventario.",
                reverse("donaciones:detalle", args=[inv.detalle.donacion_id]),
            )
    if proximos:
        notificar_administradores(
            "vencimiento",
            f"{len(proximos)} producto(s) próximos a vencer",
            "Productos para entrega prioritaria: " + ", ".join(i.inv_nom for i in proximos[:15]),
            reverse("inventario:lista") + "?vigencia=proximo",
        )
    if vencidos:
        notificar_administradores(
            "vencimiento",
            f"{len(vencidos)} producto(s) vencidos para retirar",
            "Productos vencidos marcados para retiro: " + ", ".join(i.inv_nom for i in vencidos[:15]),
            reverse("inventario:lista") + "?vigencia=vencido",
        )
    for donacion in Donacion.objects.filter(pk__in=donaciones):
        donacion.recalcular_estado()
    return {"proximos": len(proximos), "vencidos": len(vencidos)}
