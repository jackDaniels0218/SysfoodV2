"""Procesos automáticos (tareas programadas).

Cada tarea se declara en REGISTRO con su frecuencia. Se ejecutan:
  * con `python manage.py ejecutar_tareas` (para cron o el Programador de tareas de Windows);
  * en Docker, con el ciclo del contenedor (docker/entrypoint.sh), cada hora;
  * y, como respaldo, desde el middleware cuando alguien navega el sistema.
Una tarea nunca corre dos veces en el mismo periodo: la fecha de la última
ejecución se guarda en la tabla tarea_programada con bloqueo de fila.
"""
import logging
import threading
import time
from collections import OrderedDict, namedtuple
from datetime import timedelta
from importlib import import_module

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from .models import TareaProgramada

log = logging.getLogger("sysfood")
CONTROL_DIARIO = "control_vencimientos"

Tarea = namedtuple("Tarea", "nombre titulo frecuencia funcion descripcion")

REGISTRO = OrderedDict((t.nombre, t) for t in [
    Tarea(CONTROL_DIARIO, "Control de vencimientos", "diaria", "core.tareas._control_vencimientos",
          "Asigna la vigencia del inventario, marca documentos vencidos y avisa a donantes y administradores."),
    Tarea("recalculo_puntajes", "Recálculo nocturno de puntajes", "diaria", "usuarios.puntaje.tarea_recalculo_nocturno",
          "Recalcula el puntaje de necesidad de todos los beneficiarios (el tiempo sin ayuda cambia cada día) y reasigna su grupo."),
    Tarea("geocodificacion", "Geocodificación de direcciones", "horaria", "usuarios.ubicacion.tarea_geocodificacion",
          "Ubica en el mapa a los beneficiarios pendientes y reintenta los fallidos; tras varios fallos los marca para revisión."),
    Tarea("verificacion_documentos", "Lectura automática de documentos", "horaria", "usuarios.verificacion.tarea_pendientes",
          "Lee con OCR los documentos que quedaron sin leer (por ejemplo, si el servicio no estaba disponible) y aplica el semáforo."),
    Tarea("reportes_programados", "Envío de reportes programados", "horaria", "reportes.programados.tarea_envios",
          "Envía por correo los reportes programados que ya cumplieron su periodo (desde la hora reportes_hora_envio)."),
    Tarea("limpieza_chat", "Limpieza de consultas del asistente", "diaria", "asistente.motor.tarea_limpieza",
          "Borra las consultas del asistente más antiguas que la retención configurada (chat_retencion_dias)."),
])

PERIODOS = {"diaria": timedelta(days=1), "horaria": timedelta(hours=1)}


def _funcion(tarea):
    modulo, nombre = tarea.funcion.rsplit(".", 1)
    return getattr(import_module(modulo), nombre)


def _vencida(tarea, ultima, ahora):
    if ultima is None:
        return True
    if tarea.frecuencia == "diaria":
        return timezone.localdate(ultima) < timezone.localdate(ahora)
    return ahora - ultima >= PERIODOS[tarea.frecuencia]


def _resumen(resultado):
    if resultado is None:
        return "Sin cambios"
    if isinstance(resultado, dict):
        return ", ".join(f"{k}: {v}" for k, v in resultado.items())[:255]
    return str(resultado)[:255]


def ejecutar(nombre, forzar=False):
    """Ejecuta la tarea si le corresponde (o siempre, con forzar). Devuelve su resultado o None si no tocaba."""
    tarea = REGISTRO[nombre]
    ahora = timezone.now()
    with transaction.atomic():
        registro, _ = TareaProgramada.objects.select_for_update().get_or_create(tar_nombre=nombre)
        if not forzar and not _vencida(tarea, registro.tar_ult_ejecucion, ahora):
            return None
        registro.tar_ult_ejecucion = ahora
        registro.save(update_fields=["tar_ult_ejecucion"])
    inicio = time.monotonic()
    try:
        resultado = _funcion(tarea)()
    except Exception as error:
        TareaProgramada.objects.filter(pk=nombre).update(tar_resultado=f"Error: {error}"[:255], tar_duracion_ms=0)
        raise
    TareaProgramada.objects.filter(pk=nombre).update(
        tar_resultado=_resumen(resultado), tar_duracion_ms=int((time.monotonic() - inicio) * 1000),
    )
    log.info("Tarea %s ejecutada: %s", nombre, _resumen(resultado))
    return resultado


def ejecutar_pendientes(excluir=()):
    """Ejecuta todas las tareas que estén al día de vencer. Un fallo no detiene a las demás."""
    resultados = {}
    for nombre in REGISTRO:
        if nombre in excluir:
            continue
        try:
            resultado = ejecutar(nombre)
        except Exception:
            log.exception("Falló la tarea %s", nombre)
            resultados[nombre] = "error"
            continue
        if resultado is not None:
            resultados[nombre] = resultado
    return resultados


_hilo_candado = threading.Lock()
_ultimo_lanzamiento = [0.0]


def lanzar_en_segundo_plano(cada_segundos=600):
    """Lanza ejecutar_pendientes en un hilo, como mucho una vez cada `cada_segundos` por proceso."""
    if not getattr(settings, "TAREAS_AUTOMATICAS", True):
        return False
    with _hilo_candado:
        if time.monotonic() - _ultimo_lanzamiento[0] < cada_segundos:
            return False
        _ultimo_lanzamiento[0] = time.monotonic()

    def correr():
        try:
            ejecutar_pendientes(excluir=(CONTROL_DIARIO,))
        except Exception:
            log.exception("Falló la ejecución en segundo plano de las tareas")
        finally:
            close_old_connections()

    threading.Thread(target=correr, name="sysfood-tareas", daemon=True).start()
    return True


# ---------------------------------------------------------------- Tareas del núcleo

def _control_vencimientos():
    from inventario.servicios import controlar_vencimientos
    from usuarios.servicios import controlar_documentos_vencidos

    hoy = timezone.localdate()
    resultado = controlar_vencimientos(hoy)
    resultado["documentos_vencidos"] = controlar_documentos_vencidos(hoy)
    return resultado


def ejecutar_control_diario(forzar=False):
    """Control de vencimientos de inventario y documentos. Una vez al día como mínimo."""
    return ejecutar(CONTROL_DIARIO, forzar=forzar)


def ultima_ejecucion(nombre=CONTROL_DIARIO):
    tarea = TareaProgramada.objects.filter(tar_nombre=nombre).first()
    return tarea.tar_ult_ejecucion if tarea else None


def estado():
    """Lista de tareas con su última ejecución, para la página de administración."""
    registros = {t.tar_nombre: t for t in TareaProgramada.objects.all()}
    filas = []
    for tarea in REGISTRO.values():
        r = registros.get(tarea.nombre)
        filas.append({
            "tarea": tarea, "ultima": r.tar_ult_ejecucion if r else None,
            "resultado": r.tar_resultado if r else "", "duracion": r.tar_duracion_ms if r else None,
        })
    return filas
