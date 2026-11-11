from datetime import timedelta
from decimal import Decimal
from importlib import import_module
from io import StringIO

from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from core import parametros
from core.models import FiltroGuardado, Parametro
from core.tests.utilidades import (
    PruebaBase,
    crear_admin,
    crear_beneficiario,
    crear_categoria,
    crear_donacion,
    crear_donante,
)
from donaciones import servicios as don_srv
from donaciones.forms import DetalleForm
from donaciones.models import DetalleDonacion, Donacion
from entregas import servicios as ent_srv
from inventario import servicios, unidades
from inventario.models import Inventario
from solicitudes import servicios as sol_srv


def donar_latas(donante, cantidad="24", unidad="latas", nombre="Atún"):
    categoria = crear_categoria()
    if not Inventario.objects.exists():
        crear_donacion(donante)  # Crea la bodega activa.
    det = DetalleDonacion(
        categoria=categoria,
        dd_nom=nombre,
        dd_cantidad=Decimal(cantidad),
        dd_unidad=unidad,
        dd_fec_venc=timezone.localdate() + timedelta(days=200),
    )
    don_srv.registrar(Donacion(donante=donante), [det], donante)
    return Inventario.objects.get(detalle=det)


class FormatoTests(PruebaBase):
    def test_formato_por_unidad(self):
        casos = [
            ("50", "kilogramos", "50 kg"),
            ("24", "latas", "24 latas"),
            ("1", "latas", "1 lata"),
            ("2.50", "litros", "2,5 L"),
            ("1", "unidades", "1 unidad"),
            ("3", "cajas", "3 cajas"),
            ("1", "paquetes", "1 paquete"),
            ("1500", "gramos", "1.500 g"),
            ("0.25", "kilogramos", "0,25 kg"),
        ]
        for cantidad, unidad, esperado in casos:
            self.assertEqual(unidades.formatear(Decimal(cantidad), unidad), esperado)

    def test_abreviaturas_parametrizadas(self):
        Parametro.objects.filter(par_clave="unidades_abreviaturas").update(par_valor="kilogramos:kilos, latas:lt")
        self.assertEqual(unidades.formatear(Decimal("3"), "kilogramos"), "3 kilos")
        self.assertEqual(unidades.formatear(Decimal("3"), "latas"), "3 lt")

    def test_validacion_contables_y_divisibles(self):
        self.assertEqual(unidades.validar("2,5", "kilogramos"), Decimal("2.5"))
        self.assertEqual(unidades.validar("24", "latas"), Decimal("24"))
        with self.assertRaisesMessage(ValidationError, "escriba 24 o 25, no 24,5"):
            unidades.validar("24.5", "latas")
        with self.assertRaisesMessage(ValidationError, "escriba 1, no 0,5"):
            unidades.validar("0.5", "cajas")
        with self.assertRaises(ValidationError):
            unidades.validar("1.255", "kilogramos")

    def test_divisibles_se_configuran(self):
        Parametro.objects.filter(par_clave="unidades_divisibles").update(par_valor="kilogramos,latas")
        self.assertTrue(unidades.es_divisible("latas"))
        self.assertFalse(unidades.es_divisible("litros"))

    def test_parametro_divisibles_valida_contra_unidades_de_medida(self):
        with self.assertRaisesMessage(ValidationError, "toneladas"):
            parametros.validar("unidades_divisibles", "kilogramos,toneladas")
        self.assertEqual(
            parametros.validar("unidades_abreviaturas", "kilogramos:kg,litros:L"), "kilogramos:kg, litros:L"
        )
        with self.assertRaises(ValidationError):
            parametros.validar("unidades_abreviaturas", "kilogramos")


class ValidacionTests(PruebaBase):
    def setUp(self):
        self.donante = crear_donante()
        self.admin = crear_admin()

    def test_formulario_de_donacion_rechaza_decimales_en_contables(self):
        datos = {
            "categoria": crear_categoria().pk,
            "dd_nom": "Atún",
            "dd_cantidad": "24.5",
            "dd_unidad": "latas",
            "dd_fec_venc": (timezone.localdate() + timedelta(days=30)).isoformat(),
        }
        form = DetalleForm(data=datos)
        self.assertFalse(form.is_valid())
        self.assertIn("unidades completas", form.errors["dd_cantidad"][0])
        datos.update(dd_cantidad="2.5", dd_unidad="kilogramos")
        self.assertTrue(DetalleForm(data=datos).is_valid())

    def test_formulario_indica_que_unidades_son_divisibles(self):
        form = DetalleForm()
        self.assertIn("kilogramos", form.fields["dd_unidad"].widget.attrs["data-divisibles"])
        self.assertNotIn("latas", form.fields["dd_unidad"].widget.attrs["data-divisibles"])

    def test_servicio_de_donacion_rechaza_decimales(self):
        with self.assertRaises(ValidationError):
            donar_latas(self.donante, "10.5")
        self.assertFalse(DetalleDonacion.objects.filter(dd_unidad="latas").exists())

    def test_marca_divisible_al_ingresar(self):
        inv = donar_latas(self.donante)
        self.assertFalse(inv.inv_divisible)
        self.assertFalse(inv.detalle.dd_divisible)
        self.assertTrue(Inventario.objects.get(inv_unidad="kilogramos").inv_divisible)

    def test_base_de_datos_rechaza_decimales_en_contables(self):
        inv = donar_latas(self.donante)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Inventario.objects.filter(pk=inv.pk).update(inv_cant_disp=Decimal("3.5"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            DetalleDonacion.objects.filter(pk=inv.detalle_id).update(dd_cantidad=Decimal("3.5"))
        # Los divisibles sí admiten decimales.
        kilos = Inventario.objects.get(inv_unidad="kilogramos")
        Inventario.objects.filter(pk=kilos.pk).update(inv_cant_disp=Decimal("3.5"))

    def test_ajuste_respeta_la_unidad(self):
        inv = donar_latas(self.donante)
        with self.assertRaisesMessage(ValidationError, "unidades completas"):
            servicios.ajustar(inv, Decimal("20.5"), "conteo", self.admin)
        inv = servicios.ajustar(inv, Decimal("20"), "conteo", self.admin)
        self.assertEqual(inv.inv_cant_disp, 20)

    def test_carrito_y_entrega_respetan_la_unidad(self):
        inv = donar_latas(self.donante)
        ben = crear_beneficiario(verificado=True, admin=self.admin)
        with self.assertRaisesMessage(ValidationError, "unidades completas"):
            sol_srv.agregar_al_carrito(ben, inv, "1.5")
        sol_srv.agregar_al_carrito(ben, inv, "4")
        entrega = sol_srv.aprobar(sol_srv.enviar_solicitud(ben), self.admin, "recogida")
        entrega = ent_srv.avanzar(entrega, self.admin)
        entrega = ent_srv.avanzar(entrega, self.admin)
        det = entrega.detalles.get()
        with self.assertRaisesMessage(ValidationError, "unidades completas"):
            ent_srv.avanzar(entrega, self.admin, cantidades={det.pk: Decimal("2.5")})
        ent_srv.avanzar(entrega, self.admin, cantidades={det.pk: Decimal("3")})
        inv.refresh_from_db()
        self.assertEqual(inv.inv_cant_disp, 21)


class PanelTests(PruebaBase):
    def setUp(self):
        self.admin = self.ingresar(crear_admin())
        self.donante = crear_donante()

    def test_panel_muestra_cantidades_formateadas_y_kpis(self):
        donar_latas(self.donante, "60")
        r = self.client.get(reverse("inventario:lista"))
        self.assertContains(r, "60 latas")
        self.assertContains(r, "10 kg")
        self.assertEqual(r.context["kpi"]["disponibles"], 2)
        self.assertContains(r, "data-ajuste-rapido")

    def test_alerta_de_proximos_a_vencer(self):
        crear_donacion(self.donante, [("Leche", "6", 2)])
        r = self.client.get(reverse("inventario:lista"))
        self.assertContains(r, "Vencen pronto")
        self.assertEqual(r.context["kpi"]["proximos"], 1)

    def test_vista_en_tarjetas_se_recuerda(self):
        crear_donacion(self.donante)
        r = self.client.get(reverse("inventario:lista"), {"vista": "tarjetas"})
        self.assertContains(r, "sf-inv-card")
        r = self.client.get(reverse("inventario:lista"))
        self.assertEqual(r.context["vista"], "tarjetas")

    def test_estado_vacio_util(self):
        r = self.client.get(reverse("inventario:lista"))
        self.assertContains(r, "El inventario está vacío")
        r = self.client.get(reverse("inventario:lista"), {"q": "nada"})
        self.assertContains(r, "Ningún producto coincide")

    def test_ajuste_rapido_vuelve_a_la_lista(self):
        inv = donar_latas(self.donante)
        siguiente = reverse("inventario:lista") + "?vista=tabla"
        r = self.client.post(
            reverse("inventario:ajustar", args=[inv.pk]),
            {"nueva_cantidad": "12", "motivo": "conteo físico", "siguiente": siguiente},
        )
        self.assertRedirects(r, siguiente, fetch_redirect_response=False)
        inv.refresh_from_db()
        self.assertEqual(inv.inv_cant_disp, 12)
        r = self.client.post(
            reverse("inventario:ajustar", args=[inv.pk]),
            {"nueva_cantidad": "11.5", "motivo": "x", "siguiente": "https://otro.sitio/"},
        )
        self.assertRedirects(r, reverse("inventario:detalle", args=[inv.pk]), fetch_redirect_response=False)
        inv.refresh_from_db()
        self.assertEqual(inv.inv_cant_disp, 12)

    def test_no_conformes_heredados_y_comando(self):
        inv = donar_latas(self.donante)
        # Simula un dato de antes de la regla: unidad contable con decimales, conservado como divisible.
        Inventario.objects.filter(pk=inv.pk).update(inv_divisible=True)
        Inventario.objects.filter(pk=inv.pk).update(inv_cant_disp=Decimal("23.5"))
        r = self.client.get(reverse("inventario:lista"))
        self.assertEqual(r.context["kpi"]["por_revisar"], 1)
        r = self.client.get(reverse("inventario:lista"), {"revisar": "1"})
        self.assertEqual([i.pk for i in r.context["pagina"]], [inv.pk])
        salida = StringIO()
        call_command("revisar_cantidades", stdout=salida)
        self.assertIn("Atún", salida.getvalue())

    def test_migracion_marca_registros_existentes(self):
        inv = donar_latas(self.donante)
        Inventario.objects.filter(pk=inv.pk).update(inv_divisible=True)
        otro = donar_latas(self.donante, nombre="Maíz")
        Inventario.objects.filter(pk=otro.pk).update(inv_divisible=True)
        Inventario.objects.filter(pk=otro.pk).update(inv_cant_disp=Decimal("7.5"))
        import_module("inventario.migrations.0002_unidades_contables").marcar(apps, None)
        inv.refresh_from_db()
        otro.refresh_from_db()
        self.assertFalse(inv.inv_divisible)  # Contable y entero: queda contable.
        self.assertTrue(otro.inv_divisible)  # Contable con decimales: se conserva y se reporta.


class FiltrosGuardadosTests(PruebaBase):
    def setUp(self):
        self.admin = self.ingresar(crear_admin())

    def test_guardar_usar_y_eliminar(self):
        r = self.client.post(
            reverse("core:filtro_guardar"),
            {
                "vista": "inventario",
                "nombre": "Vencen pronto",
                "f_vigencia": "proximo",
                "f_page": "3",
            },
        )
        self.assertRedirects(r, reverse("inventario:lista") + "?vigencia=proximo", fetch_redirect_response=False)
        filtro = FiltroGuardado.objects.get(usuario=self.admin)
        self.assertEqual(filtro.fil_consulta, "vigencia=proximo")
        r = self.client.get(reverse("inventario:lista"))
        self.assertContains(r, "Vencen pronto")
        # Mismo nombre: se reemplaza.
        self.client.post(
            reverse("core:filtro_guardar"), {"vista": "inventario", "nombre": "Vencen pronto", "f_vigencia": "vencido"}
        )
        self.assertEqual(FiltroGuardado.objects.get().fil_consulta, "vigencia=vencido")
        self.client.post(reverse("core:filtro_eliminar", args=[filtro.pk]))
        self.assertFalse(FiltroGuardado.objects.exists())

    def test_filtros_son_de_cada_usuario(self):
        otro = crear_admin()
        filtro = FiltroGuardado.objects.create(
            usuario=otro, fil_vista="inventario", fil_nombre="Ajeno", fil_consulta="q=a"
        )
        self.assertEqual(self.client.post(reverse("core:filtro_eliminar", args=[filtro.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("inventario:lista")), "Ajeno")

    def test_sin_filtros_no_guarda(self):
        self.client.post(reverse("core:filtro_guardar"), {"vista": "inventario", "nombre": "Vacío"})
        self.assertFalse(FiltroGuardado.objects.exists())
        self.assertEqual(
            self.client.post(reverse("core:filtro_guardar"), {"vista": "otra", "nombre": "x", "f_q": "a"}).status_code,
            404,
        )
