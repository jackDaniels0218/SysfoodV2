"""Mejora 2: geocodificación automática, mapa de beneficiarios y mapa de calor."""

import json
import math
import random
from decimal import Decimal
from unittest import mock

from django.urls import reverse

from core import tareas
from core.geocodificacion import ErrorGeocodificacion, Resultado, geocodificar, normalizar
from core.models import Bitacora, GeoCache, Notificacion, Parametro
from core.tests.utilidades import PruebaBase, crear_admin, crear_beneficiario, crear_donacion, crear_donante
from inventario.models import Inventario
from solicitudes import servicios as sol_srv
from usuarios import ubicacion
from usuarios.models import PerfilBeneficiario as Perfil


def perfil(u):
    return Perfil.objects.get(pk=u.pk)


class GeocodificacionTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin()

    def test_registro_ubica_automaticamente_y_audita(self):
        b = crear_beneficiario()
        p = perfil(b)
        self.assertEqual(p.ben_geo_estado, Perfil.GEO_OK)
        self.assertIsNotNone(p.ben_lat)
        self.assertEqual(p.ben_zona, "Centro")
        self.assertTrue(
            Bitacora.objects.filter(
                bit_accion="geocodificacion", bit_registro=str(b.pk), bit_detalle__contains="Ubicado automáticamente"
            ).exists()
        )

    def test_cache_evita_consultar_dos_veces(self):
        falso = mock.Mock(return_value=Resultado(True, Decimal("4.8"), Decimal("-74.3"), "Centro", "prueba"))
        with mock.patch.dict("core.geocodificacion.PROVEEDORES", {"nominatim": falso}):
            geocodificar("Calle 5 # 3-20")
            r = geocodificar("calle 5  #  3-20 ")
        self.assertEqual(falso.call_count, 1)
        self.assertTrue(r.fuente.startswith("caché"))
        self.assertEqual(GeoCache.objects.count(), 1)
        self.assertEqual(normalizar("Cl. 3 #4-10, Facatativá"), "cl. 3 no 4-10, facatativa")

    def test_cambio_de_direccion_reubica(self):
        b = crear_beneficiario()
        p = b.perfil_beneficiario
        antes = (perfil(b).ben_lat, perfil(b).ben_lng)
        p.ben_dir = "Carrera 9 # 20-11"
        p.save()
        despues = perfil(b)
        self.assertEqual(despues.ben_geo_estado, Perfil.GEO_OK)
        self.assertNotEqual(antes, (despues.ben_lat, despues.ben_lng))
        self.assertTrue(
            Bitacora.objects.filter(bit_accion="geocodificacion", bit_detalle__contains="Cambio de dirección").exists()
        )

    def test_fallo_temporal_reintenta_y_luego_marca_para_revision(self):
        Parametro.objects.filter(par_clave="geo_max_intentos").update(par_valor="2")
        b = crear_beneficiario()
        p = b.perfil_beneficiario
        p.ben_dir = "Calle sin servicio 123"
        p.save()
        self.assertEqual(perfil(b).ben_geo_estado, Perfil.GEO_REINTENTAR)
        self.assertEqual(perfil(b).ben_geo_intentos, 1)
        resumen = tareas.ejecutar("geocodificacion", forzar=True)
        self.assertEqual(resumen["para_revision"], 1)
        p = perfil(b)
        self.assertEqual(p.ben_geo_estado, Perfil.GEO_REVISION)
        self.assertTrue(
            Notificacion.objects.filter(destinatario=self.admin, not_titulo="Dirección por revisar").exists()
        )
        # La tarea ya no insiste con los casos en revisión.
        self.assertEqual(
            tareas.ejecutar("geocodificacion", forzar=True), {"ubicados": 0, "fallidos": 0, "para_revision": 0}
        )

    def test_direccion_no_encontrada(self):
        b = crear_beneficiario()
        p = b.perfil_beneficiario
        p.ben_dir = "Lugar inexistente"
        p.save()
        self.assertIn("no se encontró", perfil(b).ben_geo_detalle)

    def test_admin_ubica_manualmente_y_reintenta(self):
        b = crear_beneficiario()
        self.ingresar(self.admin)
        url = reverse("usuarios:ubicar", args=[b.pk])
        r = self.client.post(url, {"lat": "200", "lng": "-74"}, follow=True)
        self.assertContains(r, "Coordenadas inválidas")
        self.client.post(url, {"lat": "4.800001", "lng": "-74.300002"})
        p = perfil(b)
        self.assertEqual((p.ben_geo_estado, p.ben_lat), (Perfil.GEO_MANUAL, Decimal("4.800001")))
        # La tarea no sobrescribe una ubicación manual.
        self.assertIsNone(ubicacion.geocodificar_beneficiario(b.pk, "prueba"))
        r = self.client.post(url, {"accion": "reintentar"}, follow=True)
        self.assertContains(r, "Dirección ubicada")


class MapaTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin()
        self.b1 = crear_beneficiario(verificado=True, admin=self.admin)
        self.b2 = crear_beneficiario()
        crear_donacion(crear_donante(), productos=[("Arroz", "50", 200)])
        sol_srv.agregar_al_carrito(self.b1, Inventario.objects.first(), "1")
        sol_srv.enviar_solicitud(self.b1)

    def test_solo_el_administrador_ve_el_mapa(self):
        for usuario in (crear_donante(), self.b1):
            self.ingresar(usuario)
            for nombre in ("reportes:mapa", "reportes:mapa_datos"):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 403)
            self.assertEqual(self.client.get(reverse("reportes:mapa_exportar", args=["csv"])).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("reportes:mapa_datos")).status_code, 302)

    def test_datos_con_peso_y_filtros_y_auditoria(self):
        self.ingresar(self.admin)
        r = self.client.get(reverse("reportes:mapa_datos"))
        datos = r.json()
        self.assertEqual(datos["total"], 2)
        p1 = next(p for p in datos["puntos"] if p["id"] == self.b1.pk)
        p2 = next(p for p in datos["puntos"] if p["id"] == self.b2.pk)
        self.assertEqual((p1["solicitudes"], p2["solicitudes"]), (1, 0))
        self.assertGreater(p1["peso"], p2["peso"])  # Mismo perfil; b1 tiene una solicitud.
        self.assertTrue(0 < p1["peso"] <= 1)
        self.assertEqual(r["Cache-Control"], "private, no-store")
        self.assertTrue(
            Bitacora.objects.filter(bit_accion="consulta_mapa", bit_detalle__contains="2 punto(s)").exists()
        )
        r = self.client.get(reverse("reportes:mapa_datos"), {"verif": "verificado"})
        self.assertEqual([p["id"] for p in r.json()["puntos"]], [self.b1.pk])
        r = self.client.get(reverse("reportes:mapa_datos"), {"desde": "2000-01-01", "hasta": "2000-12-31"})
        self.assertEqual(r.json()["total"], 0)  # Nadie tiene solicitudes en ese rango.
        r = self.client.get(reverse("reportes:mapa_datos"), {"grupo": "<script>", "desde": "basura"})
        self.assertEqual(r.json()["total"], 2)  # Filtros inválidos se ignoran.

    def test_peso_del_calor_parametrizable(self):
        Parametro.objects.filter(par_clave__in=["calor_peso_puntaje", "calor_peso_personas"]).update(par_valor="0")
        puntos, _ = ubicacion.puntos({})
        pesos = {p["id"]: p["peso"] for p in puntos}
        self.assertEqual(pesos[self.b2.pk], 0)
        self.assertEqual(pesos[self.b1.pk], round(1 / 5, 3))  # 1 de 5 solicitudes.

    def test_exportacion_desplazada_sin_nombres(self):
        self.ingresar(self.admin)
        r = self.client.get(reverse("reportes:mapa_exportar", args=["geojson"]))
        geo = json.loads(r.content)
        self.assertEqual(len(geo["features"]), 2)
        texto = r.content.decode()
        self.assertNotIn(self.b1.usu_nom, texto)
        self.assertIn("desplazadas", geo["properties"]["aviso"])
        real = perfil(self.b1)
        exportados = [f["geometry"]["coordinates"] for f in geo["features"]]
        self.assertNotIn([float(real.ben_lng), float(real.ben_lat)], exportados)
        r = self.client.get(reverse("reportes:mapa_exportar", args=["csv"]))
        self.assertIn("latitud,longitud,grupo", r.content.decode("utf-8-sig"))
        self.assertEqual(Bitacora.objects.filter(bit_accion="exportacion_mapa").count(), 2)

    def test_desplazamiento_dentro_del_radio(self):
        azar = random.Random(7)
        for _ in range(200):
            lat, lng = ubicacion.desplazar(4.81, -74.35, 300, azar)
            dy = (lat - 4.81) * 111_320
            dx = (lng + 74.35) * 111_320 * math.cos(math.radians(4.81))
            self.assertLessEqual(math.hypot(dx, dy), 302)
        self.assertEqual(ubicacion.desplazar(4.81, -74.35, 0), (4.81, -74.35))

    def test_paginas_del_mapa(self):
        self.ingresar(self.admin)
        r = self.client.get(reverse("reportes:mapa"))
        self.assertContains(r, "leaflet-heat.js")
        self.assertContains(r, "Direcciones por revisar")
        r = self.client.get(reverse("reportes:dashboard"))
        self.assertContains(r, "mapa-panel")
        r = self.client.get(reverse("usuarios:revisar_usuario", args=[self.b1.pk]))
        self.assertContains(r, "Ubicación en el mapa")


class ErroresProveedorTests(PruebaBase):
    def test_error_de_red_no_rompe_el_registro(self):
        def caido(consulta):
            raise ErrorGeocodificacion("sin red")

        with mock.patch.dict("core.geocodificacion.PROVEEDORES", {"nominatim": caido}):
            b = crear_beneficiario()
        self.assertEqual(perfil(b).ben_geo_estado, Perfil.GEO_REINTENTAR)

    def test_proveedor_desactivado(self):
        Parametro.objects.filter(par_clave="geo_proveedor").update(par_valor="desactivado")
        b = crear_beneficiario()
        self.assertIn("desactivada", perfil(b).ben_geo_detalle)
