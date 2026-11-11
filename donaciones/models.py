from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Floor

ANONIMO = "Donante anónimo"


class Donacion(models.Model):
    """Encabezado de la donación (Actividad 5)."""

    DISPONIBLE, RESERVADA, ENTREGADA, VENCIDA, CANCELADA = "disponible", "reservada", "entregada", "vencida", "cancelada"
    ESTADOS = [
        (DISPONIBLE, "Disponible"), (RESERVADA, "Reservada"), (ENTREGADA, "Entregada"),
        (VENCIDA, "Vencida"), (CANCELADA, "Cancelada"),
    ]

    dona_id = models.AutoField(primary_key=True)
    donante = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column="usu_id", related_name="donaciones",
    )
    dona_anonima = models.BooleanField("donación anónima", default=False)
    dona_estado = models.CharField("estado", max_length=10, choices=ESTADOS, default=DISPONIBLE, db_index=True)
    dona_obs = models.TextField("observaciones", blank=True)
    dona_fec_reg = models.DateTimeField("fecha de registro", auto_now_add=True, db_index=True)
    dona_fec_mod = models.DateTimeField("última modificación", auto_now=True)

    class Meta:
        db_table = "donacion"
        ordering = ["-dona_fec_reg"]
        verbose_name = "donación"

    def __str__(self):
        return f"Donación #{self.dona_id}"

    def nombre_donante(self, usuario=None):
        """Nombre visible del donante. Solo el administrador (o el propio donante) ve la identidad."""
        if self.dona_anonima and not (usuario and (usuario.es_admin or usuario.pk == self.donante_id)):
            return ANONIMO
        perfil = getattr(self.donante, "perfil_donante", None)
        return perfil.nombre_publico if perfil else self.donante.nombre_completo

    @property
    def nombre_publico(self):
        return ANONIMO if self.dona_anonima else self.nombre_donante(self.donante)

    @property
    def editable(self):
        return self.dona_estado == self.DISPONIBLE and not self.tiene_movimientos_de_salida()

    def tiene_movimientos_de_salida(self):
        from inventario.models import Kardex

        return Kardex.objects.filter(
            inventario__detalle__donacion=self, kar_tipo__in=[Kardex.RESERVA, Kardex.ENTREGA]
        ).exists()

    def recalcular_estado(self):
        """Deriva el estado de la donación a partir de su inventario."""
        if self.dona_estado == self.CANCELADA:
            return self.dona_estado
        from inventario.models import Inventario, Kardex

        items = list(Inventario.objects.filter(detalle__donacion=self))
        if not items:
            return self.dona_estado
        pendientes = [i for i in items if i.inv_estado != Inventario.RETIRADO and i.inv_cant_disp > 0]
        entregada = Kardex.objects.filter(inventario__in=items, kar_tipo=Kardex.ENTREGA).exists()
        if any(i.inv_cant_reserv > 0 for i in items):
            nuevo = self.RESERVADA
        elif not pendientes and entregada:
            nuevo = self.ENTREGADA
        elif all(i.inv_est_venc == Inventario.VENCIDO for i in items):
            nuevo = self.VENCIDA
        else:
            nuevo = self.DISPONIBLE
        if nuevo != self.dona_estado:
            self.dona_estado = nuevo
            self.save(update_fields=["dona_estado", "dona_fec_mod"])
        return nuevo


class DetalleDonacion(models.Model):
    """Productos que componen la donación."""

    REGISTRADO, EN_INVENTARIO, RETIRADO = "registrado", "en_inventario", "retirado"
    ESTADOS = [(REGISTRADO, "Registrado"), (EN_INVENTARIO, "En inventario"), (RETIRADO, "Retirado")]

    dd_id = models.AutoField(primary_key=True)
    donacion = models.ForeignKey(Donacion, on_delete=models.PROTECT, db_column="dona_id", related_name="detalles")
    categoria = models.ForeignKey(
        "catalogo.Categoria", on_delete=models.PROTECT, db_column="cat_id", related_name="detalles_donacion",
        verbose_name="categoría",
    )
    dd_nom = models.CharField("producto", max_length=120)
    dd_desc = models.CharField("descripción", max_length=255, blank=True)
    dd_cantidad = models.DecimalField(
        "cantidad", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))],
    )
    dd_unidad = models.CharField("unidad de medida", max_length=30)
    dd_divisible = models.BooleanField("admite decimales", default=True)
    dd_fec_venc = models.DateField("fecha de vencimiento")
    dd_lote = models.CharField("lote", max_length=50, blank=True)
    dd_estado = models.CharField("estado", max_length=15, choices=ESTADOS, default=REGISTRADO)

    class Meta:
        db_table = "detalle_donacion"
        ordering = ["dd_id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(dd_cantidad__gt=0), name="dd_cantidad_positiva"),
            models.CheckConstraint(
                condition=models.Q(dd_divisible=True) | models.Q(dd_cantidad=Floor("dd_cantidad")),
                name="dd_contable_entero",
                violation_error_message="Las unidades contables solo admiten cantidades enteras.",
            ),
        ]

    def __str__(self):
        from inventario.unidades import formatear

        return f"{self.dd_nom} ({formatear(self.dd_cantidad, self.dd_unidad)})"

    def clean(self):
        super().clean()
        from inventario import unidades

        if self.dd_cantidad is not None and self.dd_unidad:
            try:
                unidades.validar(self.dd_cantidad, self.dd_unidad)
            except ValidationError as error:
                raise ValidationError({"dd_cantidad": error.messages})

    def save(self, *args, **kwargs):
        from inventario import unidades

        self.dd_divisible = unidades.es_divisible(self.dd_unidad)
        if kwargs.get("update_fields") is not None and "dd_unidad" in kwargs["update_fields"]:
            kwargs["update_fields"] = {*kwargs["update_fields"], "dd_divisible"}
        super().save(*args, **kwargs)
