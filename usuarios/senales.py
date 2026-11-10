"""Recalculo automático del puntaje de necesidad cuando cambian sus datos de origen."""
from django.db.models.signals import post_delete, post_save


def _perfil(sender, instance, created, update_fields=None, raw=False, **kwargs):
    if raw:
        return
    if update_fields and set(update_fields) <= instance.CAMPOS_AUTOMATICOS:
        return  # Cambios hechos por el propio sistema (verificación o puntaje): no afectan el cálculo.
    from . import puntaje

    puntaje.recalcular(instance, "Registro del beneficiario" if created else "Cambio en los datos del beneficiario")


def _documento(sender, instance, raw=False, **kwargs):
    if raw:
        return
    from . import puntaje

    if instance.docv_tipo in ("identidad", "sisben", "residencia", "discapacidad"):
        puntaje.recalcular_usuario(instance.usuario_id, f"Cambio en los documentos ({instance.get_docv_tipo_display().lower()})")


def _solicitud(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    from . import puntaje

    motivo = f"Nueva solicitud #{instance.pk}" if created else f"Cambio de estado de la solicitud #{instance.pk}"
    puntaje.recalcular_usuario(instance.beneficiario_id, motivo)


def _entrega(sender, instance, created, raw=False, **kwargs):
    if raw or instance.ent_estado != instance.ENTREGADO:
        return
    from . import puntaje

    puntaje.recalcular_usuario(instance.solicitud.beneficiario_id, f"Entrega {instance.ent_cod} recibida")


def conectar():
    from django.apps import apps

    post_save.connect(_perfil, sender=apps.get_model("usuarios", "PerfilBeneficiario"), dispatch_uid="puntaje_perfil")
    Documento = apps.get_model("usuarios", "DocumentoValidacion")
    post_save.connect(_documento, sender=Documento, dispatch_uid="puntaje_documento")
    post_delete.connect(_documento, sender=Documento, dispatch_uid="puntaje_documento_borrado")
    post_save.connect(_solicitud, sender=apps.get_model("solicitudes", "Solicitud"), dispatch_uid="puntaje_solicitud")
    post_save.connect(_entrega, sender=apps.get_model("entregas", "Entrega"), dispatch_uid="puntaje_entrega")
