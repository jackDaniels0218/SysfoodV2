"""Actividad 6, 12 y 19: inventario, kardex, control de vencimientos e integridad."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from core.models import Notificacion
from core.tareas import ejecutar_control_diario
from core.tests.utilidades import (
    PruebaBase,
    crear_admin,
    crear_beneficiario,
    crear_categoria,
    crear_donacion,
    crear_donante,
)
from donaciones.models import Donacion
from inventario import servicios
from inventario.models import Inventario, Kardex
from solicitudes import servicios as sol_srv
from solicitudes.models import CarritoItem


class InventarioAdminTests(PruebaBase):
    def setUp(self):
        self.admin = self.ingresar(crear_admin())
        self.donante = crear_donante()
        crear_donacion(self.donante, productos=[("Arroz", "10", 100), ("Leche", "6", 2), ("Pasta", "4", 30)])
        self.arroz = Inventario.objects.get(inv_nom="Arroz")

    def test_lista_ordenada_por_vencimiento_con_filtros(self):
        r = self.client.get(reverse("inventario:lista"))
        nombres = [i.inv_nom for i in r.context["pagina"]]
        self.assertEqual(nombres, ["Leche", "Pasta", "Arroz"])
        self.assertContains(r, "fila-proximo")
        r = self.client.get(reverse("inventario:lista"), {"q": "arr"})
        self.assertEqual([i.inv_nom for i in r.context["pagina"]], ["Arroz"])
        r = self.client.get(reverse("inventario:lista"), {"vigencia": "proximo"})
        self.assertEqual([i.inv_nom for i in r.context["pagina"]], ["Leche"])

    def test_ajuste_exige_motivo_y_queda_en_kardex(self):
        r = self.client.post(
            reverse("inventario:ajustar", args=[self.arroz.pk]), {"nueva_cantidad": "8", "motivo": ""}, follow=True
        )
        self.assertContains(r, "exige una cantidad válida")
        self.client.post(
            reverse("inventario:ajustar", args=[self.arroz.pk]), {"nueva_cantidad": "8", "motivo": "Conteo físico"}
        )
        self.arroz.refresh_from_db()
        self.assertEqual(self.arroz.inv_cant_disp, 8)
        k = self.arroz.kardex.get(kar_tipo=Kardex.AJUSTE)
        self.assertEqual(
            (k.kar_cant_anterior, k.kar_cant_resultante, k.kar_motivo, k.usuario), (10, 8, "Conteo físico", self.admin)
        )

    def test_cantidad_nunca_negativa(self):
        with self.assertRaises(ValidationError):
            servicios.ajustar(self.arroz, Decimal("-1"), "Error", self.admin)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Inventario.objects.filter(pk=self.arroz.pk).update(inv_cant_disp=-5)

    def test_baja_logica_con_motivo(self):
        self.client.post(reverse("inventario:baja", args=[self.arroz.pk]), {"motivo": "danado", "detalle": "Humedad"})
        self.arroz.refresh_from_db()
        self.assertEqual(self.arroz.inv_estado, Inventario.RETIRADO)
        self.assertEqual((self.arroz.inv_mot_baja, self.arroz.usuario_baja), ("danado", self.admin))
        self.assertIsNotNone(self.arroz.inv_fec_baja)
        self.assertTrue(Inventario.objects.filter(pk=self.arroz.pk).exists())
        r = self.client.post(
            reverse("inventario:baja", args=[Inventario.objects.get(inv_nom="Pasta").pk]),
            {"motivo": "otro"},
            follow=True,
        )
        self.assertContains(r, "Describa el motivo")

    def test_no_se_retira_con_entregas_pendientes(self):
        ben = crear_beneficiario(verificado=True, admin=self.admin)
        sol_srv.agregar_al_carrito(ben, self.arroz, "3")
        entrega = sol_srv.aprobar(sol_srv.enviar_solicitud(ben), self.admin, "recogida")
        with self.assertRaisesMessage(ValidationError, "Cancele antes esas entregas"):
            servicios.dar_baja(self.arroz, "danado", "", self.admin)
        from entregas import servicios as ent_srv

        ent_srv.cancelar(entrega, self.admin, "Producto dañado")
        servicios.dar_baja(self.arroz, "danado", "", self.admin)
        self.arroz.refresh_from_db()
        self.assertEqual(self.arroz.inv_estado, Inventario.RETIRADO)

    def test_kardex_es_inmutable(self):
        k = Kardex.objects.first()
        k.kar_motivo = "alterado"
        with self.assertRaises(PermissionDenied):
            k.save()
        with self.assertRaises(PermissionDenied):
            k.delete()

    def test_retirar_vencidos(self):
        Inventario.objects.filter(inv_nom="Leche").update(inv_fec_venc=timezone.localdate() - timedelta(days=1))
        ejecutar_control_diario(forzar=True)
        self.client.post(reverse("inventario:retirar_vencidos"))
        leche = Inventario.objects.get(inv_nom="Leche")
        self.assertEqual((leche.inv_estado, leche.inv_mot_baja), (Inventario.RETIRADO, "vencido"))


class ControlVencimientosTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin()
        self.donante = crear_donante()
        self.cat = crear_categoria(dias=10)
        self.donacion = crear_donacion(
            self.donante, categoria=self.cat, productos=[("Queso", "5", 30), ("Yogur", "3", 40)]
        )

    def test_asigna_vigencia_segun_dias_de_la_categoria_o_parametro(self):
        hoy = timezone.localdate()
        queso = Inventario.objects.get(inv_nom="Queso")
        self.assertEqual(queso.calcular_vigencia(hoy), Inventario.VIGENTE)
        self.assertEqual(queso.calcular_vigencia(hoy + timedelta(days=21)), Inventario.PROXIMO)  # faltan 9 < 10
        self.assertEqual(queso.calcular_vigencia(hoy + timedelta(days=20)), Inventario.VIGENTE)  # faltan 10
        self.assertEqual(queso.calcular_vigencia(hoy + timedelta(days=31)), Inventario.VENCIDO)
        self.cat.cat_dias_alerta = None
        self.cat.save()
        queso.categoria.refresh_from_db()
        self.assertEqual(queso.calcular_vigencia(hoy + timedelta(days=24)), Inventario.PROXIMO)  # parámetro general 7

    def test_proceso_diario_notifica_y_saca_del_catalogo(self):
        ben = crear_beneficiario(verificado=True, admin=self.admin)
        queso = Inventario.objects.get(inv_nom="Queso")
        sol_srv.agregar_al_carrito(ben, queso, "1")
        hoy = timezone.localdate()
        Inventario.objects.filter(inv_nom="Queso").update(inv_fec_venc=hoy - timedelta(days=1))
        Inventario.objects.filter(inv_nom="Yogur").update(inv_fec_venc=hoy + timedelta(days=3))
        resultado = ejecutar_control_diario(forzar=True)
        self.assertEqual((resultado["vencidos"], resultado["proximos"]), (1, 1))
        self.assertEqual(Inventario.objects.get(inv_nom="Queso").inv_est_venc, Inventario.VENCIDO)
        self.assertEqual(Inventario.objects.get(inv_nom="Yogur").inv_est_venc, Inventario.PROXIMO)
        self.assertFalse(Inventario.catalogo().filter(inv_nom="Queso").exists())
        self.assertFalse(CarritoItem.objects.filter(beneficiario=ben).exists())
        with self.assertRaises(ValidationError):
            sol_srv.agregar_al_carrito(ben, queso, "1")
        self.assertTrue(
            Notificacion.objects.filter(destinatario=self.donante, not_titulo="Producto próximo a vencer").exists()
        )
        self.assertTrue(Notificacion.objects.filter(destinatario=self.admin, not_tipo="vencimiento").exists())

    def test_donacion_vencida_cuando_vencen_todos_sus_productos(self):
        Inventario.objects.update(inv_fec_venc=timezone.localdate() - timedelta(days=2))
        ejecutar_control_diario(forzar=True)
        self.donacion.refresh_from_db()
        self.assertEqual(self.donacion.dona_estado, Donacion.VENCIDA)

    def test_se_ejecuta_una_vez_al_dia_automaticamente(self):
        self.assertIsNotNone(ejecutar_control_diario())
        self.assertIsNone(ejecutar_control_diario())  # Ya corrió hoy.

    def test_comando_de_gestion(self):
        from io import StringIO

        from django.core.management import call_command

        salida = StringIO()
        call_command("actualizar_vencimientos", stdout=salida)
        self.assertIn("Control ejecutado", salida.getvalue())
