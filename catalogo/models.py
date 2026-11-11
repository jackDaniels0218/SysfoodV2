from django.conf import settings
from django.db import models


class Categoria(models.Model):
    """Categorías de producto (Actividad 3)."""

    ESTADOS = [("activa", "Activa"), ("inactiva", "Inactiva")]

    cat_id = models.AutoField(primary_key=True)
    cat_nom = models.CharField("nombre", max_length=80, unique=True)
    cat_desc = models.CharField("descripción", max_length=255, blank=True)
    cat_perecedero = models.BooleanField("producto perecedero", default=False)
    cat_dias_alerta = models.PositiveSmallIntegerField(
        "días de alerta de vencimiento",
        null=True,
        blank=True,
        help_text="Si se deja vacío se usa el valor general de los parámetros.",
    )
    cat_estado = models.CharField("estado", max_length=10, choices=ESTADOS, default="activa")

    class Meta:
        db_table = "categoria"
        ordering = ["cat_nom"]
        verbose_name = "categoría"

    def __str__(self):
        return self.cat_nom

    def dias_alerta(self):
        from core import parametros

        return (
            self.cat_dias_alerta if self.cat_dias_alerta is not None else parametros.entero("dias_alerta_vencimiento")
        )


class Bodega(models.Model):
    """Lugares físicos de almacenamiento (Actividad 4)."""

    ESTADOS = [("activa", "Activa"), ("inactiva", "Inactiva")]

    bod_id = models.AutoField(primary_key=True)
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="usu_id_resp",
        related_name="bodegas",
        verbose_name="responsable",
    )
    bod_nom = models.CharField("nombre", max_length=100, unique=True)
    bod_dir = models.CharField("dirección", max_length=200)
    bod_capacidad = models.CharField("capacidad estimada", max_length=100, help_text="Por ejemplo: 500 kg, 20 m³")
    bod_estado = models.CharField("estado", max_length=10, choices=ESTADOS, default="activa")

    class Meta:
        db_table = "bodega"
        ordering = ["bod_nom"]

    def __str__(self):
        return self.bod_nom
