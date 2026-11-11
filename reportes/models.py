from datetime import timedelta

from django.conf import settings
from django.db import models


class ReporteProgramado(models.Model):
    """Envío automático por correo de una estadística, con sus filtros, cada día, semana o mes."""

    DIARIA, SEMANAL, MENSUAL = "diaria", "semanal", "mensual"
    FRECUENCIAS = [(DIARIA, "Cada día"), (SEMANAL, "Cada semana"), (MENSUAL, "Cada mes")]
    PERIODOS = {DIARIA: timedelta(days=1), SEMANAL: timedelta(days=7), MENSUAL: timedelta(days=30)}
    FORMATOS = [("pdf", "PDF"), ("xlsx", "Excel"), ("csv", "CSV")]

    rep_id = models.AutoField(primary_key=True)
    creador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column="usu_id", related_name="+")
    rep_estadistica = models.CharField("estadística", max_length=40)
    rep_filtros = models.JSONField("filtros", default=dict, blank=True)
    rep_relativo = models.BooleanField(
        "solo el último periodo", default=True,
        help_text="Si está marcado, cada envío cubre el último día, semana o mes en lugar de las fechas fijas.",
    )
    rep_frecuencia = models.CharField("frecuencia", max_length=10, choices=FRECUENCIAS, default=SEMANAL)
    rep_formato = models.CharField("formato", max_length=5, choices=FORMATOS, default="pdf")
    rep_destinatarios = models.CharField("destinatarios", max_length=500, help_text="Correos separados por comas.")
    rep_activo = models.BooleanField("activo", default=True)
    rep_ultimo_envio = models.DateTimeField("último envío", null=True, blank=True)
    rep_resultado = models.CharField("resultado del último envío", max_length=255, blank=True)
    rep_fecha_crea = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        db_table = "reporte_programado"
        ordering = ["rep_estadistica", "rep_id"]
        verbose_name = "reporte programado"

    def __str__(self):
        return f"{self.titulo} ({self.get_rep_frecuencia_display().lower()})"

    @property
    def titulo(self):
        from .consultas import TIPOS

        return TIPOS.get(self.rep_estadistica, self.rep_estadistica)

    @property
    def lista_destinatarios(self):
        return [c.strip() for c in self.rep_destinatarios.split(",") if c.strip()]

    def vencido(self, ahora):
        if self.rep_ultimo_envio is None:
            return True
        # Margen de una hora para que la hora de envío no se corra un poco cada vez.
        return ahora - self.rep_ultimo_envio >= self.PERIODOS[self.rep_frecuencia] - timedelta(hours=1)
