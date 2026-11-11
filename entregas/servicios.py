"""Cambios de estado de las entregas."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core.servicios import notificar
from inventario import servicios as inv_srv

from .models import Entrega, HistorialEntrega


def _avisar(entrega, texto_estado):
    solicitud = entrega.solicitud
    notificar(
        solicitud.beneficiario,
        "entrega",
        f"Entrega {entrega.ent_cod}: {texto_estado}",
        f"Su entrega {entrega.ent_cod} cambió a «{texto_estado}».",
        reverse("entregas:seguimiento") + f"?codigo={entrega.ent_cod}",
    )
    # El donante recibe el avance sin datos del beneficiario.
    donantes = {}
    for det in entrega.detalles.select_related("inventario__detalle__donacion__donante"):
        donantes.setdefault(det.inventario.detalle.donacion.donante, []).append(det.inventario.inv_nom)
    for donante, productos in donantes.items():
        notificar(
            donante,
            "entrega",
            f"Avance de entrega: {texto_estado}",
            f"La entrega que incluye sus productos ({', '.join(productos)}) cambió a «{texto_estado}».",
            reverse("donaciones:mis_donaciones"),
        )


def _historial(entrega, usuario, anterior, nuevo, obs=""):
    HistorialEntrega.objects.create(
        entrega=entrega,
        usuario=usuario,
        his_estado_ant=anterior,
        his_estado_nuevo=nuevo,
        his_obs=obs[:255],
    )


@transaction.atomic
def avanzar(entrega, usuario, observacion="", cantidades=None):
    """Mueve la entrega al siguiente estado permitido.

    cantidades: {de_id: Decimal} con lo efectivamente entregado (solo al pasar a Entregado).
    """
    entrega = Entrega.objects.select_for_update().get(pk=entrega.pk)
    siguiente = entrega.siguiente_estado
    if siguiente is None:
        raise ValidationError("La entrega no admite más cambios de estado.")
    anterior = entrega.ent_estado
    if siguiente == Entrega.ENTREGADO:
        cantidades = cantidades or {}
        for det in entrega.detalles.select_related("inventario"):
            entregada = Decimal(cantidades.get(det.pk, det.de_cant_asig))
            inv_srv.entregar(det.inventario, det.de_cant_asig, entregada, usuario, entrega)
            det.de_cant_entregada = entregada
            det.save(update_fields=["de_cant_entregada"])
        entrega.ent_fec_entrega = timezone.now()
    entrega.ent_estado = siguiente
    if observacion:
        entrega.ent_obs = (entrega.ent_obs + "\n" + observacion).strip()
    entrega.save()
    _historial(entrega, usuario, anterior, siguiente, observacion)
    texto = dict(Entrega.ESTADOS)[siguiente]
    transaction.on_commit(lambda: _avisar(entrega, texto))
    return entrega


@transaction.atomic
def cancelar(entrega, usuario, motivo, cancelar_solicitud=True):
    from solicitudes.models import Solicitud

    if not motivo or not motivo.strip():
        raise ValidationError("Cancelar la entrega exige un motivo.")
    entrega = Entrega.objects.select_for_update().get(pk=entrega.pk)
    if not entrega.cancelable:
        raise ValidationError("Una entrega entregada o ya cancelada no puede cancelarse.")
    anterior = entrega.ent_estado
    for det in entrega.detalles.select_related("inventario"):
        inv_srv.liberar(
            det.inventario, det.de_cant_asig, usuario, entrega, f"Cancelación de {entrega.ent_cod}: {motivo}"
        )
    entrega.ent_estado = Entrega.CANCELADO
    entrega.ent_mot_cancel = motivo.strip()[:255]
    entrega.save()
    _historial(entrega, usuario, anterior, Entrega.CANCELADO, motivo)
    if cancelar_solicitud:
        Solicitud.objects.filter(pk=entrega.solicitud_id).update(
            sol_estado=Solicitud.CANCELADA,
            sol_obs_admin=f"Entrega cancelada: {motivo.strip()}",
            sol_fec_resp=timezone.now(),
        )
    transaction.on_commit(lambda: _avisar(entrega, "Cancelado"))
    return entrega


@transaction.atomic
def actualizar_datos(entrega, usuario, modalidad, direccion, fecha_prog, responsable, observacion):
    entrega = Entrega.objects.select_for_update().get(pk=entrega.pk)
    if entrega.ent_estado in (Entrega.ENTREGADO, Entrega.CANCELADO):
        raise ValidationError("La entrega ya está cerrada.")
    if modalidad == Entrega.DOMICILIO and not (direccion or "").strip():
        raise ValidationError("Indique la dirección para la entrega a domicilio.")
    entrega.ent_modalidad = modalidad
    entrega.ent_dir_entrega = direccion.strip() if modalidad == Entrega.DOMICILIO else ""
    entrega.ent_fec_prog = fecha_prog
    entrega.responsable = responsable
    entrega.ent_obs = observacion or ""
    entrega.save()
    return entrega
