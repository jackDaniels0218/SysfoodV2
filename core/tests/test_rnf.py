"""Los requerimientos no funcionales se toman de sysfood/rnf.py, un solo archivo."""

from unittest import mock

from django.conf import settings
from django.contrib.auth.hashers import get_hasher
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.test import SimpleTestCase
from django.urls import reverse

from core import parametros
from core.models import Bitacora, Parametro
from core.tests.utilidades import PruebaBase, crear_admin, crear_donante
from sysfood import rnf
from usuarios.validators import ComplejidadValidator


class ConfiguracionTests(SimpleTestCase):
    """La configuración de Django sale de rnf.py."""

    def test_sesion(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, rnf.SESION_MINUTOS * 60)
        self.assertEqual(settings.SESSION_SAVE_EVERY_REQUEST, rnf.SESION_POR_INACTIVIDAD)
        self.assertEqual(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE, rnf.SESION_CERRAR_CON_NAVEGADOR)

    def test_idioma_zona_y_limites(self):
        self.assertEqual(settings.LANGUAGE_CODE, rnf.IDIOMA)
        self.assertEqual(settings.TIME_ZONE, rnf.ZONA_HORARIA)
        self.assertEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, rnf.LIMITE_FORMULARIO_MB * 1024 * 1024)
        self.assertEqual(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, rnf.LIMITE_ARCHIVO_EN_MEMORIA_MB * 1024 * 1024)

    def test_iteraciones_pbkdf2(self):
        from core.hashers import PBKDF2SysFood

        self.assertEqual(PBKDF2SysFood.iterations, rnf.CONTRASENA_ITERACIONES_PBKDF2)
        self.assertIn("core.hashers.PBKDF2SysFood", settings.PASSWORD_HASHERS)
        # Mismo nombre de algoritmo que el de Django: las contraseñas ya guardadas siguen sirviendo.
        self.assertEqual(PBKDF2SysFood.algorithm, get_hasher("pbkdf2_sha256").algorithm)

    def test_los_parametros_toman_su_valor_por_defecto_de_rnf(self):
        for clave, valor in rnf.PARAMETROS.items():
            self.assertEqual(parametros.DEFINICIONES[clave].valor, str(valor), clave)


class ContrasenaTests(SimpleTestCase):
    def _clave(self, largo):
        base = "Aa1#"
        return (base * largo)[:largo]

    def test_longitud_minima(self):
        with self.assertRaises(ValidationError):
            validate_password(self._clave(rnf.CONTRASENA_LONGITUD_MINIMA - 1))
        validate_password(self._clave(max(rnf.CONTRASENA_LONGITUD_MINIMA, 8)))

    def test_complejidad_configurable(self):
        validador = ComplejidadValidator()
        with self.assertRaises(ValidationError):
            validador.validate("sinsimbolo123A")
        with mock.patch.object(rnf, "CONTRASENA_EXIGE_ESPECIAL", False):
            validador.validate("sinsimbolo123A")

    def test_texto_de_requisitos(self):
        texto = rnf.requisitos_contrasena()
        self.assertIn(f"al menos {rnf.CONTRASENA_LONGITUD_MINIMA} caracteres", texto)
        with (
            mock.patch.object(rnf, "CONTRASENA_EXIGE_MAYUSCULA", False),
            mock.patch.object(rnf, "CONTRASENA_EXIGE_MINUSCULA", False),
            mock.patch.object(rnf, "CONTRASENA_EXIGE_NUMERO", False),
        ):
            self.assertNotIn("mayúsculas", rnf.requisitos_contrasena())
            self.assertTrue(rnf.requisitos_contrasena().endswith("con un símbolo"))


class PaginacionTests(PruebaBase):
    def test_registros_por_pagina(self):
        self.ingresar(crear_admin())
        for _ in range(3):
            crear_donante()
        with mock.patch.dict(rnf.REGISTROS_POR_PAGINA, {"usuarios": 2}):
            r = self.client.get(reverse("usuarios:lista"))
        self.assertEqual(len(r.context["pagina"].object_list), 2)

    def test_lista_desconocida_usa_20(self):
        self.assertEqual(rnf.por_pagina("no-existe"), 20)


class ValoresDesdeElCodigoTests(PruebaBase):
    """Un cambio en rnf.py se aplica a Parámetros al arrancar, sin pisar lo que cambie el administrador."""

    def _valor(self, clave):
        return Parametro.objects.get(par_clave=clave).par_valor

    def test_cambio_en_el_codigo_se_aplica_y_se_audita(self):
        otro = rnf.INTENTOS_INGRESO % 20 + 1  # Siempre distinto del valor actual y dentro del rango.
        with mock.patch.dict(rnf.PARAMETROS, {"intentos_ingreso": otro}):
            self.assertEqual(parametros.aplicar_desde_codigo(), ["intentos_ingreso"])
            self.assertEqual(self._valor("intentos_ingreso"), str(otro))
            registro = Bitacora.objects.get(bit_accion="cambio_parametro", bit_registro="intentos_ingreso")
            self.assertIn("sysfood/rnf.py", registro.bit_detalle)
            # Al volver a arrancar sin otro cambio en el código no se toca nada.
            self.assertEqual(parametros.aplicar_desde_codigo(), [])

    def test_respeta_el_cambio_del_administrador_mientras_el_codigo_no_cambie(self):
        Parametro.objects.filter(par_clave="minutos_bloqueo").update(par_valor="30")
        self.assertEqual(parametros.aplicar_desde_codigo(), [])
        self.assertEqual(self._valor("minutos_bloqueo"), "30")

    def test_valor_invalido_en_el_codigo_detiene_el_arranque(self):
        with (
            mock.patch.dict(rnf.PARAMETROS, {"tam_max_archivo_mb": 99}),
            self.assertRaisesMessage(ImproperlyConfigured, "tam_max_archivo_mb"),
        ):
            parametros.aplicar_desde_codigo()

    def test_el_bloqueo_usa_el_valor_aplicado(self):
        donante = crear_donante(correo="rnf@prueba.co")
        with mock.patch.dict(rnf.PARAMETROS, {"intentos_ingreso": 2}):
            parametros.aplicar_desde_codigo()
        for _ in range(2):
            self.client.post(reverse("usuarios:login"), {"correo": "rnf@prueba.co", "password": "mala"})
        donante.refresh_from_db()
        self.assertEqual(donante.usu_estado, donante.BLOQUEADO)
