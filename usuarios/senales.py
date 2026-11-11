"""Reacciones automáticas a los cambios de datos:
recálculo del puntaje de necesidad y geocodificación de la dirección."""

from django.db.models.signals import post_delete, post_init, post_save


def _recordar_direccion(sender, instance, **kwargs):
    instance._dir_original = instance.__dict__.get("ben_dir")


def _perfil(sender, instance, created, update_fields=None, raw=False, **kwargs):
    if raw:
        return
    if update_fields and set(update_fields) <= instance.CAMPOS_AUTOMATICOS:
        return  # Cambios hechos por el propio sistema (verificación, puntaje, ubicación): no afectan el cálculo.
    from . import puntaje, ubicacion

    puntaje.recalcular(instance, "Registro del beneficiario" if created else "Cambio en los datos del beneficiario")
    if created and not instance.ubicado:
        ubicacion.programar(instance.pk, "Registro del beneficiario")
    elif not created and instance.ben_dir != getattr(instance, "_dir_original", instance.ben_dir):
        ubicacion.marcar_cambio_direccion(instance, "Cambio de dirección")
    instance._dir_original = instance.ben_dir


def _documento(sender, instance, raw=False, **kwargs):
    if raw:
        return
    from . import puntaje

    if instance.docv_tipo in ("identidad", "sisben", "residencia", "discapacidad"):
        puntaje.recalcular_usuario(
            instance.usuario_id, f"Cambio en los documentos ({instance.get_docv_tipo_display().lower()})"
        )


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

    Perfil = apps.get_model("usuarios", "PerfilBeneficiario")
    post_init.connect(_recordar_direccion, sender=Perfil, dispatch_uid="geo_direccion_original")
    post_save.connect(_perfil, sender=Perfil, dispatch_uid="puntaje_perfil")
    Documento = apps.get_model("usuarios", "DocumentoValidacion")
    post_save.connect(_documento, sender=Documento, dispatch_uid="puntaje_documento")
    post_delete.connect(_documento, sender=Documento, dispatch_uid="puntaje_documento_borrado")
    post_save.connect(_solicitud, sender=apps.get_model("solicitudes", "Solicitud"), dispatch_uid="puntaje_solicitud")
    post_save.connect(_entrega, sender=apps.get_model("entregas", "Entrega"), dispatch_uid="puntaje_entrega")
