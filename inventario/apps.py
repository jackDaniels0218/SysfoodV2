from django.apps import AppConfig


class Config(AppConfig):
    name = "inventario"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import unidades  # noqa: F401  (registra la reacción a los cambios de unidades)
