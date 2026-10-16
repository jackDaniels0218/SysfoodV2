import logging

from django.utils import timezone

from .tareas import ejecutar_control_diario

log = logging.getLogger("sysfood")


class ControlVencimientosMiddleware:
    """Garantiza que el control de vencimientos corra al menos una vez al día,
    aunque no se haya programado la tarea en el sistema operativo."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.ultimo_dia = None

    def __call__(self, request):
        hoy = timezone.localdate()
        if self.ultimo_dia != hoy and not request.path.startswith("/static/"):
            try:
                ejecutar_control_diario()
                self.ultimo_dia = hoy
            except Exception:  # Nunca bloquear la navegación por el proceso automático.
                log.exception("Falló el control diario de vencimientos")
        return self.get_response(request)
