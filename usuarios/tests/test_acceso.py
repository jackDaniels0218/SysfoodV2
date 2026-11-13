"""Actividad 1, 10 y 17: registro, autenticación, recuperación y control por rol."""

from datetime import timedelta

from django.core import mail
from django.urls import reverse
from django.utils import timezone

from core.models import Bitacora, Parametro
from core.tests.utilidades import CLAVE, PruebaBase, crear_admin, crear_beneficiario, crear_donante
from sysfood import rnf
from usuarios.models import PerfilBeneficiario, Usuario


def largo_minimo(clave):
    """Alarga la clave hasta la longitud mínima de sysfood/rnf.py, para que las pruebas sigan
    sirviendo si se cambia ese requerimiento."""
    return clave + "x" * max(0, rnf.CONTRASENA_LONGITUD_MINIMA - len(clave))


NUEVA = largo_minimo("OtraClave#2025")
SEGURA = largo_minimo("Segura#2025x")


def datos_registro(rol="donante", **extra):
    datos = {
        "usu_rol": rol,
        "usu_nom": "Laura",
        "usu_ape": "Ruiz",
        "usu_correo": "laura@correo.com",
        "usu_tel": "3101112222",
        "password1": SEGURA,
        "password2": SEGURA,
        "acepta": "on",
        "don-don_tipo_persona": "natural",
        "don-don_tipo_doc": "CC",
        "don-don_doc_nit": "1012345678",
        "don-don_dir": "Cra 1",
        "ben-ben_tipo_doc": "CC",
        "ben-ben_num_doc": "52000111",
        "ben-ben_fec_exp_doc": "2012-03-04",
        "ben-ben_dir": "Cl 9",
        "ben-ben_num_personas": "4",
        "ben-ben_sisben": "B3",
        "ben-ben_estrato": "2",
    }
    datos.update(extra)
    return datos


class RegistroTests(PruebaBase):
    def test_registro_donante_crea_cuenta_con_hash_y_sesion(self):
        r = self.client.post(reverse("usuarios:registro"), datos_registro())
        self.assertRedirects(r, reverse("core:inicio"), target_status_code=302)
        u = Usuario.objects.get(usu_correo="laura@correo.com")
        self.assertEqual(u.usu_rol, Usuario.DONANTE)
        self.assertTrue(u.password.startswith("pbkdf2_sha256$"))
        self.assertNotIn("Segura#2025x", u.password)
        self.assertTrue(u.usu_acepta_datos)
        self.assertIsNotNone(u.usu_fec_acepta)
        self.assertEqual(u.perfil_donante.don_doc_nit, "1012345678")

    def test_registro_beneficiario_queda_pendiente_de_verificacion(self):
        r = self.client.post(reverse("usuarios:registro"), datos_registro("beneficiario"))
        self.assertRedirects(r, reverse("usuarios:documentos"))
        perfil = PerfilBeneficiario.objects.get(usuario__usu_correo="laura@correo.com")
        self.assertEqual(perfil.ben_estado_verif, PerfilBeneficiario.PENDIENTE)

    def test_aceptar_politica_es_obligatorio(self):
        datos = datos_registro()
        datos.pop("acepta")
        r = self.client.post(reverse("usuarios:registro"), datos)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Debe aceptar la política")
        self.assertFalse(Usuario.objects.filter(usu_correo="laura@correo.com").exists())

    def test_correo_unico_y_formato(self):
        crear_donante(correo="laura@correo.com")
        r = self.client.post(reverse("usuarios:registro"), datos_registro(usu_correo="LAURA@correo.com"))
        self.assertContains(r, "Ya existe una cuenta con este correo")
        r = self.client.post(reverse("usuarios:registro"), datos_registro(usu_correo="no-es-correo"))
        self.assertContains(r, "correo electrónico válida")

    def test_confirmacion_y_requisitos_de_contrasena(self):
        r = self.client.post(reverse("usuarios:registro"), datos_registro(password2="Distinta#2025"))
        self.assertContains(r, "Las contraseñas no coinciden")
        if not rnf.CONTRASENA_EXIGE_MAYUSCULA:
            self.skipTest("sysfood/rnf.py no exige mayúsculas")
        sencilla = largo_minimo("sencilla#12")
        r = self.client.post(reverse("usuarios:registro"), datos_registro(password1=sencilla, password2=sencilla))
        self.assertContains(r, "una letra mayúscula")
        self.assertFalse(Usuario.objects.exists())

    def test_fecha_expedicion_futura_y_documento_unico_por_tipo(self):
        futura = (timezone.localdate() + timedelta(days=3)).isoformat()
        r = self.client.post(
            reverse("usuarios:registro"), datos_registro("beneficiario", **{"ben-ben_fec_exp_doc": futura})
        )
        self.assertContains(r, "no puede ser futura")
        existente = crear_beneficiario()
        r = self.client.post(
            reverse("usuarios:registro"),
            datos_registro("beneficiario", **{"ben-ben_num_doc": existente.perfil_beneficiario.ben_num_doc}),
        )
        self.assertContains(r, "Ya existe un beneficiario registrado con este documento")

    def test_juridica_requiere_razon_social_y_nit_unico(self):
        r = self.client.post(
            reverse("usuarios:registro"),
            datos_registro(**{"don-don_tipo_persona": "juridica", "don-don_tipo_doc": "NIT"}),
        )
        self.assertContains(r, "razón social es obligatoria")
        otro = crear_donante()
        r = self.client.post(
            reverse("usuarios:registro"), datos_registro(**{"don-don_doc_nit": otro.perfil_donante.don_doc_nit})
        )
        self.assertContains(r, "Ya existe un donante registrado")


class LoginTests(PruebaBase):
    def setUp(self):
        self.usuario = crear_donante(correo="donante@prueba.co")

    def login(self, clave):
        return self.client.post(reverse("usuarios:login"), {"correo": "donante@prueba.co", "password": clave})

    def test_ingreso_correcto_redirige_al_panel_y_audita(self):
        r = self.login(CLAVE)
        self.assertRedirects(r, reverse("core:inicio"), fetch_redirect_response=False)
        self.assertTrue(Bitacora.objects.filter(bit_accion="ingreso", usuario=self.usuario).exists())
        self.usuario.refresh_from_db()
        self.assertIsNotNone(self.usuario.last_login)
        cookie = self.client.cookies["sessionid"]
        self.assertTrue(cookie["httponly"])

    def test_credenciales_incorrectas_muestran_error(self):
        r = self.login("mala")
        self.assertContains(r, "Correo o contraseña incorrectos")
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.usu_intentos, 1)

    def test_bloqueo_temporal_tras_intentos_fallidos(self):
        for _ in range(rnf.INTENTOS_INGRESO):
            r = self.login("mala")
        self.assertContains(r, f"bloqueada por {rnf.MINUTOS_BLOQUEO} minutos")
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.usu_estado, Usuario.BLOQUEADO)
        r = self.login(CLAVE)
        self.assertContains(r, "bloqueada temporalmente")
        # Al vencer el bloqueo puede volver a ingresar.
        Usuario.objects.filter(pk=self.usuario.pk).update(usu_bloqueo_hasta=timezone.now() - timedelta(minutes=1))
        r = self.login(CLAVE)
        self.assertEqual(r.status_code, 302)
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.usu_estado, Usuario.ACTIVO)
        self.assertEqual(self.usuario.usu_intentos, 0)

    def test_intentos_parametrizables(self):
        Parametro.objects.filter(par_clave="intentos_ingreso").update(par_valor="2")
        self.login("mala")
        self.login("mala")
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.usu_estado, Usuario.BLOQUEADO)

    def test_cuenta_inactiva_no_ingresa(self):
        Usuario.objects.filter(pk=self.usuario.pk).update(usu_estado=Usuario.INACTIVO)
        r = self.login(CLAVE)
        self.assertContains(r, "inactiva")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_cerrar_sesion(self):
        self.login(CLAVE)
        r = self.client.post(reverse("usuarios:logout"))
        self.assertRedirects(r, reverse("usuarios:login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_desactivar_cierra_sesiones_activas(self):
        self.ingresar(self.usuario)
        Usuario.objects.filter(pk=self.usuario.pk).update(usu_estado=Usuario.INACTIVO)
        r = self.client.get(reverse("donaciones:mis_donaciones"))
        self.assertEqual(r.status_code, 302)


class RecuperacionTests(PruebaBase):
    def setUp(self):
        self.usuario = crear_beneficiario(correo="ben@prueba.co")

    def _token(self):
        self.client.post(reverse("usuarios:recuperar"), {"correo": "ben@prueba.co"})
        self.assertEqual(len(mail.outbox), 1)
        enlace = next(linea for linea in mail.outbox[0].body.splitlines() if "/restablecer/" in linea)
        return enlace.rstrip("/").split("/")[-1]

    def test_flujo_completo_y_token_de_un_solo_uso(self):
        token = self._token()
        self.usuario.refresh_from_db()
        self.assertNotEqual(self.usuario.usu_token_rec, token)  # Solo se guarda la huella.
        url = reverse("usuarios:restablecer", args=[token])
        r = self.client.post(url, {"password1": NUEVA, "password2": NUEVA})
        self.assertRedirects(r, reverse("usuarios:login"))
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(NUEVA))
        self.assertEqual(self.usuario.usu_token_rec, "")
        r = self.client.get(url)
        self.assertRedirects(r, reverse("usuarios:recuperar"))

    def test_token_vencido(self):
        token = self._token()
        Usuario.objects.filter(pk=self.usuario.pk).update(usu_token_exp=timezone.now() - timedelta(seconds=1))
        r = self.client.get(reverse("usuarios:restablecer", args=[token]))
        self.assertRedirects(r, reverse("usuarios:recuperar"))

    def test_correo_no_registrado_no_revela_informacion(self):
        r = self.client.post(reverse("usuarios:recuperar"), {"correo": "nadie@prueba.co"}, follow=True)
        self.assertContains(r, "Si el correo está registrado")
        self.assertEqual(len(mail.outbox), 0)

    def test_nueva_contrasena_debe_ser_segura(self):
        token = self._token()
        r = self.client.post(reverse("usuarios:restablecer", args=[token]), {"password1": "abc", "password2": "abc"})
        self.assertEqual(r.status_code, 200)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(CLAVE))


class ControlPorRolTests(PruebaBase):
    """Se niega el acceso directo por dirección a páginas no autorizadas."""

    URLS_ADMIN = [
        "usuarios:lista",
        "usuarios:crear",
        "usuarios:documentos_pendientes",
        "catalogo:categorias",
        "catalogo:bodegas",
        "inventario:lista",
        "donaciones:lista_admin",
        "solicitudes:lista_admin",
        "entregas:lista",
        "core:parametros",
        "core:trazabilidad",
        "reportes:reportes",
    ]

    def test_anonimo_es_enviado_a_ingresar(self):
        for nombre in self.URLS_ADMIN + ["donaciones:nueva", "solicitudes:catalogo", "core:notificaciones"]:
            r = self.client.get(reverse(nombre))
            self.assertEqual(r.status_code, 302, nombre)
            self.assertIn(reverse("usuarios:login"), r.url)

    def test_donante_y_beneficiario_no_acceden_a_paginas_de_administrador(self):
        for usuario in (crear_donante(), crear_beneficiario(verificado=True)):
            self.ingresar(usuario)
            for nombre in self.URLS_ADMIN:
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 403, (usuario.usu_rol, nombre))

    def test_paginas_de_otro_rol(self):
        self.ingresar(crear_beneficiario(verificado=True))
        self.assertEqual(self.client.get(reverse("donaciones:nueva")).status_code, 403)
        self.ingresar(crear_donante())
        self.assertEqual(self.client.get(reverse("solicitudes:catalogo")).status_code, 403)
        self.assertEqual(self.client.get(reverse("entregas:seguimiento")).status_code, 403)
        self.ingresar(crear_admin())
        self.assertEqual(self.client.get(reverse("donaciones:nueva")).status_code, 403)

    def test_panel_por_rol(self):
        for usuario, texto in (
            (crear_admin(), "Panel del administrador"),
            (crear_donante(), "Registrar donación"),
            (crear_beneficiario(), "Estado de verificación"),
        ):
            self.ingresar(usuario)
            r = self.client.get(reverse("reportes:dashboard"))
            self.assertContains(r, texto)
