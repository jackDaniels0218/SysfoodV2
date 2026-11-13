import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class UsuarioManager(BaseUserManager):
    def create_user(self, usu_correo, password=None, **extra):
        if not usu_correo:
            raise ValueError("El correo es obligatorio.")
        usuario = self.model(usu_correo=self.normalize_email(usu_correo).lower(), **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, usu_correo, password=None, **extra):
        extra.setdefault("usu_rol", Usuario.ADMIN)
        extra.setdefault("usu_acepta_datos", True)
        extra.setdefault("usu_fec_acepta", timezone.now())
        return self.create_user(usu_correo, password, **extra)

    def get_by_natural_key(self, correo):
        return self.get(usu_correo__iexact=correo)


class Usuario(AbstractBaseUser):
    """Cuenta del sistema (Actividad 1). Un único rol por usuario."""

    ADMIN, DONANTE, BENEFICIARIO = "administrador", "donante", "beneficiario"
    ROLES = [(ADMIN, "Administrador"), (DONANTE, "Donante"), (BENEFICIARIO, "Beneficiario")]
    ACTIVO, INACTIVO, BLOQUEADO = "activo", "inactivo", "bloqueado"
    ESTADOS = [(ACTIVO, "Activo"), (INACTIVO, "Inactivo"), (BLOQUEADO, "Bloqueado")]

    usu_id = models.AutoField(primary_key=True)
    usu_rol = models.CharField("rol", max_length=15, choices=ROLES, db_index=True)
    usu_correo = models.EmailField("correo electrónico", max_length=150, unique=True)
    password = models.CharField("contraseña", max_length=128, db_column="usu_pwd_hash")
    usu_nom = models.CharField("nombres", max_length=80)
    usu_ape = models.CharField("apellidos", max_length=80)
    usu_tel = models.CharField("teléfono", max_length=20)
    usu_estado = models.CharField("estado", max_length=10, choices=ESTADOS, default=ACTIVO, db_index=True)
    usu_acepta_datos = models.BooleanField("acepta la política de datos", default=False)
    usu_fec_acepta = models.DateTimeField("fecha de aceptación", null=True, blank=True)
    usu_intentos = models.PositiveSmallIntegerField("intentos fallidos", default=0)
    last_login = models.DateTimeField("último acceso", null=True, blank=True, db_column="usu_ult_acceso")
    usu_bloqueo_hasta = models.DateTimeField("bloqueado hasta", null=True, blank=True)
    usu_token_rec = models.CharField("token de recuperación", max_length=64, blank=True)
    usu_token_exp = models.DateTimeField("vencimiento del token", null=True, blank=True)
    usu_fec_reg = models.DateTimeField("fecha de registro", auto_now_add=True)

    objects = UsuarioManager()

    USERNAME_FIELD = "usu_correo"
    EMAIL_FIELD = "usu_correo"
    REQUIRED_FIELDS = ["usu_nom", "usu_ape", "usu_tel"]

    class Meta:
        db_table = "usuario"
        ordering = ["usu_nom", "usu_ape"]

    def __str__(self):
        return self.nombre_completo

    @property
    def nombre_completo(self):
        return f"{self.usu_nom} {self.usu_ape}".strip()

    @property
    def is_active(self):
        return self.usu_estado != self.INACTIVO

    @property
    def es_admin(self):
        return self.usu_rol == self.ADMIN

    @property
    def es_donante(self):
        return self.usu_rol == self.DONANTE

    @property
    def es_beneficiario(self):
        return self.usu_rol == self.BENEFICIARIO

    # --- Recuperación de contraseña: se guarda solo la huella del token.
    @staticmethod
    def _huella(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def generar_token_recuperacion(self, minutos):
        token = secrets.token_urlsafe(32)
        self.usu_token_rec = self._huella(token)
        self.usu_token_exp = timezone.now() + timedelta(minutes=minutos)
        self.save(update_fields=["usu_token_rec", "usu_token_exp"])
        return token

    def token_valido(self, token):
        return bool(
            self.usu_token_rec
            and self.usu_token_exp
            and self.usu_token_exp > timezone.now()
            and secrets.compare_digest(self.usu_token_rec, self._huella(token))
        )

    def invalidar_token(self):
        self.usu_token_rec = ""
        self.usu_token_exp = None

    @classmethod
    def buscar_por_token(cls, token):
        return cls.objects.filter(usu_token_rec=cls._huella(token)).first()


class PerfilDonante(models.Model):
    """Datos adicionales del rol Donante."""

    NATURAL, JURIDICA = "natural", "juridica"
    TIPOS_PERSONA = [(NATURAL, "Persona natural"), (JURIDICA, "Persona jurídica")]
    TIPOS_DOC = [
        ("CC", "Cédula de ciudadanía"),
        ("CE", "Cédula de extranjería"),
        ("NIT", "NIT"),
        ("Pasaporte", "Pasaporte"),
    ]
    FRECUENCIAS = [("", "Sin definir"), ("mensual", "Mensual"), ("trimestral", "Trimestral"), ("anual", "Anual")]

    usuario = models.OneToOneField(
        Usuario,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column="usu_id",
        related_name="perfil_donante",
    )
    don_tipo_persona = models.CharField("tipo de persona", max_length=10, choices=TIPOS_PERSONA)
    don_tipo_doc = models.CharField("tipo de documento", max_length=10, choices=TIPOS_DOC)
    don_doc_nit = models.CharField(
        "número de documento o NIT",
        max_length=20,
        unique=True,
        error_messages={"unique": "Ya existe un donante registrado con este documento o NIT."},
    )
    don_raz_soc = models.CharField("razón social", max_length=150, blank=True)
    don_contacto = models.CharField("nombre de contacto", max_length=150, blank=True)
    don_dir = models.CharField("dirección", max_length=200)
    don_frecuencia = models.CharField("frecuencia de donación", max_length=12, choices=FRECUENCIAS, blank=True)
    don_anonimo_def = models.BooleanField("donar de forma anónima por defecto", default=False)

    class Meta:
        db_table = "donante"
        verbose_name = "donante"

    def __str__(self):
        return f"Donante: {self.nombre_publico}"

    def clean(self):
        if self.don_tipo_persona == self.JURIDICA and not self.don_raz_soc:
            raise ValidationError({"don_raz_soc": "La razón social es obligatoria para personas jurídicas."})
        if self.don_tipo_persona == self.JURIDICA and self.don_tipo_doc != "NIT":
            raise ValidationError({"don_tipo_doc": "Las personas jurídicas se identifican con NIT."})

    @property
    def nombre_publico(self):
        if self.don_tipo_persona == self.JURIDICA and self.don_raz_soc:
            return self.don_raz_soc
        return self.usuario.nombre_completo


class PerfilBeneficiario(models.Model):
    """Datos adicionales del rol Beneficiario."""

    TIPOS_DOC = [
        ("CC", "Cédula de ciudadanía"),
        ("TI", "Tarjeta de identidad"),
        ("CE", "Cédula de extranjería"),
        ("Pasaporte", "Pasaporte"),
    ]
    SISBEN = [("A", "A"), ("B", "B"), ("C", "C"), ("D", "D"), ("NR", "No registrado")]
    # Sisbén IV: cada grupo se divide en subgrupos numerados (A1-A5, B1-B7, C1-C18, D1-D21).
    SISBEN_SUBGRUPOS = {"A": 5, "B": 7, "C": 18, "D": 21}
    SISBEN_CATEGORIAS = {
        "A": "Pobreza extrema",
        "B": "Pobreza moderada",
        "C": "Vulnerable",
        "D": "No pobre, no vulnerable",
    }
    ESTRATOS = [(i, str(i)) for i in range(1, 7)]
    PENDIENTE, EN_REVISION, VERIFICADO, RECHAZADO = "pendiente", "en_revision", "verificado", "rechazado"
    ESTADOS_VERIF = [
        (PENDIENTE, "Pendiente"),
        (EN_REVISION, "En revisión"),
        (VERIFICADO, "Verificado"),
        (RECHAZADO, "Rechazado"),
    ]

    usuario = models.OneToOneField(
        Usuario,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column="usu_id",
        related_name="perfil_beneficiario",
    )
    ben_tipo_doc = models.CharField("tipo de documento", max_length=10, choices=TIPOS_DOC)
    ben_num_doc = models.CharField("número de documento", max_length=20)
    ben_fec_exp_doc = models.DateField("fecha de expedición del documento")
    ben_dir = models.CharField("dirección de residencia", max_length=200)
    ben_num_personas = models.PositiveSmallIntegerField("personas en el hogar")
    ben_sisben = models.CharField("nivel de Sisbén", max_length=2, choices=SISBEN)
    ben_sisben_subgrupo = models.PositiveSmallIntegerField("subgrupo de Sisbén", null=True, blank=True)
    ben_estrato = models.PositiveSmallIntegerField("estrato social", choices=ESTRATOS)
    ben_discapacidad = models.BooleanField("tiene discapacidad", default=False)
    ben_estado_verif = models.CharField(
        "estado de verificación",
        max_length=12,
        choices=ESTADOS_VERIF,
        default=PENDIENTE,
        db_index=True,
    )
    ben_fec_verif = models.DateTimeField("fecha de verificación", null=True, blank=True)
    # Puntaje automático de necesidad (usuarios/puntaje.py). Lo calcula el sistema, nunca el usuario.
    ben_puntaje = models.DecimalField(
        "puntaje de necesidad", max_digits=5, decimal_places=2, null=True, blank=True, db_index=True
    )
    ben_grupo = models.CharField("grupo de necesidad", max_length=30, blank=True, db_index=True)
    ben_puntaje_detalle = models.JSONField("desglose del puntaje", default=list, blank=True)
    ben_fec_puntaje = models.DateTimeField("fecha del cálculo", null=True, blank=True)
    # Ubicación automática (usuarios/ubicacion.py). Solo la ve el administrador.
    GEO_PENDIENTE, GEO_OK, GEO_REINTENTAR, GEO_REVISION, GEO_MANUAL = (
        "pendiente",
        "ubicado",
        "reintentar",
        "revision",
        "manual",
    )
    ESTADOS_GEO = [
        (GEO_PENDIENTE, "Pendiente"),
        (GEO_OK, "Ubicado automáticamente"),
        (GEO_REINTENTAR, "Falló, se reintentará"),
        (GEO_REVISION, "Requiere revisión"),
        (GEO_MANUAL, "Ubicado por el administrador"),
    ]
    ben_lat = models.DecimalField("latitud", max_digits=9, decimal_places=6, null=True, blank=True)
    ben_lng = models.DecimalField("longitud", max_digits=9, decimal_places=6, null=True, blank=True)
    ben_zona = models.CharField("zona o barrio", max_length=80, blank=True, db_index=True)
    ben_geo_estado = models.CharField(
        "estado de la ubicación", max_length=12, choices=ESTADOS_GEO, default=GEO_PENDIENTE, db_index=True
    )
    ben_geo_intentos = models.PositiveSmallIntegerField("intentos de geocodificación", default=0)
    ben_geo_fecha = models.DateTimeField("último intento de geocodificación", null=True, blank=True)
    ben_geo_detalle = models.CharField("resultado de la geocodificación", max_length=255, blank=True)

    CAMPOS_AUTOMATICOS = {
        "ben_estado_verif",
        "ben_fec_verif",
        "ben_puntaje",
        "ben_grupo",
        "ben_puntaje_detalle",
        "ben_fec_puntaje",
        "ben_lat",
        "ben_lng",
        "ben_zona",
        "ben_geo_estado",
        "ben_geo_intentos",
        "ben_geo_fecha",
        "ben_geo_detalle",
    }

    class Meta:
        db_table = "beneficiario"
        verbose_name = "beneficiario"
        constraints = [
            models.UniqueConstraint(
                fields=["ben_tipo_doc", "ben_num_doc"],
                name="ben_documento_unico",
                violation_error_message="Ya existe un beneficiario registrado con este documento.",
            ),
            models.CheckConstraint(
                condition=models.Q(ben_estrato__gte=1, ben_estrato__lte=6), name="ben_estrato_rango"
            ),
            models.CheckConstraint(condition=models.Q(ben_num_personas__gte=1), name="ben_personas_minimo"),
            models.CheckConstraint(
                condition=models.Q(ben_puntaje__isnull=True) | models.Q(ben_puntaje__gte=0, ben_puntaje__lte=100),
                name="ben_puntaje_rango",
            ),
            models.CheckConstraint(
                condition=models.Q(ben_lat__isnull=True)
                | models.Q(ben_lat__gte=-90, ben_lat__lte=90, ben_lng__gte=-180, ben_lng__lte=180),
                name="ben_coordenadas_rango",
            ),
        ]

    def __str__(self):
        return f"Beneficiario: {self.ben_tipo_doc} {self.ben_num_doc}"

    def clean(self):
        if self.ben_fec_exp_doc and self.ben_fec_exp_doc > timezone.localdate():
            raise ValidationError({"ben_fec_exp_doc": "La fecha de expedición no puede ser futura."})

    @property
    def sisben_codigo(self):
        """Grupo y subgrupo como aparecen en el certificado (C8), o la letra si no se registró el subgrupo."""
        if self.ben_sisben == "NR":
            return "No registrado"
        return f"{self.ben_sisben}{self.ben_sisben_subgrupo or ''}"

    @property
    def sisben_texto(self):
        if self.ben_sisben == "NR":
            return "No registrado"
        return f"{self.sisben_codigo} · {self.SISBEN_CATEGORIAS.get(self.ben_sisben, '')}"

    @property
    def verificado(self):
        return self.ben_estado_verif == self.VERIFICADO

    @property
    def ubicado(self):
        return self.ben_lat is not None and self.ben_lng is not None

    @property
    def grupo(self):
        """Grupo de necesidad vigente {clave, nombre, minimo, color} según los parámetros."""
        from . import puntaje

        return puntaje.grupo_por_clave(self.ben_grupo)


def ruta_documento(instancia, nombre):
    return f"documentos/{instancia.usuario_id}/{nombre}"


class DocumentoValidacion(models.Model):
    """Documentos de soporte (Actividad 2)."""

    IDENTIDAD, SISBEN, RESIDENCIA, DISCAPACIDAD = "identidad", "sisben", "residencia", "discapacidad"
    CAMARA_COMERCIO, RUT = "camara_comercio", "rut"
    TIPOS = [
        (IDENTIDAD, "Documento de identidad"),
        (SISBEN, "Certificado de Sisbén"),
        (RESIDENCIA, "Soporte de residencia o estrato"),
        (DISCAPACIDAD, "Certificado de discapacidad"),
        (CAMARA_COMERCIO, "Cámara de Comercio"),
        (RUT, "RUT"),
    ]
    TIPOS_BENEFICIARIO = (IDENTIDAD, SISBEN, RESIDENCIA, DISCAPACIDAD)
    TIPOS_DONANTE_JURIDICO = (CAMARA_COMERCIO, RUT)

    CARGADO, APROBADO, RECHAZADO, VENCIDO = "cargado", "aprobado", "rechazado", "vencido"
    ESTADOS = [(CARGADO, "Cargado"), (APROBADO, "Aprobado"), (RECHAZADO, "Rechazado"), (VENCIDO, "Vencido")]

    docv_id = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, db_column="usu_id", related_name="documentos")
    revisor = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="usu_id_revisor",
        related_name="+",
    )
    docv_tipo = models.CharField("tipo de documento", max_length=20, choices=TIPOS)
    docv_nom_archivo = models.CharField("nombre del archivo", max_length=255)
    docv_ruta = models.CharField("ruta protegida", max_length=255)
    docv_mime = models.CharField("tipo MIME", max_length=50)
    docv_tam_bytes = models.PositiveIntegerField("tamaño (bytes)")
    docv_hash = models.CharField("huella SHA-256", max_length=64, db_index=True)
    docv_estado = models.CharField("estado", max_length=10, choices=ESTADOS, default=CARGADO, db_index=True)
    docv_obs = models.TextField("observación", blank=True)
    docv_fec_carga = models.DateTimeField("fecha de carga", auto_now_add=True)
    docv_fec_revision = models.DateTimeField("fecha de revisión", null=True, blank=True)
    docv_fec_venc = models.DateField("fecha de vencimiento", null=True, blank=True)
    # Verificación automática (usuarios/verificacion.py)
    OCR_PENDIENTE, OCR_PROCESADO, OCR_NO_DISPONIBLE, OCR_ERROR, OCR_NO_APLICA = (
        "pendiente",
        "procesado",
        "no_disponible",
        "error",
        "no_aplica",
    )
    ESTADOS_OCR = [
        (OCR_PENDIENTE, "Pendiente de lectura"),
        (OCR_PROCESADO, "Leído automáticamente"),
        (OCR_NO_DISPONIBLE, "Lectura automática no disponible"),
        (OCR_ERROR, "Error de lectura (se reintentará)"),
        (OCR_NO_APLICA, "Revisión manual"),
    ]
    ALTA, MEDIA, BAJA, ILEGIBLE = "alta", "media", "baja", "ilegible"
    DECISIONES = [
        (ALTA, "Confianza alta"),
        (MEDIA, "Confianza media"),
        (BAJA, "Confianza baja"),
        (ILEGIBLE, "Ilegible"),
    ]
    docv_ocr_estado = models.CharField(
        "lectura automática", max_length=14, choices=ESTADOS_OCR, default=OCR_NO_APLICA, db_index=True
    )
    docv_ocr_texto = models.TextField("texto leído", blank=True)
    docv_ocr_confianza = models.DecimalField(
        "confianza de la verificación", max_digits=5, decimal_places=1, null=True, blank=True
    )
    docv_ocr_resultado = models.JSONField("resultado de la comparación", default=dict, blank=True)
    docv_decision_auto = models.CharField(
        "decisión automática", max_length=10, choices=DECISIONES, blank=True, db_index=True
    )
    docv_verif_auto = models.BooleanField("resuelto automáticamente", default=False, db_index=True)
    docv_ocr_intentos = models.PositiveSmallIntegerField("intentos de lectura", default=0)
    docv_fec_ocr = models.DateTimeField("fecha de lectura", null=True, blank=True)

    class Meta:
        db_table = "documento_validacion"
        ordering = ["usuario", "docv_tipo"]

    def __str__(self):
        return f"{self.get_docv_tipo_display()} de {self.usuario}"

    @property
    def ruta_absoluta(self):
        return settings.PROTECTED_MEDIA_ROOT / self.docv_ruta

    def leer_contenido(self):
        """Bytes del archivo. Usa la copia del disco y, si no está (el disco de Render se borra al
        reiniciar), la recupera de la base de datos y la vuelve a escribir. FileNotFoundError si no hay."""
        ruta = self.ruta_absoluta
        if self.docv_ruta and ruta.is_file():
            return ruta.read_bytes()
        guardado = ArchivoDocumento.objects.filter(documento_id=self.pk).values_list("arc_contenido", flat=True).first()
        if guardado is None:
            raise FileNotFoundError(f"El archivo del documento {self.pk} no está guardado.")
        contenido = bytes(guardado)
        try:  # Copia en disco para las siguientes lecturas; si falla, se sigue leyendo de la base.
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_bytes(contenido)
        except OSError:
            pass
        return contenido

    @property
    def es_imagen(self):
        return self.docv_mime.startswith("image/")

    @property
    def semaforo(self):
        """verde, amarillo o rojo según la decisión automática (vacío si no hubo)."""
        return {self.ALTA: "verde", self.MEDIA: "amarillo", self.BAJA: "rojo", self.ILEGIBLE: "rojo"}.get(
            self.docv_decision_auto, ""
        )

    @property
    def discrepancias(self):
        return [c for c in (self.docv_ocr_resultado or {}).get("campos", []) if c.get("coincide", 0) < 1]


class ArchivoDocumento(models.Model):
    """Contenido de un documento de validación guardado en la base de datos.

    Es la copia permanente: el disco del servidor puede borrarse (en Render, en cada despliegue o
    reinicio). Va en una tabla aparte para no traer los bytes en cada consulta de documentos.
    """

    documento = models.OneToOneField(
        DocumentoValidacion,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column="docv_id",
        related_name="archivo",
    )
    arc_contenido = models.BinaryField("contenido")

    class Meta:
        db_table = "archivo_documento"
        verbose_name = "archivo de documento"

    def __str__(self):
        return f"Archivo del documento {self.documento_id}"
