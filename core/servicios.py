"""Servicios transversales: auditoría y notificaciones."""

import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import Bitacora, Notificacion

log = logging.getLogger("sysfood")


def ip_cliente(request):
    if request is None:
        return None
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def auditar(request, accion, entidad, registro="", detalle="", usuario=None):
    """Registra una acción en la bitácora de auditoría."""
    if usuario is None and request is not None and request.user.is_authenticated:
        usuario = request.user
    return Bitacora.objects.create(
        usuario=usuario,
        bit_accion=accion,
        bit_entidad=entidad,
        bit_registro=str(registro or ""),
        bit_detalle=detalle,
        bit_ip=ip_cliente(request),
    )


def enviar_correo(destinatarios, asunto, mensaje):
    destinatarios = [d for d in destinatarios if d]
    if not destinatarios:
        return
    try:
        send_mail(f"[SysFood] {asunto}", mensaje, settings.DEFAULT_FROM_EMAIL, destinatarios, fail_silently=False)
    except Exception as exc:  # El fallo del correo no debe detener la operación.
        log.warning("No se pudo enviar el correo '%s': %s", asunto, exc)


def notificar(usuario, tipo, titulo, mensaje, url="", correo=True):
    """Crea una notificación interna y la envía por correo."""
    noti = Notificacion.objects.create(
        destinatario=usuario,
        not_tipo=tipo,
        not_titulo=titulo,
        not_mensaje=mensaje,
        not_url=url,
    )
    if correo:
        enlace = f"\n\nIngrese a SysFood: {settings.SITE_URL}{url}" if url else ""
        enviar_correo([usuario.usu_correo], titulo, f"Hola {usuario.usu_nom},\n\n{mensaje}{enlace}")
    return noti


def notificar_administradores(tipo, titulo, mensaje, url=""):
    from usuarios.models import Usuario

    for admin in Usuario.objects.filter(usu_rol=Usuario.ADMIN, usu_estado=Usuario.ACTIVO):
        notificar(admin, tipo, titulo, mensaje, url)
