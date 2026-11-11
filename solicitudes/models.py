from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class CarritoItem(models.Model):
    """Carrito temporal del beneficiario (Actividad 11). No tiene CRUD."""

    car_id = models.AutoField(primary_key=True)
    beneficiario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="usu_id",
        related_name="carrito",
    )
    inventario = models.ForeignKey(
        "inventario.Inventario", on_delete=models.CASCADE, db_column="inv_id", related_name="+"
    )
    car_cant = models.DecimalField(
        "cantidad", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    car_fec_agregado = models.DateTimeField("fecha en que se agregó", auto_now_add=True)

    class Meta:
        db_table = "carrito"
        ordering = ["car_fec_agregado"]
        constraints = [models.UniqueConstraint(fields=["beneficiario", "inventario"], name="carrito_producto_unico")]

    def __str__(self):
        return f"{self.inventario.inv_nom}: {self.inventario.cantidad_texto(self.car_cant)}"


class Solicitud(models.Model):
    """Solicitud de productos (Actividad 7). Se crea desde el carrito."""

    PENDIENTE, APROBADA, RECHAZADA, CANCELADA = "pendiente", "aprobada", "rechazada", "cancelada"
    ESTADOS = [(PENDIENTE, "Pendiente"), (APROBADA, "Aprobada"), (RECHAZADA, "Rechazada"), (CANCELADA, "Cancelada")]

    sol_id = models.AutoField(primary_key=True)
    beneficiario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="usu_id",
        related_name="solicitudes",
    )
    revisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="usu_id_revisor",
        related_name="+",
    )
    sol_estado = models.CharField("estado", max_length=10, choices=ESTADOS, default=PENDIENTE, db_index=True)
    sol_obs_admin = models.TextField("observación del administrador", blank=True)
    sol_fec_envio = models.DateTimeField("fecha de envío", auto_now_add=True, db_index=True)
    sol_fec_resp = models.DateTimeField("fecha de respuesta", null=True, blank=True)

    class Meta:
        db_table = "solicitud"
        ordering = ["-sol_fec_envio"]

    def __str__(self):
        return f"Solicitud #{self.sol_id}"


class SolicitudDetalle(models.Model):
    """Productos solicitados."""

    sd_id = models.AutoField(primary_key=True)
    solicitud = models.ForeignKey(Solicitud, on_delete=models.PROTECT, db_column="sol_id", related_name="detalles")
    inventario = models.ForeignKey(
        "inventario.Inventario", on_delete=models.PROTECT, db_column="inv_id", related_name="+"
    )
    sd_cant = models.DecimalField("cantidad solicitada", max_digits=12, decimal_places=2)

    class Meta:
        db_table = "solicitud_detalle"
        constraints = [models.CheckConstraint(condition=models.Q(sd_cant__gt=0), name="sd_cant_positiva")]

    def __str__(self):
        return f"{self.inventario.inv_nom}: {self.inventario.cantidad_texto(self.sd_cant)}"
