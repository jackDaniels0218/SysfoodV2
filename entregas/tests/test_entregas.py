"""Actividad 8 y 14: entregas, estados, historial y seguimiento."""
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from core.models import Notificacion
from core.tests.utilidades import PruebaBase, crear_admin, crear_beneficiario, crear_donacion, crear_donante
from donaciones.models import Donacion
from entregas import servicios
from entregas.models import Entrega, HistorialEntrega
from inventario.models import Inventario, Kardex
from solicitudes import servicios as sol_srv
from solicitudes.models import Solicitud


class EntregasTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin()
        self.donante = crear_donante()
        self.donacion = crear_donacion(self.donante, productos=[("Arroz", "10", 100)])
        self.arroz = Inventario.objects.get()
        self.ben = crear_beneficiario(verificado=True, admin=self.admin)
        sol_srv.agregar_al_carrito(self.ben, self.arroz, "4")
        self.entrega = sol_srv.aprobar(sol_srv.enviar_solicitud(self.ben), self.admin, "recogida")

    def avanzar(self, veces=1, **kw):
        for _ in range(veces):
            self.entrega = servicios.avanzar(self.entrega, self.admin, **kw)

    def test_transiciones_permitidas_y_historial(self):
        self.avanzar()
        self.assertEqual(self.entrega.ent_estado, Entrega.EN_BODEGA)
        self.avanzar()
        self.assertEqual(self.entrega.ent_estado, Entrega.EN_ENTREGA)
        self.avanzar()
        self.assertEqual(self.entrega.ent_estado, Entrega.ENTREGADO)
        with self.assertRaises(ValidationError):
            self.avanzar()
        estados = list(self.entrega.historial.values_list("his_estado_ant", "his_estado_nuevo"))
        self.assertEqual(estados, [("", "en_revision"), ("en_revision", "en_bodega"), ("en_bodega", "en_entrega"), ("en_entrega", "entregado")])

    def test_entregado_descuenta_definitivamente(self):
        self.avanzar(3)
        self.arroz.refresh_from_db()
        self.assertEqual((self.arroz.inv_cant_disp, self.arroz.inv_cant_reserv), (6, 0))
        self.assertIsNotNone(self.entrega.ent_fec_entrega)
        det = self.entrega.detalles.get()
        self.assertEqual(det.de_cant_entregada, 4)
        self.assertTrue(Kardex.objects.filter(kar_tipo=Kardex.ENTREGA, entrega=self.entrega, kar_cantidad=4).exists())

    def test_entrega_parcial_devuelve_lo_no_entregado(self):
        self.avanzar(2)
        det = self.entrega.detalles.get()
        self.avanzar(cantidades={det.pk: Decimal("3")})
        self.arroz.refresh_from_db()
        self.assertEqual((self.arroz.inv_cant_disp, self.arroz.inv_cant_reserv), (7, 0))

    def test_donacion_entregada_cuando_todo_sale(self):
        sol_srv.agregar_al_carrito(self.ben, Inventario.objects.get(), "6")
        otra = sol_srv.aprobar(sol_srv.enviar_solicitud(self.ben), self.admin, "recogida")
        self.avanzar(3)
        for _ in range(3):
            otra = servicios.avanzar(otra, self.admin)
        self.donacion.refresh_from_db()
        self.assertEqual(self.donacion.dona_estado, Donacion.ENTREGADA)

    def test_cancelar_exige_motivo_y_libera(self):
        with self.assertRaises(ValidationError):
            servicios.cancelar(self.entrega, self.admin, "")
        self.avanzar()
        servicios.cancelar(self.entrega, self.admin, "Beneficiario no responde")
        self.entrega.refresh_from_db()
        self.assertEqual((self.entrega.ent_estado, self.entrega.ent_mot_cancel), (Entrega.CANCELADO, "Beneficiario no responde"))
        self.arroz.refresh_from_db()
        self.assertEqual((self.arroz.inv_cant_disp, self.arroz.inv_cant_reserv), (10, 0))
        self.assertEqual(Solicitud.objects.get().sol_estado, Solicitud.CANCELADA)

    def test_no_se_cancela_una_entrega_entregada(self):
        self.avanzar(3)
        with self.assertRaises(ValidationError):
            servicios.cancelar(self.entrega, self.admin, "Tarde")

    def test_historial_inmutable(self):
        h = HistorialEntrega.objects.first()
        with self.assertRaises(PermissionDenied):
            h.save()
        with self.assertRaises(PermissionDenied):
            h.delete()

    def test_notificaciones_sin_datos_del_beneficiario(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.avanzar()
        self.assertTrue(Notificacion.objects.filter(destinatario=self.ben, not_tipo="entrega").exists())
        aviso = Notificacion.objects.filter(destinatario=self.donante, not_tipo="entrega").get()
        for dato in (self.ben.usu_nom, self.ben.usu_ape, self.ben.perfil_beneficiario.ben_dir, self.entrega.ent_cod):
            self.assertNotIn(dato, aviso.not_mensaje + aviso.not_titulo)

    def test_vistas_del_administrador(self):
        self.ingresar(self.admin)
        url = reverse("entregas:detalle", args=[self.entrega.pk])
        self.assertContains(self.client.get(reverse("entregas:lista")), self.entrega.ent_cod)
        r = self.client.post(reverse("entregas:actualizar", args=[self.entrega.pk]), {
            "ent_modalidad": "domicilio", "ent_dir_entrega": "", "ent_fec_prog": "", "responsable": self.admin.pk, "ent_obs": ""}, follow=True)
        self.assertContains(r, "Indique la dirección")
        self.client.post(reverse("entregas:avanzar", args=[self.entrega.pk]), {"observacion": "Alistado"})
        self.assertContains(self.client.get(url), "En bodega")
        self.client.post(reverse("entregas:cancelar", args=[self.entrega.pk]), {"motivo": "Sin transporte"})
        self.entrega.refresh_from_db()
        self.assertEqual(self.entrega.ent_estado, Entrega.CANCELADO)

    def test_seguimiento_por_codigo_solo_del_propio_beneficiario(self):
        self.ingresar(self.ben)
        r = self.client.get(reverse("entregas:seguimiento"), {"codigo": self.entrega.ent_cod.lower()})
        self.assertEqual(r.context["e"], self.entrega)
        self.assertContains(r, "En revisión")
        self.ingresar(crear_beneficiario(verificado=True, admin=self.admin))
        r = self.client.get(reverse("entregas:seguimiento"), {"codigo": self.entrega.ent_cod})
        self.assertIsNone(r.context["e"])
        self.assertContains(r, "No encontramos una entrega suya")
