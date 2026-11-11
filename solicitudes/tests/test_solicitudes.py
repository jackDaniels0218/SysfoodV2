"""Actividad 7 y 11: catálogo, carrito y solicitudes."""

from django.core.exceptions import ValidationError
from django.urls import reverse

from core.models import Notificacion, Parametro
from core.tests.utilidades import PruebaBase, crear_admin, crear_beneficiario, crear_donacion, crear_donante
from entregas.models import Entrega
from inventario.models import Inventario, Kardex
from solicitudes import servicios
from solicitudes.models import CarritoItem, Solicitud


class CatalogoCarritoTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin()
        self.donante = crear_donante()
        crear_donacion(self.donante, productos=[(f"Producto {i}", "10", 100) for i in range(7)])
        self.ben = self.ingresar(crear_beneficiario(verificado=True, admin=self.admin))
        self.items = list(Inventario.objects.order_by("inv_id"))

    def test_catalogo_busqueda_y_filtro(self):
        r = self.client.get(reverse("solicitudes:catalogo"), {"q": "Producto 3"})
        self.assertEqual([i.inv_nom for i in r.context["pagina"]], ["Producto 3"])
        r = self.client.get(reverse("solicitudes:catalogo"), {"categoria": self.items[0].categoria_id})
        self.assertEqual(r.context["pagina"].paginator.count, 7)

    def test_catalogo_oculta_agotados_retirados_y_vencidos(self):
        from inventario import servicios as inv_srv

        inv_srv.ajustar(self.items[0], 0, "Agotado", self.admin)
        inv_srv.dar_baja(self.items[1], "danado", "", self.admin)
        from datetime import timedelta

        from django.utils import timezone

        Inventario.objects.filter(pk=self.items[2].pk).update(inv_fec_venc=timezone.localdate() - timedelta(days=1))
        r = self.client.get(reverse("solicitudes:catalogo"))
        visibles = {i.pk for i in r.context["pagina"]}
        self.assertEqual(visibles, {i.pk for i in self.items[3:]})

    def test_agregar_quitar_y_vaciar(self):
        self.client.post(reverse("solicitudes:agregar", args=[self.items[0].pk]), {"cantidad": "2"})
        self.client.post(reverse("solicitudes:agregar", args=[self.items[1].pk]), {"cantidad": "1,5"})
        self.assertEqual(CarritoItem.objects.filter(beneficiario=self.ben).count(), 2)
        item = CarritoItem.objects.get(inventario=self.items[1])
        self.assertEqual(str(item.car_cant), "1.50")
        self.assertIsNotNone(item.car_fec_agregado)
        self.client.post(reverse("solicitudes:quitar", args=[item.pk]))
        self.assertEqual(CarritoItem.objects.count(), 1)
        self.client.post(reverse("solicitudes:vaciar"))
        self.assertEqual(CarritoItem.objects.count(), 0)

    def test_maximo_cinco_productos_distintos(self):
        for inv in self.items[:5]:
            servicios.agregar_al_carrito(self.ben, inv, "1")
        with self.assertRaisesMessage(ValidationError, "máximo 5 productos"):
            servicios.agregar_al_carrito(self.ben, self.items[5], "1")
        servicios.agregar_al_carrito(self.ben, self.items[0], "3")  # Actualizar uno existente sí se permite.
        Parametro.objects.filter(par_clave="max_productos_solicitud").update(par_valor="6")
        servicios.agregar_al_carrito(self.ben, self.items[5], "1")
        self.assertEqual(CarritoItem.objects.count(), 6)

    def test_cantidad_no_supera_la_disponible(self):
        r = self.client.post(reverse("solicitudes:agregar", args=[self.items[0].pk]), {"cantidad": "11"}, follow=True)
        self.assertContains(r, "supera la disponible")
        r = self.client.post(reverse("solicitudes:agregar", args=[self.items[0].pk]), {"cantidad": "-1"}, follow=True)
        self.assertContains(r, "mayor que cero")
        self.assertFalse(CarritoItem.objects.exists())

    def test_enviar_convierte_en_solicitud_pendiente_y_notifica(self):
        servicios.agregar_al_carrito(self.ben, self.items[0], "2")
        servicios.agregar_al_carrito(self.ben, self.items[1], "3")
        r = self.client.post(reverse("solicitudes:enviar"))
        sol = Solicitud.objects.get()
        self.assertRedirects(r, reverse("solicitudes:detalle", args=[sol.pk]))
        self.assertEqual(sol.sol_estado, Solicitud.PENDIENTE)
        self.assertEqual(sol.detalles.count(), 2)
        self.assertFalse(CarritoItem.objects.exists())
        self.assertTrue(Notificacion.objects.filter(destinatario=self.admin, not_tipo="solicitud").exists())
        # Una solicitud pendiente todavía no reserva.
        self.assertEqual(Inventario.objects.get(pk=self.items[0].pk).inv_cant_reserv, 0)

    def test_beneficiario_solo_ve_sus_solicitudes(self):
        servicios.agregar_al_carrito(self.ben, self.items[0], "1")
        sol = servicios.enviar_solicitud(self.ben)
        self.ingresar(crear_beneficiario(verificado=True, admin=self.admin))
        self.assertEqual(self.client.get(reverse("solicitudes:detalle", args=[sol.pk])).status_code, 404)


class RevisionSolicitudesTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin()
        self.donante = crear_donante()
        crear_donacion(self.donante, productos=[("Arroz", "10", 100), ("Atún", "4", 200)])
        self.arroz, self.atun = Inventario.objects.get(inv_nom="Arroz"), Inventario.objects.get(inv_nom="Atún")
        self.ben = crear_beneficiario(verificado=True, admin=self.admin)
        servicios.agregar_al_carrito(self.ben, self.arroz, "6")
        servicios.agregar_al_carrito(self.ben, self.atun, "4")
        self.sol = servicios.enviar_solicitud(self.ben)
        self.ingresar(self.admin)
        self.url = reverse("solicitudes:admin_detalle", args=[self.sol.pk])

    def test_admin_ve_detalle_completo(self):
        r = self.client.get(self.url)
        self.assertContains(r, self.ben.nombre_completo)
        self.assertContains(r, self.ben.perfil_beneficiario.ben_num_doc)
        self.assertContains(r, "Arroz")

    def test_aprobar_reserva_y_genera_entrega(self):
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(
                self.url,
                {"accion": "aprobar", "ap-modalidad": "domicilio", "ap-direccion": "Cl 5", "ap-fecha_prog": ""},
            )
        entrega = Entrega.objects.get()
        self.assertRedirects(r, reverse("entregas:detalle", args=[entrega.pk]))
        self.sol.refresh_from_db()
        self.assertEqual((self.sol.sol_estado, self.sol.revisor), (Solicitud.APROBADA, self.admin))
        self.assertIsNotNone(self.sol.sol_fec_resp)
        self.assertEqual(entrega.ent_estado, Entrega.EN_REVISION)
        self.assertTrue(entrega.ent_cod.startswith("SF-"))
        self.assertEqual(entrega.ent_dir_entrega, "Cl 5")
        self.arroz.refresh_from_db()
        self.assertEqual((self.arroz.inv_cant_disp, self.arroz.inv_cant_reserv), (4, 6))
        self.assertTrue(Kardex.objects.filter(kar_tipo=Kardex.RESERVA, entrega=entrega).count() == 2)
        self.assertEqual(entrega.historial.count(), 1)
        self.assertTrue(Notificacion.objects.filter(destinatario=self.ben, not_tipo="solicitud").exists())
        aviso = Notificacion.objects.get(destinatario=self.donante, not_tipo="reserva")
        self.assertNotIn(self.ben.usu_nom, aviso.not_mensaje)

    def test_domicilio_exige_direccion(self):
        r = self.client.post(self.url, {"accion": "aprobar", "ap-modalidad": "domicilio", "ap-direccion": ""})
        self.assertContains(r, "Indique la dirección")
        self.assertFalse(Entrega.objects.exists())

    def test_aprobacion_es_todo_o_nada(self):
        from inventario import servicios as inv_srv

        inv_srv.ajustar(self.atun, 1, "Faltante", self.admin)  # Ya no alcanza para el atún.
        r = self.client.post(self.url, {"accion": "aprobar", "ap-modalidad": "recogida"})
        self.assertContains(r, "No hay cantidad suficiente")
        self.arroz.refresh_from_db()
        self.assertEqual((self.arroz.inv_cant_disp, self.arroz.inv_cant_reserv), (10, 0))
        self.assertFalse(Entrega.objects.exists())
        self.sol.refresh_from_db()
        self.assertEqual(self.sol.sol_estado, Solicitud.PENDIENTE)

    def test_rechazar_exige_motivo(self):
        r = self.client.post(self.url, {"accion": "rechazar", "mo-observacion": ""})
        self.assertContains(r, "El motivo es obligatorio")
        self.client.post(self.url, {"accion": "rechazar", "mo-observacion": "Sin cupo"})
        self.sol.refresh_from_db()
        self.assertEqual((self.sol.sol_estado, self.sol.sol_obs_admin), (Solicitud.RECHAZADA, "Sin cupo"))

    def test_cancelar_aprobada_libera_lo_reservado(self):
        servicios.aprobar(self.sol, self.admin, "recogida")
        self.client.post(self.url, {"accion": "cancelar", "mo-observacion": "El beneficiario desistió"})
        self.sol.refresh_from_db()
        self.assertEqual(self.sol.sol_estado, Solicitud.CANCELADA)
        self.arroz.refresh_from_db()
        self.assertEqual((self.arroz.inv_cant_disp, self.arroz.inv_cant_reserv), (10, 0))
        self.assertEqual(Entrega.objects.get().ent_estado, Entrega.CANCELADO)
        self.assertTrue(Kardex.objects.filter(kar_tipo=Kardex.LIBERACION).exists())
