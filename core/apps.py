from contextlib import suppress

from django.apps import AppConfig
from django.db import OperationalError, ProgrammingError
from django.db.models.signals import post_migrate


def _sincronizar_parametros(sender, **kwargs):
    """Crea los parámetros nuevos declarados en core.parametros después de cada migrate."""
    from . import parametros

    # La tabla puede no existir todavía (por ejemplo, al migrar hacia atrás).
    with suppress(OperationalError, ProgrammingError):
        parametros.sincronizar()


class Config(AppConfig):
    name = "core"
    verbose_name = "Núcleo"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        post_migrate.connect(_sincronizar_parametros, sender=self)
