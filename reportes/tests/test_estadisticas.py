from datetime import timedelta

from django.core import mail
from django.urls import reverse
from django.utils import timezone

from asistente import motor
from asistente.models import ConsultaChat
from core.models import Bitacora, Parametro
from core.tests.utilidades import PruebaBase, crear_admin, crear_beneficiario, crear_donacion, crear_donante
from reportes import consultas, exportar, programados
from reportes.models import ReporteProgramado
from usuarios.models import DocumentoValidacion, PerfilBeneficiario


class RegistroTests(PruebaBase):
    def test_todas_las_estadisticas_se_generan_vacias_y_con_filtros(self):
        hoy = timezone.localdate().isoformat()
        for clave, e in consultas.ESTADISTICAS.items():
            for filtros in ({}, {"desde": hoy, "hasta": hoy}):
                datos = consultas.generar(clave, filtros)
                self.assertEqual(datos["titulo"], e.titulo)
                self.assertEqual(len(datos["columnas"]), len(set(datos["columnas"])), clave)
                self.assertIn("grafico", datos)
                for archivo in ("pdf", "xlsx", "csv"):
                    self.assertTrue(exportar.generar_archivo(datos, archivo), (clave, archivo))

    def test_registro_unico(self):
        self.assertEqual(list(consultas.TIPOS), list(consultas.ESTADISTICAS))
        self.assertEqual(set(consultas.GENERADORES), set(consultas.ESTADISTICAS))
        for nueva in ("verificaciones", "tiempo_verificacion", "zonas", "chat", "necesidad"):
            self.assertIn(nueva, consultas.ESTADISTICAS)
        self.assertEqual(len({e.titulo for e in consultas.ESTADISTICAS.values()}), len(consultas.ESTADISTICAS))


class NuevasEstadisticasTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin()

    def test_verificaciones_automaticas_y_manuales(self):
        b = crear_beneficiario(verificado=True, admin=self.admin)
        doc = b.documentos.first()
        DocumentoValidacion.objects.filter(pk=doc.pk).update(docv_verif_auto=True, docv_decision_auto="alta")
        datos = consultas.generar("verificaciones", {})
        resumen = dict(datos["resumen"])
        self.assertEqual(resumen["Documentos revisados"], 3)
        self.assertEqual(resumen["Automáticas"], 1)
        self.assertEqual(resumen["Manuales"], 2)
        self.assertEqual(datos["grafico"]["datos"], [1, 2])
        self.assertEqual(len(consultas.generar("verificaciones", {"estado": "auto"})["filas"]), 1)

    def test_tiempo_promedio_de_verificacion(self):
        b = crear_beneficiario(verificado=True, admin=self.admin)
        for i, doc in enumerate(b.documentos.all()):
            DocumentoValidacion.objects.filter(pk=doc.pk).update(
                docv_fec_carga=doc.docv_fec_revision - timedelta(hours=2 * (i + 1)), docv_verif_auto=i == 0,
            )
        datos = consultas.generar("tiempo_verificacion", {})
        resumen = dict(datos["resumen"])
        self.assertEqual(resumen["Promedio general (horas)"], "4")  # (2 + 4 + 6) / 3
        self.assertEqual(resumen["Promedio automáticas (horas)"], "2")
        self.assertEqual(resumen["Promedio manuales (horas)"], "5")
        self.assertEqual(resumen["Mediana (horas)"], "4")

    def test_beneficiarios_por_zona(self):
        b1, b2, b3 = crear_beneficiario(), crear_beneficiario(), crear_beneficiario()
        PerfilBeneficiario.objects.filter(usuario__in=[b1, b2]).update(ben_zona="Centro")
        PerfilBeneficiario.objects.filter(usuario=b3).update(ben_zona="Cartagenita")
        datos = consultas.generar("zonas", {})
        self.assertEqual(datos["filas"][0][:2], ["Centro", 2])
        self.assertEqual(datos["filas"][1][:2], ["Cartagenita", 1])
        self.assertEqual(datos["enlace"][1], "reportes:mapa")

    def test_consultas_del_chat(self):
        contexto = motor.Contexto.desde(None)
        for pregunta in ("olvidé mi contraseña", "xyzzy plutonio", "xyzzy plutonio"):
            motor.registrar(pregunta, motor.responder(pregunta, contexto), contexto)
        datos = consultas.generar("chat", {})
        resumen = dict(datos["resumen"])
        self.assertEqual(resumen["Consultas"], 3)
        self.assertEqual(resumen["Sin respuesta"], 2)
        self.assertIn("Sin respuesta frecuente: «xyzzy plutonio»", resumen)
        self.assertEqual(len(consultas.generar("chat", {"estado": ConsultaChat.BUSQUEDA})["filas"]), 1)


class VistasTests(PruebaBase):
    def setUp(self):
        self.admin = self.ingresar(crear_admin())
        crear_donacion(crear_donante())

    def test_pagina_de_cada_estadistica(self):
        for clave in consultas.ESTADISTICAS:
            r = self.client.get(reverse("reportes:reportes"), {"tipo": clave})
            self.assertEqual(r.status_code, 200, clave)
            self.assertContains(r, 'data-png="g1"')
        self.assertEqual(self.client.get(reverse("reportes:reportes"), {"tipo": "nada"}).status_code, 404)

    def test_solo_muestra_los_filtros_que_admite(self):
        r = self.client.get(reverse("reportes:reportes"), {"tipo": "chat", "categoria": "1"})
        self.assertNotContains(r, 'name="categoria"')
        self.assertNotIn("categoria", r.context["filtros"])
        r = self.client.get(reverse("reportes:reportes"), {"tipo": "donaciones"})
        self.assertContains(r, 'name="categoria"')

    def test_exportar_csv(self):
        r = self.client.get(reverse("reportes:exportar", args=["csv"]), {"tipo": "donaciones"})
        self.assertEqual(r["Content-Type"], "text/csv; charset=utf-8")
        texto = r.content.decode("utf-8")
        self.assertTrue(texto.startswith("﻿N.º;Fecha;Donante"))
        self.assertIn(".csv", r["Content-Disposition"])
        self.assertTrue(Bitacora.objects.filter(bit_entidad="reporte", bit_detalle__startswith="Exportación CSV").exists())
        Parametro.objects.filter(par_clave="reportes_separador_csv").update(par_valor=",")
        r = self.client.get(reverse("reportes:exportar", args=["csv"]), {"tipo": "donaciones"})
        self.assertTrue(r.content.decode("utf-8").startswith("﻿N.º,Fecha,Donante"))
        self.assertEqual(self.client.get(reverse("reportes:exportar", args=["doc"]), {"tipo": "donaciones"}).status_code, 404)

    def test_rango_por_defecto_parametrizado(self):
        Parametro.objects.filter(par_clave="reportes_dias_por_defecto").update(par_valor="30")
        r = self.client.get(reverse("reportes:reportes"), {"tipo": "donaciones"})
        self.assertEqual(r.context["filtros"]["desde"], (timezone.localdate() - timedelta(days=30)).isoformat())
        r = self.client.get(reverse("reportes:reportes"), {"tipo": "donaciones", "todo": "1"})
        self.assertNotIn("desde", r.context["filtros"])

    def test_catalogo_lista_todas(self):
        r = self.client.get(reverse("reportes:catalogo"))
        for e in consultas.ESTADISTICAS.values():
            self.assertContains(r, e.titulo)
        self.assertContains(r, "Indicadores en los paneles")

    def test_solo_administrador(self):
        self.ingresar(crear_beneficiario())
        for url in (reverse("reportes:catalogo"), reverse("reportes:programados"), reverse("reportes:exportar", args=["csv"])):
            self.assertEqual(self.client.get(url).status_code, 403)


class ProgramadosTests(PruebaBase):
    def setUp(self):
        self.admin = self.ingresar(crear_admin())
        crear_donacion(crear_donante())

    def programar(self, **datos):
        base = {"tipo": "donaciones", "destinatarios": "jefe@ejemplo.co, otra@ejemplo.co", "frecuencia": "semanal",
                "formato": "pdf", "relativo": "1"}
        base.update(datos)
        return self.client.post(reverse("reportes:programar"), base)

    def test_programar_y_listar(self):
        r = self.programar(estado="disponible", desde="2020-01-01")
        self.assertRedirects(r, reverse("reportes:programados"), fetch_redirect_response=False)
        rep = ReporteProgramado.objects.get()
        self.assertEqual(rep.lista_destinatarios, ["jefe@ejemplo.co", "otra@ejemplo.co"])
        self.assertEqual(rep.rep_filtros, {"estado": "disponible"})  # Relativo: no guarda fechas fijas.
        self.assertContains(self.client.get(reverse("reportes:programados")), "Donaciones por periodo y estado")

    def test_correos_invalidos(self):
        self.programar(destinatarios="no-es-correo")
        self.assertFalse(ReporteProgramado.objects.exists())

    def test_enviar_ahora_adjunta_el_archivo_y_audita(self):
        self.programar(formato="csv")
        rep = ReporteProgramado.objects.get()
        self.client.post(reverse("reportes:programado_accion", args=[rep.pk, "enviar"]))
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, ["jefe@ejemplo.co", "otra@ejemplo.co"])
        nombre, contenido, tipo = correo.attachments[0]
        self.assertTrue(nombre.endswith(".csv"))
        self.assertEqual(tipo, "text/csv")
        rep.refresh_from_db()
        self.assertIsNotNone(rep.rep_ultimo_envio)
        self.assertTrue(Bitacora.objects.filter(bit_accion="envio_reporte").exists())

    def test_pausar_y_eliminar(self):
        self.programar()
        rep = ReporteProgramado.objects.get()
        self.client.post(reverse("reportes:programado_accion", args=[rep.pk, "pausar"]))
        rep.refresh_from_db()
        self.assertFalse(rep.rep_activo)
        self.client.post(reverse("reportes:programado_accion", args=[rep.pk, "eliminar"]))
        self.assertFalse(ReporteProgramado.objects.exists())

    def test_tarea_envia_solo_los_vencidos_y_desde_la_hora(self):
        self.programar(frecuencia="diaria")
        rep = ReporteProgramado.objects.get()
        Parametro.objects.filter(par_clave="reportes_hora_envio").update(par_valor="7")
        temprano = timezone.make_aware(timezone.datetime.combine(timezone.localdate(), timezone.datetime.min.time())) + timedelta(hours=5)
        self.assertEqual(programados.tarea_envios(temprano)["enviados"], 0)
        tarde = temprano + timedelta(hours=4)
        self.assertEqual(programados.tarea_envios(tarde), {"enviados": 1, "fallidos": 0})
        self.assertEqual(programados.tarea_envios(tarde + timedelta(hours=2)), {"enviados": 0, "fallidos": 0})
        self.assertEqual(programados.tarea_envios(tarde + timedelta(days=1)), {"enviados": 1, "fallidos": 0})
        rep.rep_activo = False
        rep.save()
        self.assertEqual(programados.tarea_envios(tarde + timedelta(days=3))["enviados"], 0)

    def test_periodo_relativo(self):
        rep = ReporteProgramado(rep_estadistica="donaciones", rep_frecuencia="semanal", rep_relativo=True, rep_filtros={"estado": "x"})
        ahora = timezone.now()
        filtros = programados.filtros_de(rep, ahora)
        self.assertEqual(filtros["hasta"], timezone.localtime(ahora).date().isoformat())
        self.assertEqual(filtros["desde"], (timezone.localtime(ahora) - timedelta(days=7)).date().isoformat())
        self.assertEqual(filtros["estado"], "x")
