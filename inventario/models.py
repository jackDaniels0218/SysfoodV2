from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models.functions import Floor
from django.utils import timezone

from core.models import _SoloInsercion


class Inventario(models.Model):
    """Producto en inventario (Actividad 6). Se crea al registrar una donación."""

    DISPONIBLE, RESERVADO, AGOTADO, RETIRADO = "disponible", "reservado", "agotado", "retirado"
    ESTADOS = [(DISPONIBLE, "Disponible"), (RESERVADO, "Reservado"), (AGOTADO, "Agotado"), (RETIRADO, "Retirado")]
    VIGENTE, PROXIMO, VENCIDO = "vigente", "proximo", "vencido"
    VIGENCIAS = [(VIGENTE, "Vigente"), (PROXIMO, "Próximo a vencer"), (VENCIDO, "Vencido")]
    MOTIVOS_BAJA = [
        ("vencido", "Vencido"),
        ("danado", "Dañado"),
        ("retiro_donante", "Retiro del donante"),
        ("otro", "Otro"),
    ]

    inv_id = models.AutoField(primary_key=True)
    detalle = models.OneToOneField(
        "donaciones.DetalleDonacion",
        on_delete=models.PROTECT,
        db_column="dd_id",
        related_name="inventario",
    )
    bodega = models.ForeignKey(
        "catalogo.Bodega", on_delete=models.PROTECT, db_column="bod_id", related_name="inventario"
    )
    categoria = models.ForeignKey(
        "catalogo.Categoria",
        on_delete=models.PROTECT,
        db_column="cat_id",
        related_name="inventario",
    )
    inv_nom = models.CharField("producto", max_length=120, db_index=True)
    inv_unidad = models.CharField("unidad", max_length=30)
    inv_divisible = models.BooleanField(
        "admite decimales",
        default=True,
        help_text="Copia de la unidad al ingresar: si es falso, todas las cantidades deben ser enteras.",
    )
    inv_cant_inicial = models.DecimalField("cantidad inicial", max_digits=12, decimal_places=2)
    inv_cant_disp = models.DecimalField("cantidad disponible", max_digits=12, decimal_places=2)
    inv_cant_reserv = models.DecimalField("cantidad reservada", max_digits=12, decimal_places=2, default=Decimal("0"))
    inv_fec_venc = models.DateField("fecha de vencimiento", db_index=True)
    inv_estado = models.CharField("estado", max_length=10, choices=ESTADOS, default=DISPONIBLE, db_index=True)
    inv_est_venc = models.CharField("vigencia", max_length=10, choices=VIGENCIAS, default=VIGENTE, db_index=True)
    inv_fec_ingreso = models.DateTimeField("fecha de ingreso", auto_now_add=True)
    inv_mot_baja = models.CharField("motivo de baja", max_length=20, choices=MOTIVOS_BAJA, blank=True)
    inv_det_baja = models.CharField("detalle de la baja", max_length=255, blank=True)
    inv_fec_baja = models.DateTimeField("fecha de baja", null=True, blank=True)
    usuario_baja = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="usu_id_baja",
        related_name="+",
    )

    class Meta:
        db_table = "inventario"
        ordering = ["inv_fec_venc", "inv_nom"]
        constraints = [
            models.CheckConstraint(condition=models.Q(inv_cant_disp__gte=0), name="inv_disp_no_negativa"),
            models.CheckConstraint(condition=models.Q(inv_cant_reserv__gte=0), name="inv_reserv_no_negativa"),
            models.CheckConstraint(
                condition=models.Q(inv_divisible=True)
                | models.Q(
                    inv_cant_inicial=Floor("inv_cant_inicial"),
                    inv_cant_disp=Floor("inv_cant_disp"),
                    inv_cant_reserv=Floor("inv_cant_reserv"),
                ),
                name="inv_contable_entero",
                violation_error_message="Las unidades contables solo admiten cantidades enteras.",
            ),
        ]

    def __str__(self):
        return f"{self.inv_nom} ({self.cantidad_texto(self.inv_cant_disp)})"

    def cantidad_texto(self, cantidad):
        from .unidades import formatear

        return formatear(cantidad, self.inv_unidad)

    def validar_cantidad(self, cantidad):
        """Valida contra la unidad con que se registró el producto (la misma regla que la base de datos)."""
        from .unidades import validar

        return validar(cantidad, self.inv_unidad, self.inv_divisible)

    @property
    def paso(self):
        return "0.01" if self.inv_divisible else "1"

    @property
    def cantidad_existente(self):
        return self.inv_cant_disp + self.inv_cant_reserv

    @property
    def dias_para_vencer(self):
        return (self.inv_fec_venc - timezone.localdate()).days

    @property
    def disponible_para_catalogo(self):
        return (
            self.inv_estado in (self.DISPONIBLE,)
            and self.inv_est_venc != self.VENCIDO
            and self.inv_cant_disp > 0
            and self.inv_fec_venc >= timezone.localdate()
        )

    def calcular_vigencia(self, hoy=None):
        hoy = hoy or timezone.localdate()
        if self.inv_fec_venc < hoy:
            return self.VENCIDO
        if self.inv_fec_venc - hoy < timedelta(days=self.categoria.dias_alerta()):
            return self.PROXIMO
        return self.VIGENTE

    def calcular_estado(self):
        if self.inv_estado == self.RETIRADO:
            return self.RETIRADO
        if self.inv_cant_disp > 0:
            return self.DISPONIBLE
        if self.inv_cant_reserv > 0:
            return self.RESERVADO
        return self.AGOTADO

    @classmethod
    def catalogo(cls):
        """Productos visibles para los beneficiarios: vigentes y con existencia."""
        return cls.objects.filter(
            inv_estado=cls.DISPONIBLE,
            inv_cant_disp__gt=0,
            inv_fec_venc__gte=timezone.localdate(),
        ).exclude(inv_est_venc=cls.VENCIDO)


class Kardex(_SoloInsercion):
    """Movimientos de inventario. Solo inserción (Actividad 14 y 19)."""

    INGRESO, RESERVA, LIBERACION, ENTREGA, AJUSTE, BAJA = (
        "ingreso",
        "reserva",
        "liberacion",
        "entrega",
        "ajuste",
        "baja",
    )
    TIPOS = [
        (INGRESO, "Ingreso"),
        (RESERVA, "Reserva"),
        (LIBERACION, "Liberación"),
        (ENTREGA, "Entrega"),
        (AJUSTE, "Ajuste"),
        (BAJA, "Baja"),
    ]

    kar_id = models.BigAutoField(primary_key=True)
    inventario = models.ForeignKey(Inventario, on_delete=models.PROTECT, db_column="inv_id", related_name="kardex")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="usu_id",
        related_name="+",
    )
    entrega = models.ForeignKey(
        "entregas.Entrega",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="ent_id",
        related_name="kardex",
    )
    kar_tipo = models.CharField("tipo de movimiento", max_length=12, choices=TIPOS, db_index=True)
    kar_cantidad = models.DecimalField("cantidad", max_digits=12, decimal_places=2)
    kar_cant_anterior = models.DecimalField("disponible anterior", max_digits=12, decimal_places=2)
    kar_cant_resultante = models.DecimalField("disponible resultante", max_digits=12, decimal_places=2)
    kar_reserv_anterior = models.DecimalField("reservado anterior", max_digits=12, decimal_places=2, default=0)
    kar_reserv_resultante = models.DecimalField("reservado resultante", max_digits=12, decimal_places=2, default=0)
    kar_motivo = models.CharField("motivo", max_length=255, blank=True)
    kar_fecha = models.DateTimeField("fecha", auto_now_add=True, db_index=True)

    class Meta:
        db_table = "kardex"
        ordering = ["-kar_fecha", "-kar_id"]
