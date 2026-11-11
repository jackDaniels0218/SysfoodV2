from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models


class Parametro(models.Model):
    """Valores de configuración del sistema (Actividad 9).

    Los parámetros se crean en la migración inicial: no se crean ni se
    eliminan desde la aplicación, solo se modifican.
    """

    par_id = models.AutoField(primary_key=True)
    par_clave = models.CharField("clave", max_length=60, unique=True)
    par_valor = models.CharField("valor", max_length=500)
    par_desc = models.CharField("descripción", max_length=255)
    usuario_mod = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="usu_id_mod",
        related_name="+",
        verbose_name="modificado por",
    )
    par_fec_mod = models.DateTimeField("última modificación", auto_now=True)

    class Meta:
        db_table = "parametro"
        ordering = ["par_clave"]
        verbose_name = "parámetro"

    def __str__(self):
        return f"{self.par_clave} = {self.par_valor}"

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Los parámetros no se eliminan.")


class _SoloInsercion(models.Model):
    """Registro inmutable: se puede crear, pero nunca editar ni borrar."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionDenied("Este registro es de solo consulta y no puede modificarse.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Este registro es de solo consulta y no puede eliminarse.")


class Bitacora(_SoloInsercion):
    """Bitácora de auditoría (Actividad 14)."""

    ACCIONES = [
        ("crear", "Crear"),
        ("editar", "Editar"),
        ("eliminar", "Eliminar"),
        ("ingreso", "Ingreso al sistema"),
        ("ingreso_fallido", "Ingreso fallido"),
        ("salida", "Cierre de sesión"),
        ("cambio_estado", "Cambio de estado"),
        ("cambio_parametro", "Cambio de parámetro"),
        ("consulta_anonimo", "Consulta de identidad de donante anónimo"),
        ("recuperacion", "Recuperación de contraseña"),
        ("respaldo", "Respaldo"),
        ("calculo_puntaje", "Cálculo automático de puntaje"),
        ("clasificacion", "Clasificación automática por grupo"),
        ("tarea_programada", "Tarea programada"),
        ("geocodificacion", "Geocodificación automática"),
        ("consulta_mapa", "Consulta del mapa de beneficiarios"),
        ("exportacion_mapa", "Exportación del mapa de beneficiarios"),
        ("verificacion_auto", "Verificación automática de documento"),
        ("escalamiento_chat", "Consulta del asistente enviada al administrador"),
        ("envio_reporte", "Envío programado de reporte"),
    ]

    bit_id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_column="usu_id",
        related_name="+",
    )
    bit_accion = models.CharField("acción", max_length=30, choices=ACCIONES)
    bit_entidad = models.CharField("entidad", max_length=60)
    bit_registro = models.CharField("registro afectado", max_length=60, blank=True)
    bit_detalle = models.TextField("detalle", blank=True)
    bit_ip = models.GenericIPAddressField("dirección IP", null=True, blank=True)
    bit_fecha = models.DateTimeField("fecha", auto_now_add=True, db_index=True)

    class Meta:
        db_table = "bitacora"
        ordering = ["-bit_fecha", "-bit_id"]


class Notificacion(models.Model):
    """Notificaciones internas (Actividad 13). Las crea el sistema."""

    TIPOS = [
        ("documento", "Documentos"),
        ("solicitud", "Solicitudes"),
        ("entrega", "Entregas"),
        ("reserva", "Reservas"),
        ("vencimiento", "Vencimientos"),
        ("cuenta", "Cuenta"),
        ("donacion", "Donaciones"),
        ("ayuda", "Consultas de ayuda"),
    ]

    not_id = models.BigAutoField(primary_key=True)
    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="usu_id",
        related_name="notificaciones",
    )
    not_tipo = models.CharField("tipo", max_length=20, choices=TIPOS)
    not_titulo = models.CharField("título", max_length=150)
    not_mensaje = models.TextField("mensaje")
    not_url = models.CharField("registro relacionado", max_length=255, blank=True)
    not_leida = models.BooleanField("leída", default=False)
    not_fecha = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        db_table = "notificacion"
        ordering = ["-not_fecha", "-not_id"]
        indexes = [models.Index(fields=["destinatario", "not_leida"])]


class TareaProgramada(models.Model):
    """Control interno de los procesos automáticos (fecha de última ejecución)."""

    tar_nombre = models.CharField(max_length=60, primary_key=True)
    tar_ult_ejecucion = models.DateTimeField(null=True, blank=True)
    tar_resultado = models.CharField("resultado", max_length=255, blank=True)
    tar_duracion_ms = models.PositiveIntegerField("duración (ms)", null=True, blank=True)

    class Meta:
        db_table = "tarea_programada"


class GeoCache(models.Model):
    """Caché de geocodificación: una dirección normalizada se consulta al proveedor una sola vez."""

    geo_id = models.BigAutoField(primary_key=True)
    geo_direccion = models.CharField("dirección normalizada", max_length=255, unique=True)
    geo_encontrada = models.BooleanField("encontrada", default=True)
    geo_lat = models.DecimalField("latitud", max_digits=9, decimal_places=6, null=True, blank=True)
    geo_lng = models.DecimalField("longitud", max_digits=9, decimal_places=6, null=True, blank=True)
    geo_zona = models.CharField("zona o barrio", max_length=80, blank=True)
    geo_proveedor = models.CharField("proveedor", max_length=30)
    geo_fecha = models.DateTimeField("fecha", auto_now=True)

    class Meta:
        db_table = "geo_cache"
        verbose_name = "dirección geocodificada"


class FiltroGuardado(models.Model):
    """Combinación de filtros de una lista que el usuario guarda con un nombre para reutilizarla."""

    VISTAS = {
        "inventario": "inventario:lista",
        "solicitudes": "solicitudes:lista_admin",
        "usuarios": "usuarios:lista",
        "donaciones": "donaciones:lista_admin",
        "entregas": "entregas:lista",
    }

    fil_id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_column="usu_id", related_name="filtros"
    )
    fil_vista = models.CharField("lista", max_length=30)
    fil_nombre = models.CharField("nombre", max_length=60)
    fil_consulta = models.CharField("filtros", max_length=500)
    fil_fecha = models.DateTimeField("fecha", auto_now=True)

    class Meta:
        db_table = "filtro_guardado"
        ordering = ["fil_nombre"]
        constraints = [
            models.UniqueConstraint(fields=["usuario", "fil_vista", "fil_nombre"], name="filtro_unico_por_usuario")
        ]

    def __str__(self):
        return self.fil_nombre
