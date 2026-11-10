"""Fábricas de datos para las pruebas."""
import hashlib
import shutil
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from catalogo.models import Bodega, Categoria
from donaciones import servicios as don_srv
from donaciones.models import DetalleDonacion, Donacion
from usuarios import servicios as usu_srv
from usuarios.models import DocumentoValidacion, PerfilBeneficiario, PerfilDonante, Usuario

CLAVE = "Clave$egura123"
_contador = [0]


def siguiente():
    _contador[0] += 1
    return _contador[0]


def pdf(marca=None, nombre="doc.pdf", relleno=0):
    marca = marca or f"pdf-{siguiente()}"
    contenido = b"%PDF-1.4\n%" + marca.encode() + b"\n" + b"0" * relleno + b"%%EOF\n"
    return SimpleUploadedFile(nombre, contenido, content_type="application/pdf")


def png(marca=None, nombre="foto.png"):
    marca = marca or f"png-{siguiente()}"
    return SimpleUploadedFile(nombre, b"\x89PNG\r\n\x1a\n" + marca.encode(), content_type="image/png")


def crear_usuario(rol, correo=None, **extra):
    n = siguiente()
    datos = dict(usu_nom=f"Nombre{n}", usu_ape=f"Apellido{n}", usu_tel="3000000000",
                 usu_acepta_datos=True, usu_fec_acepta=timezone.now())
    datos.update(extra)
    return Usuario.objects.create_user(correo or f"u{n}@prueba.co", CLAVE, usu_rol=rol, **datos)


def crear_admin(**extra):
    return crear_usuario(Usuario.ADMIN, **extra)


def crear_donante(anonimo=False, juridica=False, **extra):
    u = crear_usuario(Usuario.DONANTE, **extra)
    PerfilDonante.objects.create(
        usuario=u, don_tipo_persona="juridica" if juridica else "natural", don_tipo_doc="NIT" if juridica else "CC",
        don_doc_nit=f"9{siguiente():08d}", don_raz_soc="Empresa S.A.S." if juridica else "", don_dir="Calle 1",
        don_anonimo_def=anonimo,
    )
    return u


def crear_beneficiario(verificado=False, admin=None, discapacidad=False, **extra):
    u = crear_usuario(Usuario.BENEFICIARIO, **extra)
    PerfilBeneficiario.objects.create(
        usuario=u, ben_tipo_doc="CC", ben_num_doc=f"{siguiente():010d}", ben_fec_exp_doc=date(2015, 1, 1),
        ben_dir="Barrio Centro", ben_num_personas=3, ben_sisben="A", ben_estrato=1, ben_discapacidad=discapacidad,
    )
    if verificado:
        admin = admin or crear_admin()
        tipos = [DocumentoValidacion.IDENTIDAD, DocumentoValidacion.SISBEN, DocumentoValidacion.RESIDENCIA]
        if discapacidad:
            tipos.append(DocumentoValidacion.DISCAPACIDAD)
        for t in tipos:
            doc = usu_srv.cargar_documento(u, t, pdf())
            usu_srv.revisar_documento(doc, admin, True)
        u.refresh_from_db()
    return u


def crear_categoria(nombre=None, dias=None):
    return Categoria.objects.create(cat_nom=nombre or f"Categoría {siguiente()}", cat_dias_alerta=dias)


def crear_bodega(responsable=None):
    responsable = responsable or Usuario.objects.filter(usu_rol=Usuario.ADMIN).first() or crear_admin()
    return Bodega.objects.create(responsable=responsable, bod_nom=f"Bodega {siguiente()}", bod_dir="Calle 2", bod_capacidad="100 kg")


def crear_donacion(donante, productos=None, anonima=False, categoria=None):
    """productos: lista de (nombre, cantidad, días para vencer)."""
    categoria = categoria or crear_categoria()
    if not Bodega.objects.filter(bod_estado="activa").exists():
        crear_bodega()
    productos = productos or [("Arroz", "10", 200)]
    hoy = timezone.localdate()
    detalles = [
        DetalleDonacion(categoria=categoria, dd_nom=n, dd_cantidad=Decimal(q), dd_unidad="kilogramos", dd_fec_venc=hoy + timedelta(days=d))
        for n, q, d in productos
    ]
    return don_srv.registrar(Donacion(donante=donante, dona_anonima=anonima), detalles, donante)


def geocodificador_falso(consulta):
    """Proveedor de mapas de prueba: nunca sale a internet.
    «inexistente» → no se encuentra; «sin servicio» → fallo temporal; lo demás → punto estable cerca de Facatativá."""
    from core.geocodificacion import ErrorGeocodificacion, Resultado

    texto = consulta.lower()
    if "inexistente" in texto:
        return Resultado(False, fuente="prueba")
    if "sin servicio" in texto:
        raise ErrorGeocodificacion("Servicio de prueba caído")
    h = int(hashlib.sha256(texto.encode()).hexdigest()[:8], 16)
    lat = Decimal("4.81") + Decimal(h % 1000) / Decimal(100000)
    lng = Decimal("-74.35") - Decimal((h // 1000) % 1000) / Decimal(100000)
    return Resultado(True, lat.quantize(Decimal("0.000001")), lng.quantize(Decimal("0.000001")), "Centro", "prueba")


class _ConAlmacenamientoTemporal:
    """Usa una carpeta temporal como almacenamiento protegido."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="sysfood_test_")
        cls._override = override_settings(
            PROTECTED_MEDIA_ROOT=__import__("pathlib").Path(cls._tmp) / "protegido",
            BACKUP_ROOT=__import__("pathlib").Path(cls._tmp) / "backups",
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            ALLOWED_HOSTS=["testserver", "localhost"],
        )
        cls._override.enable()
        cls._geo = mock.patch.dict("core.geocodificacion.PROVEEDORES", {"nominatim": geocodificador_falso})
        cls._geo.start()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._geo.stop()
        cls._override.disable()
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def ingresar(self, usuario):
        self.client.force_login(usuario, backend="django.contrib.auth.backends.ModelBackend")
        return usuario


class PruebaBase(_ConAlmacenamientoTemporal, TestCase):
    pass


class PruebaTransaccional(_ConAlmacenamientoTemporal, TransactionTestCase):
    """Para pruebas que vacían la base de datos (restauración de respaldos)."""

    serialized_rollback = True
