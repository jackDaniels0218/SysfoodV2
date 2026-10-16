"""Procesos automáticos diarios."""
import logging
import threading

from django.db import transaction
from django.utils import timezone

from .models import TareaProgramada

log = logging.getLogger("sysfood")
CONTROL_DIARIO = "control_vencimientos"
_candado = threading.Lock()


def ejecutar_control_diario(forzar=False):
    """Control de vencimientos de inventario y documentos. Una vez al día como mínimo."""
    from inventario.servicios import controlar_vencimientos
    from usuarios.servicios import controlar_documentos_vencidos

    hoy = timezone.localdate()
    with transaction.atomic():
        tarea, _ = TareaProgramada.objects.select_for_update().get_or_create(tar_nombre=CONTROL_DIARIO)
        if not forzar and tarea.tar_ult_ejecucion and timezone.localdate(tarea.tar_ult_ejecucion) >= hoy:
            return None
        tarea.tar_ult_ejecucion = timezone.now()
        tarea.save()
    resultado = controlar_vencimientos(hoy)
    resultado["documentos_vencidos"] = controlar_documentos_vencidos(hoy)
    log.info("Control de vencimientos ejecutado: %s", resultado)
    return resultado


def ultima_ejecucion():
    tarea = TareaProgramada.objects.filter(tar_nombre=CONTROL_DIARIO).first()
    return tarea.tar_ult_ejecucion if tarea else None
