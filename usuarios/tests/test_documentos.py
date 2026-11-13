"""Actividad 2 y 18: documentos de validación y su protección."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import reverse

from core.models import Notificacion, Parametro
from core.tests.utilidades import PruebaBase, crear_admin, crear_beneficiario, crear_donante, pdf, png
from usuarios import servicios
from usuarios.models import DocumentoValidacion as Doc
from usuarios.models import PerfilBeneficiario


class CargaDocumentosTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin()
        self.ben = crear_beneficiario()

    def subir(self, tipo, archivo, usuario=None):
        self.ingresar(usuario or self.ben)
        return self.client.post(reverse("usuarios:documentos"), {"docv_tipo": tipo, "archivo": archivo})

    def estado(self):
        return PerfilBeneficiario.objects.get(pk=self.ben.pk).ben_estado_verif

    def test_carga_valida_guarda_en_almacenamiento_protegido(self):
        r = self.subir(Doc.IDENTIDAD, pdf("cedula"))
        self.assertRedirects(r, reverse("usuarios:documentos"))
        doc = Doc.objects.get(usuario=self.ben)
        self.assertEqual(doc.docv_estado, Doc.CARGADO)
        self.assertEqual(doc.docv_mime, "application/pdf")
        self.assertEqual(len(doc.docv_hash), 64)
        self.assertTrue(doc.ruta_absoluta.exists())
        self.assertTrue(str(doc.ruta_absoluta).startswith(str(settings.PROTECTED_MEDIA_ROOT)))
        self.assertNotIn(str(settings.PROTECTED_MEDIA_ROOT), str(settings.STATICFILES_DIRS))

    def test_formato_no_permitido(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        r = self.subir(Doc.IDENTIDAD, SimpleUploadedFile("virus.exe", b"MZ..."))
        self.assertContains(r, "Formato no permitido")
        self.assertFalse(Doc.objects.exists())

    def test_contenido_que_no_coincide_con_la_extension(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        r = self.subir(Doc.IDENTIDAD, SimpleUploadedFile("falso.pdf", b"esto no es un pdf"))
        self.assertContains(r, "no corresponde a un PDF")

    def test_tamano_maximo_parametrizable(self):
        Parametro.objects.filter(par_clave="tam_max_archivo_mb").update(par_valor="1")
        r = self.subir(Doc.IDENTIDAD, pdf(relleno=1024 * 1024 + 10))
        self.assertContains(r, "supera el tamaño máximo de 1 MB")

    def test_formatos_parametrizables(self):
        Parametro.objects.filter(par_clave="formatos_permitidos").update(par_valor="pdf")
        r = self.subir(Doc.IDENTIDAD, png())
        self.assertContains(r, "Formato no permitido")

    def test_documento_duplicado_en_otra_cuenta(self):
        self.subir(Doc.IDENTIDAD, pdf("mismo-archivo"))
        otro = crear_beneficiario()
        r = self.subir(Doc.IDENTIDAD, pdf("mismo-archivo"), usuario=otro)
        self.assertContains(r, "ya fue cargado en otra cuenta")

    def test_flujo_de_verificacion(self):
        self.assertEqual(self.estado(), PerfilBeneficiario.PENDIENTE)
        self.subir(Doc.IDENTIDAD, pdf())
        self.subir(Doc.SISBEN, png())
        self.assertEqual(self.estado(), PerfilBeneficiario.PENDIENTE)
        self.subir(Doc.RESIDENCIA, pdf())
        self.assertEqual(self.estado(), PerfilBeneficiario.EN_REVISION)
        self.assertTrue(Notificacion.objects.filter(destinatario=self.admin, not_tipo="documento").exists())

        docs = list(Doc.objects.filter(usuario=self.ben))
        servicios.revisar_documento(docs[0], self.admin, True)
        with self.assertRaises(ValidationError):
            servicios.revisar_documento(docs[1], self.admin, False, "")  # Rechazo sin observación.
        servicios.revisar_documento(docs[1], self.admin, False, "Ilegible")
        self.assertEqual(self.estado(), PerfilBeneficiario.RECHAZADO)
        self.assertTrue(Notificacion.objects.filter(destinatario=self.ben, not_titulo="Documento rechazado").exists())

        # Puede volver a cargar el rechazado.
        self.subir(docs[1].docv_tipo, pdf())
        self.assertEqual(self.estado(), PerfilBeneficiario.EN_REVISION)
        for d in Doc.objects.filter(usuario=self.ben).exclude(docv_estado=Doc.APROBADO):
            servicios.revisar_documento(d, self.admin, True)
        self.assertEqual(self.estado(), PerfilBeneficiario.VERIFICADO)
        self.assertTrue(Notificacion.objects.filter(destinatario=self.ben, not_titulo="Cuenta verificada").exists())

    def test_discapacidad_exige_certificado(self):
        ben = crear_beneficiario(discapacidad=True)
        for tipo in (Doc.IDENTIDAD, Doc.SISBEN, Doc.RESIDENCIA):
            servicios.revisar_documento(servicios.cargar_documento(ben, tipo, pdf()), self.admin, True)
        self.assertEqual(PerfilBeneficiario.objects.get(pk=ben.pk).ben_estado_verif, PerfilBeneficiario.PENDIENTE)
        servicios.revisar_documento(servicios.cargar_documento(ben, Doc.DISCAPACIDAD, pdf()), self.admin, True)
        self.assertEqual(PerfilBeneficiario.objects.get(pk=ben.pk).ben_estado_verif, PerfilBeneficiario.VERIFICADO)

    def test_aprobado_no_se_reemplaza_ni_elimina(self):
        doc = servicios.cargar_documento(self.ben, Doc.IDENTIDAD, pdf())
        servicios.revisar_documento(doc, self.admin, True)
        r = self.subir(Doc.IDENTIDAD, pdf())
        self.assertContains(r, "ya fue aprobado")
        r = self.client.post(reverse("usuarios:eliminar_documento", args=[doc.pk]), follow=True)
        self.assertContains(r, "no puede eliminarse")
        self.assertTrue(Doc.objects.filter(pk=doc.pk).exists())

    def test_eliminar_documento_no_aprobado_borra_el_archivo(self):
        doc = servicios.cargar_documento(self.ben, Doc.IDENTIDAD, pdf())
        ruta = doc.ruta_absoluta
        self.ingresar(self.ben)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("usuarios:eliminar_documento", args=[doc.pk]))
        self.assertFalse(Doc.objects.filter(pk=doc.pk).exists())
        self.assertFalse(ruta.exists())

    def test_el_documento_se_ve_aunque_se_borre_el_disco(self):
        """En Render el disco se borra al reiniciar: el archivo se recupera de la base de datos."""
        from usuarios.models import ArchivoDocumento

        archivo = pdf()
        doc = servicios.cargar_documento(self.ben, Doc.IDENTIDAD, archivo)
        original = doc.ruta_absoluta.read_bytes()
        self.assertEqual(bytes(ArchivoDocumento.objects.get(documento=doc).arc_contenido), original)
        doc.ruta_absoluta.unlink()
        self.ingresar(self.ben)
        r = self.client.get(reverse("usuarios:ver_documento", args=[doc.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, original)
        self.assertTrue(doc.ruta_absoluta.exists())  # Se vuelve a escribir la copia en disco.

    def test_documento_sin_archivo_explica_que_hay_que_cargarlo_de_nuevo(self):
        doc = servicios.cargar_documento(self.ben, Doc.IDENTIDAD, pdf())
        doc.archivo.delete()
        doc.ruta_absoluta.unlink()
        self.ingresar(self.ben)
        r = self.client.get(reverse("usuarios:ver_documento", args=[doc.pk]))
        self.assertContains(r, "volver a cargarlo", status_code=404)

    def test_solo_titular_y_administrador_ven_el_documento(self):
        doc = servicios.cargar_documento(self.ben, Doc.IDENTIDAD, pdf())
        url = reverse("usuarios:ver_documento", args=[doc.pk])
        self.ingresar(self.ben)
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn("no-store", r["Cache-Control"])
        self.ingresar(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)
        for intruso in (crear_beneficiario(), crear_donante()):
            self.ingresar(intruso)
            self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_donante_juridico_carga_camara_de_comercio_o_rut(self):
        juridico = crear_donante(juridica=True)
        r = self.subir(Doc.CAMARA_COMERCIO, pdf(), usuario=juridico)
        self.assertRedirects(r, reverse("usuarios:documentos"))
        r = self.subir(Doc.IDENTIDAD, pdf(), usuario=juridico)
        self.assertContains(r, "Escoja una opción válida")
        self.ingresar(crear_donante())
        self.assertEqual(self.client.get(reverse("usuarios:documentos")).status_code, 403)

    def test_solo_verificados_acceden_al_catalogo(self):
        self.ingresar(self.ben)
        r = self.client.get(reverse("solicitudes:catalogo"))
        self.assertRedirects(r, reverse("usuarios:documentos"))
        verificado = crear_beneficiario(verificado=True, admin=self.admin)
        self.ingresar(verificado)
        self.assertEqual(self.client.get(reverse("solicitudes:catalogo")).status_code, 200)

    def test_documento_vencido(self):
        from datetime import timedelta

        from django.utils import timezone

        verificado = crear_beneficiario(verificado=True, admin=self.admin)
        Doc.objects.filter(usuario=verificado, docv_tipo=Doc.SISBEN).update(
            docv_fec_venc=timezone.localdate() - timedelta(days=1)
        )
        self.assertEqual(servicios.controlar_documentos_vencidos(), 1)
        self.assertEqual(Doc.objects.get(usuario=verificado, docv_tipo=Doc.SISBEN).docv_estado, Doc.VENCIDO)
        self.assertEqual(
            PerfilBeneficiario.objects.get(pk=verificado.pk).ben_estado_verif, PerfilBeneficiario.PENDIENTE
        )
