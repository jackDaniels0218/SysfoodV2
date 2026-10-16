import secrets
import string

from django.conf import settings
from django.db import models

from core.models import _SoloInsercion


def generar_codigo():
    alfabeto = string.ascii_uppercase + string.digits
    while True:
        codigo = "SF-" + "".join(secrets.choice(alfabeto) for _ in range(8))
        if not Entrega.objects.filter(ent_cod=codigo).exists():
            return codigo


class Entrega(models.Model):
    """Entrega generada al aprobar una solicitud (Actividad 8)."""

    EN_REVISION, EN_BODEGA, EN_ENTREGA, ENTREGADO, CANCELADO = "en_revision", "en_bodega", "en_entrega", "entregado", "cancelado"
    ESTADOS = [
        (EN_REVISION, "En revisión"), (EN_BODEGA, "En bodega"), (EN_ENTREGA, "En entrega"),
        (ENTREGADO, "Entregado"), (CANCELADO, "Cancelado"),
    ]
    SIGUIENTE = {EN_REVISION: EN_BODEGA, EN_BODEGA: EN_ENTREGA, EN_ENTREGA: ENTREGADO}
    RECOGIDA, DOMICILIO = "recogida", "domicilio"
    MODALIDADES = [(RECOGIDA, "Recogida en bodega"), (DOMICILIO, "Entrega a domicilio")]

    ent_id = models.AutoField(primary_key=True)
    solicitud = models.OneToOneField(
        "solicitudes.Solicitud", on_delete=models.PROTECT, db_column="sol_id", related_name="entrega",
    )
    bodega = models.ForeignKey("catalogo.Bodega", on_delete=models.PROTECT, db_column="bod_id", related_name="entregas")
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column="usu_id_resp", related_name="+",
    )
    ent_cod = models.CharField("código de seguimiento", max_length=12, unique=True, default=generar_codigo)
    ent_modalidad = models.CharField("modalidad", max_length=10, choices=MODALIDADES, default=RECOGIDA)
    ent_dir_entrega = models.CharField("dirección de entrega", max_length=200, blank=True)
    ent_estado = models.CharField("estado", max_length=12, choices=ESTADOS, default=EN_REVISION, db_index=True)
    ent_fec_prog = models.DateField("fecha programada", null=True, blank=True)
    ent_fec_entrega = models.DateTimeField("fecha de entrega", null=True, blank=True)
    ent_mot_cancel = models.CharField("motivo de cancelación", max_length=255, blank=True)
    ent_obs = models.TextField("observaciones", blank=True)
    ent_fec_crea = models.DateTimeField("fecha de creación", auto_now_add=True, db_index=True)

    class Meta:
        db_table = "entrega"
        ordering = ["-ent_fec_crea"]

    def __str__(self):
        return self.ent_cod

    @property
    def siguiente_estado(self):
        return self.SIGUIENTE.get(self.ent_estado)

    @property
    def cancelable(self):
        return self.ent_estado not in (self.ENTREGADO, self.CANCELADO)

    @property
    def paso(self):
        orden = [self.EN_REVISION, self.EN_BODEGA, self.EN_ENTREGA, self.ENTREGADO]
        return orden.index(self.ent_estado) + 1 if self.ent_estado in orden else 0


class EntregaDetalle(models.Model):
    de_id = models.AutoField(primary_key=True)
    entrega = models.ForeignKey(Entrega, on_delete=models.PROTECT, db_column="ent_id", related_name="detalles")
    inventario = models.ForeignKey("inventario.Inventario", on_delete=models.PROTECT, db_column="inv_id", related_name="+")
    de_cant_asig = models.DecimalField("cantidad asignada", max_digits=12, decimal_places=2)
    de_cant_entregada = models.DecimalField("cantidad entregada", max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = "entrega_detalle"


class HistorialEntrega(_SoloInsercion):
    """Historial de estados de la entrega. Solo inserción."""

    his_id = models.BigAutoField(primary_key=True)
    entrega = models.ForeignKey(Entrega, on_delete=models.PROTECT, db_column="ent_id", related_name="historial")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, db_column="usu_id", related_name="+")
    his_estado_ant = models.CharField("estado anterior", max_length=12, blank=True)
    his_estado_nuevo = models.CharField("estado nuevo", max_length=12)
    his_obs = models.CharField("observación", max_length=255, blank=True)
    his_fecha = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        db_table = "historial_entrega"
        ordering = ["his_fecha", "his_id"]

    def nombre_estado(self, valor):
        return dict(Entrega.ESTADOS).get(valor, valor or "—")

    @property
    def anterior_display(self):
        return self.nombre_estado(self.his_estado_ant)

    @property
    def nuevo_display(self):
        return self.nombre_estado(self.his_estado_nuevo)
