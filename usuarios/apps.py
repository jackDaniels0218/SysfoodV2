from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _puntajes_faltantes(sender, **kwargs):
    """Después de migrar, calcula el puntaje de los beneficiarios que aún no lo tienen (datos existentes)."""
    from . import puntaje
    from .models import PerfilBeneficiario

    try:
        pendientes = list(PerfilBeneficiario.objects.filter(ben_puntaje__isnull=True))
    except Exception:  # La tabla aún no existe (migración parcial).
        return
    if pendientes:
        cfg = puntaje.Config()
        for perfil in pendientes:
            puntaje.recalcular(perfil, "Cálculo inicial tras la actualización del sistema", cfg)


class Config(AppConfig):
    name = "usuarios"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import (
            puntaje,  # noqa: F401  Registra la reacción a los cambios de parámetros.
            senales,
        )

        senales.conectar()
        post_migrate.connect(_puntajes_faltantes, sender=self)
