"""Mejora 3: carga de archivos y verificación automática de documentos (OCR y semáforo)."""

from datetime import date
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import Bitacora, Notificacion, Parametro
from core.tests.utilidades import PruebaBase, crear_admin, crear_beneficiario, crear_donante, pdf, png
from usuarios import ocr, servicios, verificacion
from usuarios.models import DocumentoValidacion as Doc
from usuarios.models import PerfilBeneficiario


def texto_de(usuario, numero=None, fecha="01/01/2015", nombre=None):
    p = usuario.perfil_beneficiario
    numero = numero if numero is not None else p.ben_num_doc
    nombre = nombre if nombre is not None else f"{usuario.usu_ape.upper()} {usuario.usu_nom.upper()}"
    return f"REPUBLICA DE COLOMBIA CEDULA DE CIUDADANIA NUMERO {numero} {nombre} FECHA DE EXPEDICION {fecha} BOGOTA"


def motor(texto, confianza=92):
    """Simula Tesseract instalado que devuelve `texto`."""
    return mock.patch.multiple(
        ocr,
        disponible=mock.Mock(return_value=(True, "Tesseract prueba")),
        leer=mock.Mock(return_value=(texto, confianza)),
    )


class FuncionesOCRTests(PruebaBase):
    def test_buscar_numero_tolerante_a_puntos_y_errores(self):
        self.assertEqual(ocr.buscar_numero("CC No. 52.123.456 de Bogotá", "52123456")[0], 1.0)
        self.assertEqual(ocr.buscar_numero("52 123 456", "52123456")[0], 1.0)
        parecido, leido = ocr.buscar_numero("NUMERO 52123458", "52123456")
        self.assertTrue(0.8 <= parecido < 1)
        self.assertEqual(leido, "52123458")
        self.assertEqual(ocr.buscar_numero("sin numeros", "52123456")[0], 0.0)

    def test_buscar_nombres_y_fechas(self):
        self.assertEqual(ocr.buscar_nombres("RODRIGUEZ MARIA", "María Rodríguez")[0], 1.0)
        self.assertEqual(ocr.buscar_nombres("RODRIGUFZ MARlA", "María Rodríguez")[0], 1.0)  # Errores típicos del OCR.
        self.assertEqual(ocr.buscar_nombres("PEREZ CARLOS", "María Rodríguez")[0], 0.0)
        fechas = ocr.fechas_en("Expedida el 20/05/2010, vence 2030-01-02 y nació el 3 de MAYO de 1980")
        self.assertEqual(fechas, {date(2010, 5, 20), date(2030, 1, 2), date(1980, 5, 3)})

    def test_confianza_y_semaforo(self):
        filas = [{"peso": 3, "coincide": 1}, {"peso": 2, "coincide": 1}, {"peso": 1, "coincide": 0}]
        # 100 × 5/6 × (0,7 + 0,3 × 0,9) = 80,8
        self.assertEqual(ocr.confianza(filas, 90), 80.8)
        cfg = {"alto": 85, "bajo": 40}
        self.assertEqual(verificacion.decidir(90, True, cfg), Doc.ALTA)
        self.assertEqual(verificacion.decidir(60, True, cfg), Doc.MEDIA)
        self.assertEqual(verificacion.decidir(20, True, cfg), Doc.BAJA)
        self.assertEqual(verificacion.decidir(99, False, cfg), Doc.ILEGIBLE)

    def test_umbrales_coherentes(self):
        from django.core.exceptions import ValidationError

        from core import parametros

        with self.assertRaises(ValidationError):
            parametros.validar("ocr_umbral_bajo", "90")


class CalidadAlCargarTests(PruebaBase):
    def setUp(self):
        self.b = crear_beneficiario()
        self.ingresar(self.b)

    def test_foto_borrosa_se_rechaza_de_inmediato(self):
        r = self.client.post(reverse("usuarios:documentos"), {"docv_tipo": "identidad", "archivo": png(borrosa=3)})
        self.assertContains(r, "borrosa")
        self.assertFalse(Doc.objects.filter(usuario=self.b).exists())

    def test_imagen_danada(self):
        falsa = SimpleUploadedFile("foto.png", b"\x89PNG\r\n\x1a\n basura", content_type="image/png")
        r = self.client.post(reverse("usuarios:documentos"), {"docv_tipo": "identidad", "archivo": falsa})
        self.assertContains(r, "dañado")

    def test_respuesta_json_para_la_barra_de_progreso(self):
        url = reverse("usuarios:documentos")
        r = self.client.post(url, {"docv_tipo": "identidad", "archivo": png(borrosa=3)}, HTTP_ACCEPT="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("borrosa", r.json()["mensaje"])
        r = self.client.post(url, {"docv_tipo": "identidad", "archivo": pdf()}, HTTP_ACCEPT="application/json")
        self.assertTrue(r.json()["ok"])
        self.assertIn("cargado", r.json()["mensaje"])

    def test_pagina_de_carga(self):
        r = self.client.get(reverse("usuarios:documentos"))
        self.assertContains(r, "Arrastre el archivo aquí")
        self.assertContains(r, 'capture="environment"')
        self.assertContains(r, "js/carga.js")
        self.assertContains(r, "0 de 3 cargados")

    def test_sin_ocr_sigue_el_flujo_manual(self):
        doc = servicios.cargar_documento(self.b, "identidad", png())
        self.assertIsNone(verificacion.verificar(doc))  # En este equipo no hay Tesseract.
        doc.refresh_from_db()
        self.assertEqual((doc.docv_estado, doc.docv_ocr_estado), (Doc.CARGADO, Doc.OCR_NO_DISPONIBLE))
        self.assertTrue(
            Bitacora.objects.filter(bit_accion="verificacion_auto", bit_detalle__contains="revisión manual").exists()
        )
        servicios.revisar_documento(doc, crear_admin(), True)
        doc.refresh_from_db()
        self.assertEqual(doc.docv_estado, Doc.APROBADO)
        self.assertFalse(doc.docv_verif_auto)


class SemaforoTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin()
        self.b = crear_beneficiario()

    def cargar(self, tipo="identidad", archivo=None):
        return servicios.cargar_documento(self.b, tipo, archivo or png())

    def test_verde_preaprueba_y_audita(self):
        doc = self.cargar()
        with motor(texto_de(self.b)):
            self.assertEqual(verificacion.verificar(doc), Doc.ALTA)
        doc.refresh_from_db()
        self.assertEqual(doc.docv_estado, Doc.APROBADO)
        self.assertTrue(doc.docv_verif_auto)
        self.assertIsNone(doc.revisor)
        self.assertGreaterEqual(doc.docv_ocr_confianza, 85)
        self.assertIn("Pre-aprobado", doc.docv_obs)
        self.assertEqual([c["coincide"] for c in doc.docv_ocr_resultado["campos"]], [1.0, 1.0, 1.0])
        bit = Bitacora.objects.get(bit_accion="verificacion_auto", bit_registro=str(doc.pk))
        self.assertIn("Pre-aprobado automáticamente", bit.bit_detalle)
        self.assertTrue(Notificacion.objects.filter(destinatario=self.b, not_mensaje__contains="pre-aprobado").exists())

    def test_tres_verdes_verifican_la_cuenta_sin_intervencion(self):
        with motor(texto_de(self.b) + " " + certificado_sisben(self.b)):
            verificacion.verificar(self.cargar("identidad"))
            verificacion.verificar(self.cargar("sisben"))
        with motor(f"{self.b.usu_nom} {self.b.usu_ape} Barrio Centro ESTRATO 1 factura de servicios"):
            verificacion.verificar(self.cargar("residencia"))
        self.assertEqual(PerfilBeneficiario.objects.get(pk=self.b.pk).ben_estado_verif, PerfilBeneficiario.VERIFICADO)

    def test_amarillo_va_a_la_cola_con_discrepancias(self):
        doc = self.cargar()
        with motor(texto_de(self.b, fecha="02/02/2016", nombre="OTRA PERSONA"), confianza=80):
            self.assertEqual(verificacion.verificar(doc), Doc.MEDIA)
        doc.refresh_from_db()
        self.assertEqual(doc.docv_estado, Doc.CARGADO)
        self.assertEqual([c["campo"] for c in doc.discrepancias], ["nombres", "fecha"])
        self.ingresar(self.admin)
        r = self.client.get(reverse("usuarios:documentos_pendientes"))
        self.assertContains(r, "Lo que el sistema leyó")
        self.assertContains(r, "sf-discrepancia")
        self.assertContains(r, "confianza media aparecen primero")
        self.assertContains(r, "02/02/2016")

    def test_rojo_rechaza_con_motivo_y_permite_recargar(self):
        doc = self.cargar()
        with motor("factura de un supermercado sin datos de identidad", confianza=85):
            self.assertEqual(verificacion.verificar(doc), Doc.BAJA)
        doc.refresh_from_db()
        self.assertEqual(doc.docv_estado, Doc.RECHAZADO)
        self.assertIn("número de documento", doc.docv_obs)
        self.assertTrue(Notificacion.objects.filter(destinatario=self.b, not_titulo="Documento rechazado").exists())
        nuevo = self.cargar()
        self.assertEqual(
            (nuevo.docv_estado, nuevo.docv_ocr_estado, nuevo.docv_verif_auto), (Doc.CARGADO, Doc.OCR_PENDIENTE, False)
        )

    def test_ilegible(self):
        doc = self.cargar()
        with motor("", confianza=0):
            self.assertEqual(verificacion.verificar(doc), Doc.ILEGIBLE)
        doc.refresh_from_db()
        self.assertEqual(doc.docv_estado, Doc.RECHAZADO)
        self.assertIn("ilegible", doc.docv_obs)

    def test_admin_puede_revertir_una_preaprobacion(self):
        doc = self.cargar()
        with motor(texto_de(self.b)):
            verificacion.verificar(doc)
        self.ingresar(self.admin)
        self.client.post(
            reverse("usuarios:revisar_documento", args=[doc.pk]),
            {"decision": "rechazar", "observacion": "Foto de otra persona"},
        )
        doc.refresh_from_db()
        self.assertEqual((doc.docv_estado, doc.revisor, doc.docv_verif_auto), (Doc.RECHAZADO, self.admin, False))

    def test_parametros_desactivan_las_decisiones(self):
        Parametro.objects.filter(par_clave__in=["ocr_auto_aprobar", "ocr_auto_rechazar"]).update(par_valor="no")
        alto, bajo = self.cargar("identidad"), self.cargar("sisben")
        with motor(texto_de(self.b) + " A1"):
            verificacion.verificar(alto)
        with motor("nada que ver"):
            verificacion.verificar(bajo)
        self.assertEqual(set(Doc.objects.filter(usuario=self.b).values_list("docv_estado", flat=True)), {Doc.CARGADO})
        Parametro.objects.filter(par_clave="ocr_activo").update(par_valor="no")
        doc = self.cargar("residencia", png(borrosa=3))  # Sin OCR activo tampoco se revisa la nitidez.
        self.assertIsNone(verificacion.verificar(doc))

    def test_error_de_lectura_se_reintenta_con_la_tarea(self):
        doc = self.cargar()
        with mock.patch.multiple(
            ocr,
            disponible=mock.Mock(return_value=(True, "x")),
            leer=mock.Mock(side_effect=ocr.ErrorOCR("tiempo agotado")),
        ):
            self.assertIsNone(verificacion.verificar(doc))
        doc.refresh_from_db()
        self.assertEqual((doc.docv_ocr_estado, doc.docv_ocr_intentos), (Doc.OCR_ERROR, 1))
        from core import tareas

        with motor(texto_de(self.b)):
            self.assertEqual(tareas.ejecutar("verificacion_documentos", forzar=True), {"leidos": 1, "sin_motor": 0})
        doc.refresh_from_db()
        self.assertEqual(doc.docv_estado, Doc.APROBADO)

    def test_documentos_de_donante_siempre_manuales(self):
        donante = crear_donante(juridica=True)
        doc = servicios.cargar_documento(donante, "rut", pdf())
        self.assertEqual(doc.docv_ocr_estado, Doc.OCR_NO_APLICA)
        with motor("lo que sea"):
            self.assertIsNone(verificacion.verificar(doc))


def certificado_sisben(usuario, grupo="A2", registro="Registro válido", vigencia="31 de diciembre de 2099"):
    """Texto de un certificado común del Sisbén IV (datos ficticios), como lo leería el OCR."""
    p = usuario.perfil_beneficiario
    return (
        f"DATOS PERSONALES Tipo de Documento Cedula de ciudadania Numero de Documento {p.ben_num_doc} "
        f"Sisbén {usuario.usu_nom.upper()} {usuario.usu_ape.upper()} Para efectos del periodo de transicion "
        f"presentamos su clasificacion de Sisben IV. Vigencia hasta {vigencia} GRUPO SISBÉN IV {grupo} "
        f"Municipio Encuesta: EL ROSAL CUNDINAMARCA Estado del registro: {registro} No. Ficha: 25260001552200000552"
    )


class CertificadoSisbenTests(PruebaBase):
    """El certificado del Sisbén se valida con grupo y subgrupo, estado del registro y vigencia."""

    def setUp(self):
        crear_admin()
        self.b = crear_beneficiario()  # Declara A2.

    def verificar(self, texto):
        doc = servicios.cargar_documento(self.b, "sisben", png())
        with motor(texto):
            decision = verificacion.verificar(doc)
        doc.refresh_from_db()
        return decision, doc, {c["campo"]: c for c in doc.docv_ocr_resultado["campos"]}

    def test_certificado_correcto_se_preaprueba_y_toma_la_vigencia(self):
        decision, doc, campos = self.verificar(certificado_sisben(self.b))
        self.assertEqual(decision, Doc.ALTA)
        self.assertEqual(doc.docv_estado, Doc.APROBADO)
        self.assertEqual(campos["sisben"]["leido"], "A2")
        self.assertEqual(campos["registro"]["coincide"], 1.0)
        self.assertEqual(doc.docv_fec_venc, date(2099, 12, 31))

    def test_subgrupo_distinto_va_al_administrador(self):
        decision, doc, campos = self.verificar(certificado_sisben(self.b, grupo="A4"))
        self.assertEqual(campos["sisben"]["coincide"], 0.5)
        self.assertEqual(campos["sisben"]["leido"], "A4")
        self.assertNotEqual(doc.docv_estado, Doc.APROBADO)

    def test_registro_no_valido_o_vencido_no_se_aprueba(self):
        _, doc, campos = self.verificar(certificado_sisben(self.b, registro="Registro suspendido"))
        self.assertEqual(campos["registro"]["coincide"], 0.0)
        self.assertNotEqual(doc.docv_estado, Doc.APROBADO)
        Doc.objects.all().delete()
        _, doc, campos = self.verificar(certificado_sisben(self.b, vigencia="31 de diciembre de 2020"))
        self.assertEqual(campos["vigencia"]["coincide"], 0.0)
        self.assertNotEqual(doc.docv_estado, Doc.APROBADO)

    def test_tolera_errores_de_lectura_del_subgrupo(self):
        self.assertEqual(ocr.buscar_grupo_sisben("GRUPO SISBEN IV CB Vulnerable", "C", 8)[0], 1.0)
        self.assertEqual(ocr.buscar_grupo_sisben("GRUPO SISBEN IV C8", "C", None)[0], 1.0)  # Datos sin subgrupo.
        self.assertEqual(ocr.buscar_grupo_sisben("GRUPO SISBEN IV D3", "C", 8)[0], 0.0)


class SubgrupoSisbenFormTests(PruebaBase):
    def test_subgrupo_fuera_de_rango_se_rechaza(self):
        from usuarios.forms import PerfilBeneficiarioForm

        datos = {
            "ben_tipo_doc": "CC", "ben_num_doc": "123456", "ben_fec_exp_doc": "2015-01-01", "ben_dir": "Cra 1",
            "ben_num_personas": 3, "ben_estrato": 2, "ben_sisben": "B9",
        }  # fmt: skip
        form = PerfilBeneficiarioForm(datos)
        self.assertFalse(form.is_valid())
        self.assertIn("ben_sisben", form.errors)
        datos["ben_sisben"] = "C18"
        form = PerfilBeneficiarioForm(datos)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["ben_sisben"], "C")
        self.assertEqual(form._subgrupo, 18)
