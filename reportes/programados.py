"""Envío por correo de los reportes programados (tarea horaria `reportes_programados`)."""

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from core import parametros
from core.servicios import auditar

from . import consultas, exportar
from .models import ReporteProgramado

log = logging.getLogger("sysfood")

NOMBRES_FILTROS = {
    "desde": "Desde",
    "hasta": "Hasta",
    "estado": "Estado",
    "categoria": "Categoría",
    "donante": "Donante",
    "bodega": "Bodega",
}


def filtros_de(reporte, ahora=None):
    """Filtros del envío: los guardados y, si es relativo, el último periodo como rango de fechas."""
    filtros = {k: v for k, v in (reporte.rep_filtros or {}).items() if k in consultas.TODOS_LOS_FILTROS}
    if reporte.rep_relativo:
        ahora = timezone.localtime(ahora or timezone.now())
        filtros["desde"] = (ahora - ReporteProgramado.PERIODOS[reporte.rep_frecuencia]).date().isoformat()
        filtros["hasta"] = ahora.date().isoformat()
    return filtros


def texto_filtros(filtros):
    if not filtros:
        return "Filtros: ninguno."
    return "Filtros: " + ", ".join(f"{NOMBRES_FILTROS.get(k, k)}: {v}" for k, v in filtros.items()) + "."


def enviar(reporte, usuario=None, ahora=None):
    """Genera el archivo y lo envía. Devuelve (ok, mensaje) y lo deja en la bitácora."""
    ahora = ahora or timezone.now()
    if reporte.rep_estadistica not in consultas.ESTADISTICAS:
        ok, mensaje = False, "La estadística ya no existe."
    elif not reporte.lista_destinatarios:
        ok, mensaje = False, "No tiene destinatarios."
    else:
        filtros = filtros_de(reporte, ahora)
        texto = texto_filtros(filtros)
        datos = consultas.generar(reporte.rep_estadistica, filtros)
        contenido = exportar.generar_archivo(datos, reporte.rep_formato, texto)
        tipo_mime = exportar.FORMATOS[reporte.rep_formato][0].split(";")[0]
        nombre = f"sysfood_{reporte.rep_estadistica}_{timezone.localtime(ahora):%Y%m%d}.{reporte.rep_formato}"
        cuerpo = (
            f"Adjunto encontrará el reporte «{datos['titulo']}» generado el {datos['generado']}.\n"
            f"{texto}\nRegistros: {len(datos['filas'])}.\n\n"
            + "\n".join(f"- {a}: {b}" for a, b in datos["resumen"][:8])
            + f"\n\nVer en SysFood: {settings.SITE_URL}/reportes/?tipo={reporte.rep_estadistica}\n"
            "Este envío se configura en Sistema › Reportes › Envíos programados."
        )
        correo = EmailMessage(
            f"[SysFood] {datos['titulo']}", cuerpo, settings.DEFAULT_FROM_EMAIL, reporte.lista_destinatarios
        )
        correo.attach(nombre, contenido, tipo_mime)
        try:
            correo.send(fail_silently=False)
            ok, mensaje = (
                True,
                f"Enviado a {len(reporte.lista_destinatarios)} destinatario(s) con {len(datos['filas'])} registro(s).",
            )
        except Exception as exc:  # El servidor de correo puede fallar: se reintenta en la siguiente hora.
            log.warning("No se pudo enviar el reporte programado %s: %s", reporte.pk, exc)
            ok, mensaje = False, f"Error de correo: {exc}"
    campos = ["rep_resultado"]
    reporte.rep_resultado = mensaje[:255]
    if ok:
        reporte.rep_ultimo_envio = ahora
        campos.append("rep_ultimo_envio")
    reporte.save(update_fields=campos)
    auditar(
        None, "envio_reporte", "reporte_programado", reporte.pk, f"{reporte.titulo}: {mensaje}"[:500], usuario=usuario
    )
    return ok, mensaje


def tarea_envios(ahora=None):
    """Envía los reportes activos que ya cumplieron su periodo, a partir de la hora configurada."""
    ahora = ahora or timezone.now()
    if timezone.localtime(ahora).hour < parametros.entero("reportes_hora_envio"):
        return {"enviados": 0, "pendientes": "antes de la hora de envío"}
    enviados = fallidos = 0
    for reporte in ReporteProgramado.objects.filter(rep_activo=True):
        if reporte.vencido(ahora):
            ok, _ = enviar(reporte, ahora=ahora)
            enviados += ok
            fallidos += not ok
    return {"enviados": enviados, "fallidos": fallidos}
