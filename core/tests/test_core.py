"""Actividades 9, 13, 14, 16, 17, 19 y 22: parámetros, notificaciones, auditoría, rendimiento, seguridad y respaldo."""

import time
import zipfile
from io import StringIO

from django.conf import settings
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from core.models import Bitacora, Notificacion, Parametro
from core.servicios import notificar
from core.tests.utilidades import (
    PruebaBase,
    PruebaTransaccional,
    crear_admin,
    crear_beneficiario,
    crear_bodega,
    crear_donacion,
    crear_donante,
    pdf,
)
from donaciones.models import Donacion
from inventario.models import Inventario, Kardex
from solicitudes import servicios as sol_srv
from usuarios import servicios as usu_srv
from usuarios.models import DocumentoValidacion, Usuario


class ParametrosTests(PruebaBase):
    def setUp(self):
        self.admin = self.ingresar(crear_admin())

    def test_parametros_iniciales(self):
        claves = set(Parametro.objects.values_list("par_clave", flat=True))
        for clave in (
            "max_productos_solicitud",
            "dias_alerta_vencimiento",
            "tam_max_archivo_mb",
            "formatos_permitidos",
            "intentos_ingreso",
            "vigencia_token_minutos",
            "unidades_medida",
            "bodega_predeterminada",
        ):
            self.assertIn(clave, claves)
        self.assertEqual(Parametro.objects.get(par_clave="max_productos_solicitud").par_valor, "5")
        self.assertEqual(Parametro.objects.get(par_clave="tam_max_archivo_mb").par_valor, "5")

    def test_modificar_valida_y_audita(self):
        p = Parametro.objects.get(par_clave="max_productos_solicitud")
        r = self.client.post(reverse("core:parametro_editar", args=[p.pk]), {"par_valor": "cero"})
        self.assertContains(r, "número entero")
        self.client.post(reverse("core:parametro_editar", args=[p.pk]), {"par_valor": "8"})
        p.refresh_from_db()
        self.assertEqual((p.par_valor, p.usuario_mod), ("8", self.admin))
        b = Bitacora.objects.get(bit_accion="cambio_parametro")
        self.assertIn("«5» → «8»", b.bit_detalle)
        f = Parametro.objects.get(par_clave="formatos_permitidos")
        r = self.client.post(reverse("core:parametro_editar", args=[f.pk]), {"par_valor": "pdf,exe"})
        self.assertContains(r, "Solo se admiten")

    def test_unidades_de_medida_desde_parametros(self):
        p = Parametro.objects.get(par_clave="unidades_medida")
        self.client.post(reverse("core:parametro_editar", args=[p.pk]), {"par_valor": "bultos, arrobas"})
        self.ingresar(crear_donante())
        r = self.client.get(reverse("donaciones:nueva"))
        self.assertContains(r, "Arrobas")
        self.assertNotContains(r, "Kilogramos")

    def test_no_se_eliminan(self):
        with self.assertRaises(PermissionDenied):
            Parametro.objects.first().delete()


class NotificacionesTests(PruebaBase):
    def test_interna_y_por_correo(self):
        u = crear_donante()
        notificar(u, "donacion", "Hola", "Mensaje", "/donaciones/mis-donaciones/")
        self.assertEqual(Notificacion.objects.filter(destinatario=u, not_leida=False).count(), 1)
        self.assertEqual(mail.outbox[-1].to, [u.usu_correo])
        self.ingresar(u)
        r = self.client.get(reverse("core:notificaciones"))
        self.assertContains(r, "Mensaje")
        self.assertEqual(r.context["notificaciones_sin_leer"], 1)
        n = Notificacion.objects.get(destinatario=u)
        self.client.post(reverse("core:notificacion_leer", args=[n.pk]))
        n.refresh_from_db()
        self.assertTrue(n.not_leida)

    def test_no_se_leen_notificaciones_ajenas(self):
        n = notificar(crear_donante(), "donacion", "x", "y", correo=False)
        self.ingresar(crear_donante())
        self.assertEqual(self.client.post(reverse("core:notificacion_leer", args=[n.pk])).status_code, 404)

    def test_marcar_todas(self):
        u = crear_donante()
        for i in range(3):
            notificar(u, "donacion", f"T{i}", "m", correo=False)
        self.ingresar(u)
        self.client.post(reverse("core:notificaciones_leer_todas"))
        self.assertFalse(Notificacion.objects.filter(destinatario=u, not_leida=False).exists())


class TrazabilidadTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin()
        crear_donacion(crear_donante(), productos=[("Arroz", "10", 100)])

    def test_bitacora_inmutable_y_con_ip(self):
        self.client.post(
            reverse("usuarios:login"),
            {"correo": self.admin.usu_correo, "password": "Clave$egura123"},
            REMOTE_ADDR="10.1.2.3",
        )
        b = Bitacora.objects.get(bit_accion="ingreso")
        self.assertEqual((b.usuario, b.bit_ip), (self.admin, "10.1.2.3"))
        with self.assertRaises(PermissionDenied):
            b.save()
        with self.assertRaises(PermissionDenied):
            b.delete()

    def test_consulta_con_filtros(self):
        self.ingresar(self.admin)
        r = self.client.get(reverse("core:trazabilidad"), {"vista": "kardex", "registro": "Arroz"})
        self.assertEqual(r.context["pagina"].paginator.count, 1)
        r = self.client.get(reverse("core:trazabilidad"), {"vista": "kardex", "tipo": "reserva"})
        self.assertEqual(r.context["pagina"].paginator.count, 0)
        r = self.client.get(
            reverse("core:trazabilidad"), {"vista": "bitacora", "usuario": self.admin.pk, "desde": "2000-01-01"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get(reverse("core:trazabilidad"), {"vista": "entregas"}).status_code, 200)


class ReportesTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin()
        donante = crear_donante()
        crear_donacion(donante, productos=[("Arroz", "10", 100), ("Leche", "2", 3)])
        ben = crear_beneficiario(verificado=True, admin=self.admin)
        sol_srv.agregar_al_carrito(ben, Inventario.objects.get(inv_nom="Arroz"), "2")
        sol_srv.aprobar(sol_srv.enviar_solicitud(ben), self.admin, "recogida")
        self.ingresar(self.admin)

    def test_todos_los_reportes_y_exportaciones(self):
        for tipo in ("donaciones", "inventario", "vencidos", "solicitudes", "beneficiarios"):
            r = self.client.get(reverse("reportes:reportes"), {"tipo": tipo, "desde": "2000-01-01"})
            self.assertEqual(r.status_code, 200, tipo)
            self.assertTrue(r.context["d"]["filas"] or tipo == "vencidos", tipo)
            r = self.client.get(reverse("reportes:exportar", args=["pdf"]), {"tipo": tipo})
            self.assertEqual(r["Content-Type"], "application/pdf")
            self.assertTrue(r.content.startswith(b"%PDF"))
            r = self.client.get(reverse("reportes:exportar", args=["xlsx"]), {"tipo": tipo})
            self.assertTrue(r.content.startswith(b"PK"))
            import io

            from openpyxl import load_workbook

            libro = load_workbook(io.BytesIO(r.content))
            self.assertIn("Reporte", libro.sheetnames)
            self.assertTrue(libro["Gráfico 1"]._charts)

    def test_filtros(self):
        r = self.client.get(reverse("reportes:reportes"), {"tipo": "inventario", "estado": "proximo"})
        self.assertEqual([f[1] for f in r.context["d"]["filas"]], ["Leche"])
        r = self.client.get(reverse("reportes:reportes"), {"tipo": "solicitudes", "estado": "en_revision"})
        self.assertEqual(len(r.context["d"]["filas"]), 1)
        r = self.client.get(reverse("reportes:reportes"), {"tipo": "donaciones", "hasta": "2000-01-01"})
        self.assertEqual(r.context["d"]["filas"], [])

    def test_dashboard_admin(self):
        r = self.client.get(reverse("reportes:dashboard"))
        self.assertEqual(r.context["inventario"]["proximo"], 1)
        self.assertEqual(r.context["entregas"]["En revisión"], 1)


class RendimientoTests(PruebaBase):
    """Actividad 16: consultas y registros comunes en 2 segundos o menos."""

    def test_paginas_comunes_responden_rapido(self):
        admin = crear_admin()
        donante = crear_donante()
        for i in range(20):
            crear_donacion(donante, productos=[(f"P{i}-{j}", "5", 50 + j) for j in range(5)])
        self.ingresar(admin)
        for nombre in (
            "reportes:dashboard",
            "inventario:lista",
            "donaciones:lista_admin",
            "solicitudes:lista_admin",
            "reportes:reportes",
            "core:trazabilidad",
        ):
            inicio = time.perf_counter()
            r = self.client.get(reverse(nombre))
            duracion = time.perf_counter() - inicio
            self.assertEqual(r.status_code, 200)
            self.assertLess(duracion, 2, nombre)

    def test_carga_de_documento_de_5mb(self):
        ben = crear_beneficiario()
        self.ingresar(ben)
        inicio = time.perf_counter()
        r = self.client.post(
            reverse("usuarios:documentos"), {"docv_tipo": "identidad", "archivo": pdf(relleno=5 * 1024 * 1024 - 100)}
        )
        self.assertLess(time.perf_counter() - inicio, 5)
        self.assertEqual(r.status_code, 302)


class SeguridadTests(PruebaBase):
    def test_cookies_y_cabeceras(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        r = self.client.get(reverse("usuarios:login"))
        self.assertEqual(r["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")

    def test_csrf_activo(self):
        from django.test import Client

        c = Client(enforce_csrf_checks=True)
        r = c.post(reverse("usuarios:login"), {"correo": "a@b.co", "password": "x"})
        self.assertEqual(r.status_code, 403)

    def test_https_en_produccion(self):
        import importlib
        import os

        import sysfood.settings as conf

        os.environ["DJANGO_HTTPS"] = "1"
        try:
            importlib.reload(conf)
            self.assertTrue(conf.SECURE_SSL_REDIRECT)
            self.assertTrue(conf.SESSION_COOKIE_SECURE)
            self.assertTrue(conf.CSRF_COOKIE_SECURE)
            self.assertGreater(conf.SECURE_HSTS_SECONDS, 0)
        finally:
            os.environ.pop("DJANGO_HTTPS")
            importlib.reload(conf)

    def test_interfaz_en_espanol(self):
        r = self.client.get(reverse("usuarios:registro"))
        self.assertContains(r, 'lang="es"')
        self.assertContains(r, "Crear una cuenta")


class RespaldoTests(PruebaTransaccional):
    """Actividad 22: respaldo de la base de datos y de los documentos, con restauración probada."""

    def test_respaldo_y_restauracion(self):
        admin = crear_admin()
        ben = crear_beneficiario(verificado=True, admin=admin)
        crear_donacion(crear_donante(), productos=[("Arroz", "10", 100)])
        doc = DocumentoValidacion.objects.filter(usuario=ben).first()
        contenido = doc.ruta_absoluta.read_bytes()
        salida = StringIO()
        destino = settings.BACKUP_ROOT / "prueba.zip"
        call_command("respaldo", salida=str(destino), stdout=salida)
        self.assertTrue(destino.exists())
        with zipfile.ZipFile(destino) as zf:
            self.assertIn("datos.json", zf.namelist())
            self.assertIn("protegido/" + doc.docv_ruta, zf.namelist())
        conteo = (Usuario.objects.count(), Donacion.objects.count(), Kardex.objects.count(), Bitacora.objects.count())

        # Se pierden datos y archivos...
        Donacion.objects.filter().update(dona_obs="dañado")
        doc.ruta_absoluta.unlink()
        crear_donante()

        # ...y se restauran.
        call_command("restaurar", str(destino), si=True, stdout=StringIO())
        self.assertEqual(
            (Usuario.objects.count(), Donacion.objects.count(), Kardex.objects.count(), Bitacora.objects.count()),
            conteo,
        )
        self.assertNotEqual(Donacion.objects.first().dona_obs, "dañado")
        self.assertEqual(DocumentoValidacion.objects.get(pk=doc.pk).ruta_absoluta.read_bytes(), contenido)
        self.assertTrue(Usuario.objects.get(pk=admin.pk).check_password("Clave$egura123"))


class EntradasInvalidasTests(PruebaBase):
    """Los filtros con valores inválidos no deben producir errores del servidor."""

    def test_filtros_con_basura(self):
        admin = self.ingresar(crear_admin())
        crear_donacion(crear_donante())
        basura = {
            "categoria": "abc",
            "bodega": "x",
            "donante": "uno",
            "desde": "2025-13-45",
            "hasta": "ayer",
            "page": "-1",
            "usuario": "x",
        }
        urls = [
            reverse("inventario:lista"),
            reverse("donaciones:lista_admin"),
            reverse("entregas:lista"),
            reverse("solicitudes:lista_admin"),
            reverse("core:trazabilidad"),
        ] + [
            reverse("reportes:reportes") + f"?tipo={t}"
            for t in ("donaciones", "inventario", "vencidos", "solicitudes", "beneficiarios")
        ]
        for url in urls:
            for clave, valor in basura.items():
                separador = "&" if "?" in url else "?"
                r = self.client.get(f"{url}{separador}{clave}={valor}")
                self.assertLess(r.status_code, 500, (url, clave))
        self.assertTrue(admin.es_admin)

    def test_cantidades_invalidas_en_el_carrito(self):
        admin = crear_admin()
        crear_donacion(crear_donante())
        self.ingresar(crear_beneficiario(verificado=True, admin=admin))
        inv = Inventario.objects.get()
        for valor in ("NaN", "1e999", "99999999999999", "abc", "", "-0"):
            r = self.client.post(reverse("solicitudes:agregar", args=[inv.pk]), {"cantidad": valor})
            self.assertEqual(r.status_code, 302, valor)
        from solicitudes.models import CarritoItem

        self.assertFalse(CarritoItem.objects.exists())


class IdiomaTests(PruebaBase):
    def test_siempre_en_espanol_aunque_el_navegador_este_en_ingles(self):
        r = self.client.post(reverse("usuarios:registro"), {"usu_correo": "x"}, HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9")
        self.assertContains(r, "Este campo es obligatorio")
        self.assertNotContains(r, "This field is required")
