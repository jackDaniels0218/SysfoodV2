import logging

from django.utils import timezone

from .tareas import ejecutar_control_diario, lanzar_en_segundo_plano

log = logging.getLogger("sysfood")


class ControlVencimientosMiddleware:
    """Garantiza que los procesos automáticos corran aunque no se haya programado
    la tarea en el sistema operativo: el control de vencimientos, una vez al día y
    antes de atender la primera petición; las demás tareas, en segundo plano."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.ultimo_dia = None

    def __call__(self, request):
        if not request.path.startswith("/static/"):
            hoy = timezone.localdate()
            if self.ultimo_dia != hoy:
                try:
                    ejecutar_control_diario()
                    self.ultimo_dia = hoy
                except Exception:  # Nunca bloquear la navegación por el proceso automático.
                    log.exception("Falló el control diario de vencimientos")
            lanzar_en_segundo_plano()
        return self.get_response(request)
