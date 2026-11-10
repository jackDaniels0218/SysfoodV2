"""Mejora 1: puntaje automático de necesidad, explicación y clasificación por grupos."""
from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from core import parametros, tareas
from core.models import Bitacora, Parametro
from core.tests.utilidades import PruebaBase, crear_admin, crear_beneficiario, crear_donacion, crear_donante, pdf
from inventario.models import Inventario
from solicitudes import servicios as sol_srv
from solicitudes.models import Solicitud
from usuarios import puntaje
from usuarios import servicios as usu_srv
from usuarios.models import DocumentoValidacion, PerfilBeneficiario


def datos(**cambios):
    base = {"sisben": "A", "estrato": 1, "personas": 6, "discapacidad": True, "soporte_discapacidad": True,
            "solicitudes_recientes": 1, "dias_sin_ayuda": None}
    base.update(cambios)
    return base


class CalculoTests(PruebaBase):
    def test_suma_ponderada_con_parametros_por_defecto(self):
        cfg = puntaje.Config()
        total, desglose = puntaje.calcular(datos(), cfg)
        # 25·100 + 20·100 + 20·75 + 15·100 + 5·25 + 15·100 = 9125 → ÷100 = 91,25
        self.assertEqual(total, Decimal("91.25"))
        self.assertEqual([d["puntos"] for d in desglose], [25.0, 20.0, 15.0, 15.0, 1.25, 15.0])
        self.assertAlmostEqual(sum(d["puntos"] for d in desglose), float(total))
        self.assertEqual(puntaje.grupo_para(total, cfg.grupos)["nombre"], "Prioridad crítica")

    def test_criterios_individuales(self):
        cfg = puntaje.Config()
        _, d = puntaje.calcular(datos(discapacidad=True, soporte_discapacidad=False), cfg)
        self.assertEqual(d[3]["escala"], 50.0)  # Discapacidad sin certificado aprobado.
        _, d = puntaje.calcular(datos(discapacidad=False), cfg)
        self.assertEqual(d[3]["puntos"], 0.0)
        _, d = puntaje.calcular(datos(dias_sin_ayuda=30), cfg)
        self.assertEqual(d[5]["escala"], 50.0)  # 30 de 60 días.
        _, d = puntaje.calcular(datos(personas=20, solicitudes_recientes=9), cfg)
        self.assertEqual((d[2]["escala"], d[4]["escala"]), (100.0, 100.0))  # Topes.

    def test_pesos_se_normalizan(self):
        valores = parametros.todos()
        valores.update({c: "0" for c in parametros.DEFINICIONES if c.startswith("puntaje_peso_")})
        valores["puntaje_peso_estrato"] = "3"
        cfg = puntaje.Config(valores)
        total, _ = puntaje.calcular(datos(estrato=2), cfg)
        self.assertEqual(total, Decimal("80.00"))  # Solo cuenta el estrato: escala 80.

    def test_validacion_de_parametros_compuestos(self):
        with self.assertRaises(ValidationError):
            parametros.validar("grupos_necesidad", "Alta|50|#ff0000")  # Falta grupo con mínimo 0.
        with self.assertRaises(ValidationError):
            parametros.validar("grupos_necesidad", "Alta|50|rojo; Baja|0|#00ff00")
        with self.assertRaises(ValidationError):
            parametros.validar("puntaje_escala_sisben", "A:100, B:70")  # Faltan niveles.
        with self.assertRaises(ValidationError):
            parametros.validar("puntaje_escala_estrato", "1:120, 2:80, 3:50, 4:25, 5:0, 6:0")
        self.assertEqual(parametros.validar("grupos_necesidad", "baja|0|#2B8A3E; Alta|60|#d9480f"),
                         "Alta|60|#d9480f; baja|0|#2b8a3e")


class RecalculoAutomaticoTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin()

    def test_registro_calcula_y_audita(self):
        b = crear_beneficiario()
        perfil = PerfilBeneficiario.objects.get(pk=b.pk)
        self.assertIsNotNone(perfil.ben_puntaje)
        self.assertTrue(perfil.ben_grupo)
        self.assertEqual(len(perfil.ben_puntaje_detalle), 6)
        bit = Bitacora.objects.filter(bit_accion="calculo_puntaje", bit_registro=str(b.pk)).first()
        self.assertIn("Registro del beneficiario", bit.bit_detalle)
        self.assertTrue(Bitacora.objects.filter(bit_accion="clasificacion", bit_registro=str(b.pk)).exists())

    def test_cambio_de_datos_recalcula_y_reclasifica(self):
        b = crear_beneficiario()
        perfil = b.perfil_beneficiario
        antes = PerfilBeneficiario.objects.get(pk=b.pk).ben_puntaje
        perfil.ben_estrato, perfil.ben_sisben, perfil.ben_num_personas = 6, "D", 1
        perfil.save()
        perfil.refresh_from_db()
        self.assertLess(perfil.ben_puntaje, antes)
        ultimo = Bitacora.objects.filter(bit_accion="calculo_puntaje", bit_registro=str(b.pk)).first()
        self.assertIn("Cambio en los datos del beneficiario", ultimo.bit_detalle)
        self.assertIn("→", ultimo.bit_detalle)
        clasif = Bitacora.objects.filter(bit_accion="clasificacion", bit_registro=str(b.pk)).first()
        self.assertIn("Prioridad", clasif.bit_detalle)

    def test_guardado_sin_cambios_no_duplica_auditoria(self):
        b = crear_beneficiario()
        n = Bitacora.objects.filter(bit_accion="calculo_puntaje").count()
        b.perfil_beneficiario.save()
        self.assertEqual(Bitacora.objects.filter(bit_accion="calculo_puntaje").count(), n)

    def test_aprobar_certificado_de_discapacidad_sube_el_puntaje(self):
        b = crear_beneficiario(discapacidad=True)
        doc = usu_srv.cargar_documento(b, DocumentoValidacion.DISCAPACIDAD, pdf())
        antes = PerfilBeneficiario.objects.get(pk=b.pk).ben_puntaje
        usu_srv.revisar_documento(doc, self.admin, True)
        despues = PerfilBeneficiario.objects.get(pk=b.pk).ben_puntaje
        self.assertEqual(despues - antes, Decimal("7.50"))  # 15 × (100 − 50) ÷ 100
        self.assertTrue(Bitacora.objects.filter(bit_accion="calculo_puntaje", bit_detalle__contains="documentos").exists())

    def test_nueva_solicitud_recalcula(self):
        b = crear_beneficiario(verificado=True, admin=self.admin)
        crear_donacion(crear_donante())
        sol_srv.agregar_al_carrito(b, Inventario.objects.first(), "1")
        sol_srv.enviar_solicitud(b)
        perfil = PerfilBeneficiario.objects.get(pk=b.pk)
        self.assertEqual(perfil.ben_puntaje_detalle[4]["escala"], 25.0)
        self.assertTrue(Bitacora.objects.filter(bit_accion="calculo_puntaje", bit_detalle__contains="Nueva solicitud").exists())

    def test_cambio_de_parametro_recalcula_a_todos(self):
        b1, b2 = crear_beneficiario(), crear_beneficiario()
        self.client.force_login(self.admin)
        p = Parametro.objects.get(par_clave="grupos_necesidad")
        r = self.client.post(reverse("core:parametro_editar", args=[p.pk]),
                             {"par_valor": "Urgente|50|#b42318; Normal|0|#2b8a3e"}, follow=True)
        self.assertContains(r, "Se recalculó el puntaje de 2 beneficiario(s)")
        self.assertEqual(set(PerfilBeneficiario.objects.values_list("ben_grupo", flat=True)), {"urgente"})
        self.assertTrue(Bitacora.objects.filter(bit_accion="clasificacion", bit_detalle__contains="grupos_necesidad").exists())

    def test_tarea_nocturna(self):
        crear_beneficiario()
        PerfilBeneficiario.objects.update(ben_puntaje=None)
        resultado = tareas.ejecutar("recalculo_puntajes", forzar=True)
        self.assertEqual(resultado["recalculados"], 1)
        self.assertFalse(PerfilBeneficiario.objects.filter(ben_puntaje__isnull=True).exists())
        self.assertIsNone(tareas.ejecutar("recalculo_puntajes"))  # Ya corrió hoy.
        salida = StringIO()
        call_command("ejecutar_tareas", "--listar", stdout=salida)
        self.assertIn("recalculo_puntajes", salida.getvalue())


class InterfazPuntajeTests(PruebaBase):
    def setUp(self):
        self.admin = self.ingresar(crear_admin())
        self.alto = crear_beneficiario(verificado=True, admin=self.admin)  # Sisbén A, estrato 1.
        self.bajo = crear_beneficiario(verificado=True, admin=self.admin)
        p = self.bajo.perfil_beneficiario
        p.ben_sisben, p.ben_estrato, p.ben_num_personas = "D", 5, 1
        p.save()

    def test_detalle_muestra_desglose_y_recalcular(self):
        r = self.client.get(reverse("usuarios:revisar_usuario", args=[self.alto.pk]))
        self.assertContains(r, "Puntaje de necesidad")
        self.assertContains(r, "Tiempo sin recibir ayuda")
        self.assertContains(r, "progress-bar")
        r = self.client.post(reverse("usuarios:recalcular_puntaje", args=[self.alto.pk]), follow=True)
        self.assertContains(r, "Puntaje recalculado")

    def test_ayuda_con_formula_ejemplos_y_equidad(self):
        r = self.client.get(reverse("usuarios:ayuda_puntaje"))
        self.assertContains(r, "Σ (peso")
        self.assertContains(r, "Nota de equidad")
        self.assertContains(r, "91,25")  # Primer ejemplo con los parámetros por defecto.

    def test_filtro_por_grupo_en_usuarios_y_solicitudes(self):
        grupo_bajo = PerfilBeneficiario.objects.get(pk=self.bajo.pk).ben_grupo
        r = self.client.get(reverse("usuarios:lista"), {"grupo": grupo_bajo})
        self.assertContains(r, self.bajo.nombre_completo)
        self.assertNotContains(r, self.alto.nombre_completo)

    def test_pendientes_en_orden_de_prioridad(self):
        crear_donacion(crear_donante(), productos=[("Arroz", "50", 200)])
        inv = Inventario.objects.first()
        for b in (self.bajo, self.alto):  # El de menor necesidad envía primero.
            sol_srv.agregar_al_carrito(b, inv, "1")
            sol_srv.enviar_solicitud(b)
        r = self.client.get(reverse("solicitudes:lista_admin"))
        orden = [s.beneficiario_id for s in r.context["pagina"]]
        self.assertEqual(orden, [self.alto.pk, self.bajo.pk])
        Parametro.objects.filter(par_clave="solicitudes_orden_prioridad").update(par_valor="no")
        r = self.client.get(reverse("solicitudes:lista_admin"))
        self.assertEqual([s.beneficiario_id for s in r.context["pagina"]], [self.bajo.pk, self.alto.pk])
        grupo_alto = PerfilBeneficiario.objects.get(pk=self.alto.pk).ben_grupo
        r = self.client.get(reverse("solicitudes:lista_admin"), {"estado": "pendiente", "grupo": grupo_alto})
        self.assertEqual([s.beneficiario_id for s in r.context["pagina"]], [self.alto.pk])
        self.assertEqual(Solicitud.objects.count(), 2)

    def test_reporte_por_grupo_exportable(self):
        r = self.client.get(reverse("reportes:reportes"), {"tipo": "necesidad"})
        self.assertContains(r, "Beneficiarios por grupo de necesidad")
        self.assertContains(r, self.alto.nombre_completo)
        for formato in ("pdf", "xlsx"):
            r = self.client.get(reverse("reportes:exportar", args=[formato]), {"tipo": "necesidad"})
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.content)

    def test_beneficiario_no_puede_fijar_su_puntaje_ni_ubicacion(self):
        from usuarios.forms import PerfilBeneficiarioForm

        campos = set(PerfilBeneficiarioForm().fields)
        self.assertFalse(campos & PerfilBeneficiario.CAMPOS_AUTOMATICOS)

    def test_beneficiario_no_ve_detalle_de_otros(self):
        self.ingresar(self.alto)
        r = self.client.get(reverse("usuarios:revisar_usuario", args=[self.bajo.pk]))
        self.assertEqual(r.status_code, 403)
