"""Verificación automática de documentos por semáforo.

  verde   (confianza ≥ ocr_umbral_alto)  → pre-aprobado automáticamente
  amarillo (entre los umbrales)          → cola del administrador, con las discrepancias resaltadas
  rojo    (confianza < ocr_umbral_bajo o ilegible) → rechazado automáticamente con el motivo

El flujo manual siempre funciona: si el OCR no está disponible, falla o no es
concluyente, el documento queda «Cargado» y el administrador decide como siempre.
Toda decisión automática queda en la bitácora con su confianza y su motivo.
"""

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core import parametros
from core.formato import numero
from core.servicios import auditar

from . import ocr
from .models import DocumentoValidacion as Doc

log = logging.getLogger("sysfood")
TIPOS_VERIFICABLES = (Doc.IDENTIDAD, Doc.SISBEN, Doc.RESIDENCIA, Doc.DISCAPACIDAD)
MAX_INTENTOS = 3


def aplica(usuario, tipo):
    return usuario.es_beneficiario and tipo in TIPOS_VERIFICABLES


def revisar_calidad(contenido, mime):
    """Revisión inmediata al cargar. Lanza ValidationError para pedir otra foto; devuelve las métricas."""
    if not parametros.booleano("ocr_activo") or not mime.startswith("image/"):
        return None
    try:
        imagen = ocr.imagenes(contenido, mime)[0]
    except ocr.ImagenIlegible as error:
        raise ValidationError(f"{error} Tome la foto de nuevo o cargue otro archivo.") from error
    calidad = ocr.calidad(imagen)
    if not calidad["legible"]:
        raise ValidationError(
            "No pudimos aceptar la foto: " + "; ".join(calidad["problemas"]) + ". Por favor tómela de nuevo."
        )
    return calidad


def _guardar(doc, **campos):
    Doc.objects.filter(pk=doc.pk).update(**campos)
    for k, v in campos.items():
        setattr(doc, k, v)


def decidir(confianza, legible, cfg=None):
    cfg = cfg or {}
    alto = cfg.get("alto", parametros.entero("ocr_umbral_alto"))
    bajo = cfg.get("bajo", parametros.entero("ocr_umbral_bajo"))
    if not legible:
        return Doc.ILEGIBLE
    if confianza >= alto:
        return Doc.ALTA
    if confianza >= bajo:
        return Doc.MEDIA
    return Doc.BAJA


def verificar(doc, motivo="Carga del documento"):
    """Lee el documento, lo compara con los datos registrados y aplica el semáforo. Nunca lanza excepciones."""

    doc = Doc.objects.select_related("usuario__perfil_beneficiario").get(pk=doc.pk)
    if not aplica(doc.usuario, doc.docv_tipo) or doc.docv_estado != Doc.CARGADO:
        return None
    if not parametros.booleano("ocr_activo"):
        _guardar(
            doc,
            docv_ocr_estado=Doc.OCR_NO_DISPONIBLE,
            docv_ocr_resultado={**doc.docv_ocr_resultado, "motivo": "Desactivada en Parámetros"},
        )
        return None
    listo, detalle = ocr.disponible()
    if not listo:
        _guardar(
            doc, docv_ocr_estado=Doc.OCR_NO_DISPONIBLE, docv_ocr_resultado={**doc.docv_ocr_resultado, "motivo": detalle}
        )
        auditar(
            None,
            "verificacion_auto",
            "documento_validacion",
            doc.pk,
            f"{doc.get_docv_tipo_display()}: lectura automática no disponible ({detalle}). Queda para revisión manual.",
        )
        return None

    intentos = doc.docv_ocr_intentos + 1
    try:
        contenido = doc.ruta_absoluta.read_bytes()
        paginas = ocr.imagenes(contenido, doc.docv_mime)
        calidad = ocr.calidad(paginas[0])
        texto, confianza_ocr = ocr.leer(paginas)
    except ocr.ImagenIlegible as error:
        texto, confianza_ocr, calidad = "", 0, {"legible": False, "problemas": [str(error)]}
    except (ocr.ErrorOCR, OSError) as error:
        estado = Doc.OCR_ERROR if intentos < MAX_INTENTOS else Doc.OCR_NO_DISPONIBLE
        _guardar(
            doc,
            docv_ocr_estado=estado,
            docv_ocr_intentos=intentos,
            docv_ocr_resultado={**doc.docv_ocr_resultado, "motivo": str(error)},
        )
        auditar(
            None,
            "verificacion_auto",
            "documento_validacion",
            doc.pk,
            f"{doc.get_docv_tipo_display()}: la lectura falló ({error}). "
            f"{'Se reintentará.' if estado == Doc.OCR_ERROR else 'Queda para revisión manual.'}",
        )
        return None
    except Exception as error:  # Nunca romper la carga por la verificación.
        log.exception("Error inesperado en la verificación del documento %s", doc.pk)
        _guardar(
            doc,
            docv_ocr_estado=Doc.OCR_ERROR,
            docv_ocr_intentos=intentos,
            docv_ocr_resultado={**doc.docv_ocr_resultado, "motivo": f"Error inesperado: {error}"},
        )
        return None

    filas = ocr.comparar(doc, texto)
    legible = calidad.get("legible", True) and len(texto) >= 15 and confianza_ocr >= 20
    if not legible and calidad.get("legible", True):
        calidad = {
            **calidad,
            "legible": False,
            "problemas": calidad.get("problemas", []) + ["no se distingue texto en el documento"],
        }
    conf = ocr.confianza(filas, confianza_ocr) if legible else 0.0
    decision = decidir(conf, legible)
    if decision == Doc.ALTA and ocr.incumple_obligatorios(filas):
        decision = Doc.MEDIA  # Va a la cola del administrador con la discrepancia resaltada.
    resultado = {
        "campos": filas,
        "calidad": calidad,
        "confianza_ocr": confianza_ocr,
        "motor": detalle,
        "umbral_alto": parametros.entero("ocr_umbral_alto"),
        "umbral_bajo": parametros.entero("ocr_umbral_bajo"),
    }
    extra = {}
    if doc.docv_tipo == Doc.SISBEN and not doc.docv_fec_venc:
        vigencia = ocr.vigencia_sisben(texto)
        if vigencia:
            extra["docv_fec_venc"] = vigencia  # El documento vence cuando se acabe la vigencia del certificado.
    with transaction.atomic():
        _guardar(
            doc,
            **extra,
            docv_ocr_estado=Doc.OCR_PROCESADO,
            docv_ocr_texto=texto[:20000],
            docv_ocr_confianza=conf,
            docv_ocr_resultado=resultado,
            docv_decision_auto=decision,
            docv_ocr_intentos=intentos,
            docv_fec_ocr=timezone.now(),
        )
        accion = aplicar_decision(doc, decision, conf, filas, calidad)
        auditar(
            None,
            "verificacion_auto",
            "documento_validacion",
            doc.pk,
            f"{doc.get_docv_tipo_display()} de {doc.usuario.nombre_completo}: confianza {numero(conf)} % "
            f"({dict(Doc.DECISIONES)[decision].lower()}). {accion} Campos: "
            + "; ".join(
                f"{f['etiqueta']} {'coincide' if f['coincide'] >= 1 else 'no coincide' if not f['coincide'] else 'coincide parcialmente'}"
                for f in filas
            )
            + f". Motivo: {motivo}.",
        )
    return decision


def _motivo_rechazo(filas, calidad):
    if not calidad.get("legible", True):
        return (
            "El documento es ilegible: "
            + "; ".join(calidad.get("problemas", []))
            + ". Cargue una imagen nítida y completa."
        )
    faltan = [f["etiqueta"].lower() for f in filas if not f["coincide"]]
    return (
        "No se pudo confirmar " + ", ".join(faltan) + " frente a los datos registrados. "
        "Verifique que cargó el documento correcto y que se lea completo."
    )


def aplicar_decision(doc, decision, conf, filas, calidad):
    """Aplica el semáforo. Devuelve el texto de la acción para la bitácora."""
    from . import servicios

    if decision == Doc.ALTA and parametros.booleano("ocr_auto_aprobar"):
        servicios.resolver_automaticamente(doc, True, f"Pre-aprobado automáticamente (confianza {numero(conf)} %).")
        return "Pre-aprobado automáticamente."
    if decision in (Doc.BAJA, Doc.ILEGIBLE) and parametros.booleano("ocr_auto_rechazar"):
        servicios.resolver_automaticamente(doc, False, "Rechazado automáticamente. " + _motivo_rechazo(filas, calidad))
        return "Rechazado automáticamente."
    return "Enviado a la cola del administrador con las discrepancias resaltadas."


def tarea_pendientes():
    resumen = {"leidos": 0, "sin_motor": 0}
    pendientes = Doc.objects.filter(
        docv_estado=Doc.CARGADO,
        docv_ocr_estado__in=[Doc.OCR_PENDIENTE, Doc.OCR_ERROR, Doc.OCR_NO_DISPONIBLE],
        docv_ocr_intentos__lt=MAX_INTENTOS,
    )
    if not parametros.booleano("ocr_activo") or not ocr.disponible()[0]:
        return {"leidos": 0, "sin_motor": pendientes.count()}
    for doc in pendientes[:100]:
        if verificar(doc, "Lectura programada") is not None:
            resumen["leidos"] += 1
    return resumen
