"""Reglas de negocio de cuentas y documentos de validación."""

import hashlib
import uuid
from contextlib import suppress

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core import parametros
from core.servicios import notificar, notificar_administradores

from .models import ArchivoDocumento, PerfilBeneficiario, PerfilDonante, Usuario
from .models import DocumentoValidacion as Doc

FIRMAS = {
    "pdf": (b"%PDF",),
    "jpg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
}
MIMES = {"pdf": "application/pdf", "jpg": "image/jpeg", "png": "image/png"}


def tipos_permitidos(usuario):
    if usuario.es_beneficiario:
        return list(Doc.TIPOS_BENEFICIARIO)
    if (
        usuario.es_donante
        and getattr(usuario, "perfil_donante", None)
        and usuario.perfil_donante.don_tipo_persona == PerfilDonante.JURIDICA
    ):
        return list(Doc.TIPOS_DONANTE_JURIDICO)
    return []


def tipos_obligatorios(usuario):
    if not usuario.es_beneficiario:
        return []
    tipos = [Doc.IDENTIDAD, Doc.SISBEN, Doc.RESIDENCIA]
    if usuario.perfil_beneficiario.ben_discapacidad:
        tipos.append(Doc.DISCAPACIDAD)
    return tipos


def validar_archivo(archivo, usuario):
    """Valida formato, contenido real, tamaño y duplicados. Devuelve (ext, mime, hash, bytes)."""
    formatos = parametros.lista("formatos_permitidos")
    maximo_mb = parametros.entero("tam_max_archivo_mb")
    nombre = archivo.name or ""
    ext = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if ext == "jpeg":
        ext = "jpg"
    if ext not in formatos:
        raise ValidationError(f"Formato no permitido. Use: {', '.join(f.upper() for f in formatos)}.")
    if archivo.size > maximo_mb * 1024 * 1024:
        raise ValidationError(f"El archivo supera el tamaño máximo de {maximo_mb} MB.")
    if archivo.size == 0:
        raise ValidationError("El archivo está vacío.")
    contenido = b"".join(archivo.chunks())
    if not any(contenido.startswith(f) for f in FIRMAS[ext]):
        raise ValidationError("El contenido del archivo no corresponde a un " + ext.upper() + " válido.")
    huella = hashlib.sha256(contenido).hexdigest()
    if Doc.objects.filter(docv_hash=huella).exclude(usuario=usuario).exists():
        raise ValidationError("Este documento ya fue cargado en otra cuenta.")
    return ext, MIMES[ext], huella, contenido


def _guardar_archivo(usuario, ext, contenido):
    relativa = f"documentos/{usuario.pk}/{uuid.uuid4().hex}.{ext}"
    destino = settings.PROTECTED_MEDIA_ROOT / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    return relativa


def _borrar_archivo(doc):
    # Si el archivo no se puede borrar (permisos, disco), el registro igual se elimina.
    with suppress(OSError):
        doc.ruta_absoluta.unlink(missing_ok=True)


@transaction.atomic
def cargar_documento(usuario, tipo, archivo, fec_venc=None):
    """Carga o reemplaza el documento de un tipo. No permite reemplazar uno aprobado."""
    if tipo not in tipos_permitidos(usuario):
        raise ValidationError("Este tipo de documento no aplica para su cuenta.")
    if fec_venc and fec_venc < timezone.localdate():
        raise ValidationError("La fecha de vencimiento del documento ya pasó.")
    ext, mime, huella, contenido = validar_archivo(archivo, usuario)
    from . import verificacion

    calidad = verificacion.revisar_calidad(contenido, mime)  # Pide repetir de inmediato una foto borrosa.
    doc = Doc.objects.select_for_update().filter(usuario=usuario, docv_tipo=tipo).first()
    if doc and doc.docv_estado == Doc.APROBADO:
        raise ValidationError("El documento ya fue aprobado y no puede reemplazarse.")
    anterior = None
    if doc is None:
        doc = Doc(usuario=usuario, docv_tipo=tipo)
    else:
        anterior = Doc(docv_ruta=doc.docv_ruta)
    doc.docv_nom_archivo = archivo.name[:255]
    doc.docv_ruta = _guardar_archivo(usuario, ext, contenido)
    doc.docv_mime = mime
    doc.docv_tam_bytes = len(contenido)
    doc.docv_hash = huella
    doc.docv_estado = Doc.CARGADO
    doc.docv_obs = ""
    doc.revisor = None
    doc.docv_fec_revision = None
    doc.docv_fec_venc = fec_venc
    doc.docv_fec_carga = timezone.now()
    doc.docv_ocr_estado = Doc.OCR_PENDIENTE if verificacion.aplica(usuario, tipo) else Doc.OCR_NO_APLICA
    doc.docv_ocr_texto, doc.docv_ocr_confianza, doc.docv_decision_auto = "", None, ""
    doc.docv_ocr_resultado = {"calidad": calidad} if calidad else {}
    doc.docv_verif_auto, doc.docv_ocr_intentos, doc.docv_fec_ocr = False, 0, None
    doc.save()
    ArchivoDocumento.objects.update_or_create(documento=doc, defaults={"arc_contenido": contenido})
    if anterior:
        transaction.on_commit(lambda: _borrar_archivo(anterior))
    estado_previo = _estado_verif(usuario)
    nuevo = recalcular_verificacion(usuario)
    if nuevo == PerfilBeneficiario.EN_REVISION and estado_previo != nuevo:
        notificar_administradores(
            "documento",
            "Documentos pendientes de revisión",
            f"{usuario.nombre_completo} completó sus documentos y espera verificación.",
            reverse("usuarios:revisar_usuario", args=[usuario.pk]),
        )
    elif usuario.es_donante:
        notificar_administradores(
            "documento",
            "Documento de donante por revisar",
            f"{usuario.nombre_completo} cargó {doc.get_docv_tipo_display()}.",
            reverse("usuarios:revisar_usuario", args=[usuario.pk]),
        )
    return doc


@transaction.atomic
def eliminar_documento(doc):
    if doc.docv_estado == Doc.APROBADO:
        raise ValidationError("Un documento aprobado no puede eliminarse.")
    usuario = doc.usuario
    copia = Doc(docv_ruta=doc.docv_ruta)
    doc.delete()
    transaction.on_commit(lambda: _borrar_archivo(copia))
    recalcular_verificacion(usuario)


def _estado_verif(usuario):
    if not usuario.es_beneficiario:
        return None
    return PerfilBeneficiario.objects.get(pk=usuario.pk).ben_estado_verif


def recalcular_verificacion(usuario):
    """Pendiente → En revisión → Verificado / Rechazado según sus documentos obligatorios."""
    if not usuario.es_beneficiario:
        return None
    perfil = PerfilBeneficiario.objects.select_for_update().get(pk=usuario.pk)
    estados = dict(Doc.objects.filter(usuario=usuario).values_list("docv_tipo", "docv_estado"))
    requeridos = [estados.get(t) for t in tipos_obligatorios(usuario)]
    if requeridos and all(e == Doc.APROBADO for e in requeridos):
        nuevo = PerfilBeneficiario.VERIFICADO
    elif any(e == Doc.RECHAZADO for e in requeridos):
        nuevo = PerfilBeneficiario.RECHAZADO
    elif all(e in (Doc.CARGADO, Doc.APROBADO) for e in requeridos):
        nuevo = PerfilBeneficiario.EN_REVISION
    else:
        nuevo = PerfilBeneficiario.PENDIENTE
    if nuevo != perfil.ben_estado_verif:
        perfil.ben_estado_verif = nuevo
        perfil.ben_fec_verif = (
            timezone.now() if nuevo in (PerfilBeneficiario.VERIFICADO, PerfilBeneficiario.RECHAZADO) else None
        )
        perfil.save(update_fields=["ben_estado_verif", "ben_fec_verif"])
        usuario.perfil_beneficiario = perfil
    return nuevo


@transaction.atomic
def revisar_documento(doc, admin, aprobar, observacion=""):
    """Decisión del administrador. Puede confirmar o revertir una decisión automática."""
    if doc.docv_estado == Doc.APROBADO and not (doc.docv_verif_auto and not aprobar):
        raise ValidationError("El documento ya está aprobado.")
    if not aprobar and not observacion.strip():
        raise ValidationError("Indique el motivo del rechazo.")
    doc.docv_verif_auto = False
    return _resolver(doc, aprobar, observacion.strip(), admin)


@transaction.atomic
def resolver_automaticamente(doc, aprobar, observacion):
    """Decisión del sistema (semáforo verde o rojo). Queda marcada como automática."""
    doc.docv_verif_auto = True
    return _resolver(doc, aprobar, observacion, None)


def _resolver(doc, aprobar, observacion, admin):
    doc.docv_estado = Doc.APROBADO if aprobar else Doc.RECHAZADO
    doc.docv_obs = observacion
    doc.revisor = admin
    doc.docv_fec_revision = timezone.now()
    doc.save()
    usuario = doc.usuario
    anterior = _estado_verif(usuario)
    nuevo = recalcular_verificacion(usuario)
    url = reverse("usuarios:documentos")
    if aprobar:
        texto = "fue pre-aprobado automáticamente" if admin is None else "fue aprobado"
        notificar(usuario, "documento", "Documento aprobado", f"Su {doc.get_docv_tipo_display().lower()} {texto}.", url)
    else:
        notificar(
            usuario,
            "documento",
            "Documento rechazado",
            f"Su {doc.get_docv_tipo_display().lower()} fue rechazado. Motivo: {doc.docv_obs}. Puede volver a cargarlo.",
            url,
        )
    if nuevo == PerfilBeneficiario.VERIFICADO and anterior != nuevo:
        notificar(
            usuario,
            "cuenta",
            "Cuenta verificada",
            "Sus documentos fueron aprobados. Ya puede consultar el catálogo y enviar solicitudes.",
            reverse("solicitudes:catalogo"),
        )
    return doc


def controlar_documentos_vencidos(hoy=None):
    """Marca como vencidos los documentos cuya fecha de vencimiento pasó."""
    hoy = hoy or timezone.localdate()
    vencidos = Doc.objects.filter(docv_fec_venc__lt=hoy, docv_estado__in=[Doc.CARGADO, Doc.APROBADO]).select_related(
        "usuario"
    )
    total = 0
    for doc in vencidos:
        with transaction.atomic():
            doc.docv_estado = Doc.VENCIDO
            doc.save(update_fields=["docv_estado"])
            recalcular_verificacion(doc.usuario)
            notificar(
                doc.usuario,
                "documento",
                "Documento vencido",
                f"Su {doc.get_docv_tipo_display().lower()} venció. Cargue una versión vigente.",
                reverse("usuarios:documentos"),
            )
        total += 1
    return total


def resumen_documentos(usuario):
    """Lista de tipos aplicables con su documento (o None) para la vista del titular."""
    docs = {d.docv_tipo: d for d in Doc.objects.filter(usuario=usuario)}
    obligatorios = tipos_obligatorios(usuario)
    etiquetas = dict(Doc.TIPOS)
    return [
        {"tipo": t, "nombre": etiquetas[t], "doc": docs.get(t), "obligatorio": t in obligatorios}
        for t in tipos_permitidos(usuario)
    ]


def usuario_tiene_registros(usuario):
    return (
        usuario.documentos.exists()
        or usuario.donaciones.exists()
        or usuario.solicitudes.exists()
        or usuario.bodegas.exists()
        or Usuario.objects.filter(pk=usuario.pk, last_login__isnull=False).exists()
    )
