"""Actividad 1: CRUD de usuarios por el administrador (baja lógica)."""

from django.urls import reverse

from core.models import Bitacora
from core.tests.utilidades import PruebaBase, crear_admin, crear_beneficiario, crear_donacion, crear_donante
from usuarios.models import Usuario


class AdminUsuariosTests(PruebaBase):
    def setUp(self):
        self.admin = self.ingresar(crear_admin())

    def test_crear_beneficiario_desde_administracion(self):
        datos = {
            "usu_rol": "beneficiario",
            "usu_correo": "nuevo@prueba.co",
            "usu_nom": "Ana",
            "usu_ape": "Paz",
            "usu_tel": "3001231234",
            "usu_estado": "activo",
            "password1": "Segura#2025x",
            "password2": "Segura#2025x",
            "ben-ben_tipo_doc": "TI",
            "ben-ben_num_doc": "1001",
            "ben-ben_fec_exp_doc": "2020-01-01",
            "ben-ben_dir": "Cl 1",
            "ben-ben_num_personas": "2",
            "ben-ben_sisben": "NR",
            "ben-ben_estrato": "3",
        }
        r = self.client.post(reverse("usuarios:crear"), datos)
        u = Usuario.objects.get(usu_correo="nuevo@prueba.co")
        self.assertRedirects(r, reverse("usuarios:revisar_usuario", args=[u.pk]))
        self.assertEqual(u.perfil_beneficiario.ben_tipo_doc, "TI")
        self.assertTrue(
            Bitacora.objects.filter(bit_accion="crear", bit_entidad="usuario", bit_registro=str(u.pk)).exists()
        )

    def test_crear_administrador_sin_datos_adicionales(self):
        datos = {
            "usu_rol": "administrador",
            "usu_correo": "otro@prueba.co",
            "usu_nom": "B",
            "usu_ape": "C",
            "usu_tel": "3000000001",
            "usu_estado": "activo",
            "password1": "Segura#2025x",
            "password2": "Segura#2025x",
        }
        self.client.post(reverse("usuarios:crear"), datos)
        self.assertTrue(Usuario.objects.filter(usu_correo="otro@prueba.co", usu_rol="administrador").exists())

    def test_consultar_filtrar_y_editar(self):
        don = crear_donante(usu_nom="Zacarías")
        r = self.client.get(reverse("usuarios:lista"), {"q": "Zacar", "rol": "donante"})
        self.assertContains(r, "Zacarías")
        perfil = don.perfil_donante
        datos = {
            "usu_correo": don.usu_correo,
            "usu_nom": "Zacarías",
            "usu_ape": "Nuevo",
            "usu_tel": "3009998888",
            "usu_estado": "activo",
            "don-don_tipo_persona": "natural",
            "don-don_tipo_doc": "CC",
            "don-don_doc_nit": perfil.don_doc_nit,
            "don-don_dir": "Nueva dir",
        }
        r = self.client.post(reverse("usuarios:editar", args=[don.pk]), datos)
        self.assertEqual(r.status_code, 302)
        don.refresh_from_db()
        self.assertEqual(don.usu_ape, "Nuevo")
        self.assertEqual(don.perfil_donante.don_dir, "Nueva dir")
        self.assertEqual(don.usu_rol, "donante")

    def test_desactivar_y_desbloquear(self):
        don = crear_donante()
        self.client.post(reverse("usuarios:cambiar_estado", args=[don.pk]), {"estado": "inactivo"})
        don.refresh_from_db()
        self.assertEqual(don.usu_estado, Usuario.INACTIVO)
        Usuario.objects.filter(pk=don.pk).update(usu_estado=Usuario.BLOQUEADO, usu_intentos=5)
        self.client.post(reverse("usuarios:cambiar_estado", args=[don.pk]), {"estado": "activo"})
        don.refresh_from_db()
        self.assertEqual((don.usu_estado, don.usu_intentos), (Usuario.ACTIVO, 0))

    def test_usuario_con_registros_se_desactiva_en_vez_de_eliminarse(self):
        don = crear_donante()
        crear_donacion(don)
        self.client.post(reverse("usuarios:eliminar", args=[don.pk]))
        don.refresh_from_db()
        self.assertEqual(don.usu_estado, Usuario.INACTIVO)

    def test_usuario_sin_registros_se_elimina(self):
        ben = crear_beneficiario()
        self.client.post(reverse("usuarios:eliminar", args=[ben.pk]))
        self.assertFalse(Usuario.objects.filter(pk=ben.pk).exists())

    def test_no_puede_desactivarse_a_si_mismo(self):
        self.client.post(reverse("usuarios:cambiar_estado", args=[self.admin.pk]), {"estado": "inactivo"})
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.usu_estado, Usuario.ACTIVO)


class PerfilPropioTests(PruebaBase):
    def test_usuario_edita_sus_datos_pero_no_su_estado_de_verificacion(self):
        ben = self.ingresar(crear_beneficiario())
        p = ben.perfil_beneficiario
        datos = {
            "usu_correo": ben.usu_correo,
            "usu_nom": "Nuevo",
            "usu_ape": ben.usu_ape,
            "usu_tel": "3112223344",
            "ben-ben_tipo_doc": p.ben_tipo_doc,
            "ben-ben_num_doc": p.ben_num_doc,
            "ben-ben_fec_exp_doc": "2015-01-01",
            "ben-ben_dir": "Otra",
            "ben-ben_num_personas": "5",
            "ben-ben_sisben": "C",
            "ben-ben_estrato": "2",
            "ben-ben_estado_verif": "verificado",
        }
        r = self.client.post(reverse("usuarios:perfil"), datos)
        self.assertRedirects(r, reverse("usuarios:perfil"))
        ben.refresh_from_db()
        self.assertEqual(ben.usu_nom, "Nuevo")
        self.assertEqual(ben.perfil_beneficiario.ben_num_personas, 5)
        self.assertEqual(ben.perfil_beneficiario.ben_estado_verif, "pendiente")
