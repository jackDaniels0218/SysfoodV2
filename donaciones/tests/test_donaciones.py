"""Actividad 5: donaciones (ingreso automático al inventario y anonimato)."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from catalogo.models import Bodega
from core.models import Bitacora, Parametro
from core.tests.utilidades import (
    PruebaBase,
    crear_admin,
    crear_beneficiario,
    crear_bodega,
    crear_categoria,
    crear_donacion,
    crear_donante,
)
from donaciones.models import ANONIMO, DetalleDonacion, Donacion
from inventario.models import Inventario, Kardex
from solicitudes import servicios as sol_srv


def datos_donacion(categoria, productos, anonima=False, extra=None):
    datos = {
        "productos-TOTAL_FORMS": str(len(productos)),
        "productos-INITIAL_FORMS": "0",
        "productos-MIN_NUM_FORMS": "0",
        "productos-MAX_NUM_FORMS": "1000",
        "dona_obs": "Prueba",
    }
    if anonima:
        datos["dona_anonima"] = "on"
    for i, (nombre, cantidad, venc) in enumerate(productos):
        datos.update(
            {
                f"productos-{i}-categoria": categoria.pk,
                f"productos-{i}-dd_nom": nombre,
                f"productos-{i}-dd_cantidad": cantidad,
                f"productos-{i}-dd_unidad": "kilogramos",
                f"productos-{i}-dd_fec_venc": venc,
            }
        )
    datos.update(extra or {})
    return datos


class RegistroDonacionTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin()
        self.bodega = crear_bodega(self.admin)
        self.cat = crear_categoria("Granos")
        self.donante = self.ingresar(crear_donante())
        self.futuro = (timezone.localdate() + timedelta(days=90)).isoformat()

    def test_registro_con_varios_productos_ingresa_al_inventario(self):
        r = self.client.post(
            reverse("donaciones:nueva"),
            datos_donacion(self.cat, [("Arroz", "10", self.futuro), ("Fríjol", "2.5", self.futuro)]),
        )
        donacion = Donacion.objects.get()
        self.assertRedirects(r, reverse("donaciones:detalle", args=[donacion.pk]))
        self.assertEqual(donacion.dona_estado, Donacion.DISPONIBLE)
        self.assertEqual(donacion.detalles.count(), 2)
        for det in donacion.detalles.all():
            self.assertEqual(det.dd_estado, DetalleDonacion.EN_INVENTARIO)
            inv = det.inventario
            self.assertEqual(inv.inv_cant_disp, det.dd_cantidad)
            self.assertEqual(inv.bodega, self.bodega)
            self.assertTrue(Kardex.objects.filter(inventario=inv, kar_tipo=Kardex.INGRESO).exists())
        self.assertTrue(Bitacora.objects.filter(bit_entidad="donacion", bit_accion="crear").exists())

    def test_bodega_predeterminada_por_parametro(self):
        otra = crear_bodega(self.admin)
        Parametro.objects.filter(par_clave="bodega_predeterminada").update(par_valor=str(otra.pk))
        self.client.post(reverse("donaciones:nueva"), datos_donacion(self.cat, [("Arroz", "10", self.futuro)]))
        self.assertEqual(Inventario.objects.get().bodega, otra)

    def test_validaciones_de_cantidad_y_vencimiento(self):
        hoy = timezone.localdate().isoformat()
        r = self.client.post(reverse("donaciones:nueva"), datos_donacion(self.cat, [("Arroz", "0", self.futuro)]))
        self.assertContains(r, "mayor que cero")
        r = self.client.post(reverse("donaciones:nueva"), datos_donacion(self.cat, [("Arroz", "5", hoy)]))
        self.assertContains(r, "posterior a hoy")
        r = self.client.post(reverse("donaciones:nueva"), datos_donacion(self.cat, []))
        self.assertContains(r, "al menos un producto")
        self.assertFalse(Donacion.objects.exists())

    def test_sin_bodegas_activas_no_se_registra(self):
        Bodega.objects.update(bod_estado="inactiva")
        r = self.client.post(reverse("donaciones:nueva"), datos_donacion(self.cat, [("Arroz", "1", self.futuro)]))
        self.assertContains(r, "No hay bodegas activas")
        self.assertFalse(Donacion.objects.exists())

    def test_anonimato_por_defecto_segun_preferencia(self):
        anonimo = self.ingresar(crear_donante(anonimo=True))
        r = self.client.get(reverse("donaciones:nueva"))
        self.assertTrue(r.context["form"].initial.get("dona_anonima") or r.context["form"].instance.dona_anonima)
        self.assertRegex(r.content.decode(), r'<input[^>]*name="dona_anonima"[^>]*checked')
        self.assertTrue(anonimo.perfil_donante.don_anonimo_def)


class AnonimatoTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin()
        self.donante = crear_donante(usu_nom="Secreto")
        self.donacion = crear_donacion(self.donante, anonima=True, productos=[("Atún", "10", 100)])

    def test_beneficiario_ve_donante_anonimo(self):
        self.ingresar(crear_beneficiario(verificado=True, admin=self.admin))
        r = self.client.get(reverse("solicitudes:catalogo"))
        self.assertContains(r, ANONIMO)
        self.assertNotContains(r, "Secreto")

    def test_solo_admin_consulta_identidad_y_queda_en_bitacora(self):
        self.ingresar(self.admin)
        url = reverse("donaciones:detalle", args=[self.donacion.pk])
        r = self.client.get(url)
        self.assertContains(r, ANONIMO)
        self.assertNotContains(r, "Secreto")
        r = self.client.post(url, {"accion": "revelar"})
        self.assertContains(r, "Secreto")
        self.assertTrue(
            Bitacora.objects.filter(
                bit_accion="consulta_anonimo", bit_registro=str(self.donacion.pk), usuario=self.admin
            ).exists()
        )

    def test_otros_donantes_no_ven_la_donacion(self):
        self.ingresar(crear_donante())
        self.assertEqual(self.client.get(reverse("donaciones:detalle", args=[self.donacion.pk])).status_code, 403)

    def test_reportes_no_revelan_identidad(self):
        self.ingresar(self.admin)
        r = self.client.get(reverse("reportes:reportes"), {"tipo": "donaciones"})
        filas = r.context["d"]["filas"]
        self.assertEqual(filas[0][2], ANONIMO)
        self.assertNotIn("Secreto", str(filas))
        pdf = self.client.get(reverse("reportes:exportar", args=["xlsx"]), {"tipo": "donaciones"})
        self.assertNotIn(b"Secreto", pdf.content)


class EdicionCancelacionTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin()
        self.donante = crear_donante()
        self.donacion = crear_donacion(self.donante, productos=[("Arroz", "10", 100), ("Sal", "5", 300)])
        self.ingresar(self.donante)

    def _datos_edicion(self, cambios=None, borrar=None):
        detalles = list(self.donacion.detalles.order_by("dd_id"))
        datos = {
            "productos-TOTAL_FORMS": str(len(detalles)),
            "productos-INITIAL_FORMS": str(len(detalles)),
            "productos-MIN_NUM_FORMS": "0",
            "productos-MAX_NUM_FORMS": "1000",
            "dona_obs": "Editada",
            "dona_anonima": "on",
        }
        for i, d in enumerate(detalles):
            datos.update(
                {
                    f"productos-{i}-dd_id": d.pk,
                    f"productos-{i}-donacion": self.donacion.pk,
                    f"productos-{i}-categoria": d.categoria_id,
                    f"productos-{i}-dd_nom": d.dd_nom,
                    f"productos-{i}-dd_cantidad": str(d.dd_cantidad),
                    f"productos-{i}-dd_unidad": d.dd_unidad,
                    f"productos-{i}-dd_fec_venc": d.dd_fec_venc.isoformat(),
                }
            )
        for clave, valor in (cambios or {}).items():
            datos[clave] = valor
        if borrar is not None:
            datos[f"productos-{borrar}-DELETE"] = "on"
        return datos

    def test_editar_actualiza_inventario_y_kardex(self):
        r = self.client.post(
            reverse("donaciones:editar", args=[self.donacion.pk]),
            self._datos_edicion({"productos-0-dd_cantidad": "12"}, borrar=1),
        )
        self.assertRedirects(r, reverse("donaciones:detalle", args=[self.donacion.pk]))
        self.donacion.refresh_from_db()
        self.assertTrue(self.donacion.dona_anonima)
        self.assertEqual(self.donacion.dona_obs, "Editada")
        arroz = Inventario.objects.get(inv_nom="Arroz")
        self.assertEqual(arroz.inv_cant_disp, 12)
        self.assertTrue(arroz.kardex.filter(kar_tipo=Kardex.AJUSTE, kar_cantidad=2).exists())
        sal = Inventario.objects.get(inv_nom="Sal")
        self.assertEqual(sal.inv_estado, Inventario.RETIRADO)
        self.assertEqual(sal.inv_mot_baja, "retiro_donante")

    def test_no_se_edita_ni_cancela_si_esta_reservada(self):
        ben = crear_beneficiario(verificado=True, admin=self.admin)
        sol_srv.agregar_al_carrito(ben, Inventario.objects.get(inv_nom="Arroz"), "2")
        sol = sol_srv.enviar_solicitud(ben)
        sol_srv.aprobar(sol, self.admin, "recogida")
        self.donacion.refresh_from_db()
        self.assertEqual(self.donacion.dona_estado, Donacion.RESERVADA)
        r = self.client.get(reverse("donaciones:editar", args=[self.donacion.pk]), follow=True)
        self.assertContains(r, "Solo se pueden editar donaciones disponibles")
        r = self.client.post(reverse("donaciones:cancelar", args=[self.donacion.pk]), {"motivo": "x"}, follow=True)
        self.assertContains(r, "No se puede cancelar una donación reservada")

    def test_cancelar_retira_productos(self):
        self.client.post(reverse("donaciones:cancelar", args=[self.donacion.pk]), {"motivo": "Cambio de planes"})
        self.donacion.refresh_from_db()
        self.assertEqual(self.donacion.dona_estado, Donacion.CANCELADA)
        self.assertFalse(Inventario.catalogo().exists())
        self.assertEqual(Kardex.objects.filter(kar_tipo=Kardex.BAJA).count(), 2)

    def test_admin_gestiona_todas_las_donaciones(self):
        self.ingresar(self.admin)
        r = self.client.get(reverse("donaciones:lista_admin"), {"donante": self.donante.pk})
        self.assertContains(r, f"#{self.donacion.pk}")
        self.assertEqual(self.client.get(reverse("donaciones:editar", args=[self.donacion.pk])).status_code, 200)
