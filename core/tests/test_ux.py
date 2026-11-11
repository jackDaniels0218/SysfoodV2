from django.urls import reverse

from core import busqueda, guia
from core.tests.utilidades import (
    PruebaBase, crear_admin, crear_beneficiario, crear_bodega, crear_categoria, crear_donacion, crear_donante,
)
from entregas.models import Entrega
from inventario.models import Inventario
from solicitudes import servicios as sol_srv
from solicitudes.models import CarritoItem


def titulos(grupos):
    return {g: [r["titulo"] for r in resultados] for g, resultados in grupos}


class BusquedaTests(PruebaBase):
    def setUp(self):
        self.admin = crear_admin(usu_nom="Ana", usu_ape="Gómez")
        self.donante = crear_donante(usu_nom="Pedro", usu_ape="Donador")
        self.donacion = crear_donacion(self.donante, [("Arroz integral", "10", 100)])
        self.anonima = crear_donacion(self.donante, [("Lentejas", "5", 100)], anonima=True)
        self.ben = crear_beneficiario(verificado=True, admin=self.admin, usu_nom="Rosa")

    def test_administrador_encuentra_paginas_usuarios_e_inventario(self):
        r = titulos(busqueda.buscar(self.admin, "inventario"))
        self.assertIn("Inventario", r["Páginas"])
        r = titulos(busqueda.buscar(self.admin, "Rosa"))
        self.assertIn(self.ben.nombre_completo, r["Usuarios"])
        r = titulos(busqueda.buscar(self.admin, "arroz"))
        self.assertIn("Arroz integral", r["Inventario"])
        r = titulos(busqueda.buscar(self.admin, f"#{self.donacion.pk}"))
        self.assertIn(f"Donación #{self.donacion.pk}", r["Donaciones"])

    def test_busqueda_no_revela_donantes_anonimos(self):
        r = titulos(busqueda.buscar(self.admin, "Donador"))
        self.assertIn(f"Donación #{self.donacion.pk}", r["Donaciones"])
        self.assertNotIn(f"Donación #{self.anonima.pk}", r["Donaciones"])

    def test_beneficiario_solo_ve_lo_suyo_y_el_catalogo(self):
        r = titulos(busqueda.buscar(self.ben, "Pedro"))
        self.assertNotIn("Usuarios", r)
        self.assertNotIn("Donaciones", r)
        r = titulos(busqueda.buscar(self.ben, "arroz"))
        self.assertIn("Arroz integral", r["Catálogo"])
        otro = crear_beneficiario(verificado=True, admin=self.admin)
        sol_srv.agregar_al_carrito(otro, Inventario.objects.get(inv_nom="Arroz integral"), "1")
        ajena = sol_srv.enviar_solicitud(otro)
        self.assertNotIn("Mis solicitudes", titulos(busqueda.buscar(self.ben, f"#{ajena.pk}")))

    def test_donante_solo_sus_donaciones(self):
        otro = crear_donante()
        r = titulos(busqueda.buscar(otro, "arroz"))
        self.assertNotIn("Mis donaciones", r)
        r = titulos(busqueda.buscar(self.donante, "arroz"))
        self.assertIn(f"Donación #{self.donacion.pk}", r["Mis donaciones"])

    def test_vista_json_y_html(self):
        self.ingresar(self.admin)
        r = self.client.get(reverse("core:buscar"), {"q": "arroz", "formato": "json"})
        self.assertEqual(r["Cache-Control"], "private, no-store")
        self.assertIn("Inventario", [g["nombre"] for g in r.json()["grupos"]])
        r = self.client.get(reverse("core:buscar"), {"q": "xyzzy"})
        self.assertContains(r, "Sin resultados")
        self.client.logout()
        self.assertEqual(self.client.get(reverse("core:buscar"), {"q": "arroz"}).status_code, 302)


class BaseAccesibleTests(PruebaBase):
    def test_enlace_para_saltar_y_atajos(self):
        r = self.client.get(reverse("core:inicio"))
        self.assertContains(r, 'class="sf-saltar" href="#contenido"')
        self.assertContains(r, 'id="contenido"')
        self.assertContains(r, 'id="sf-atajos"')
        self.assertContains(r, 'id="sf-confirmar"')
        self.assertNotContains(r, 'id="sf-paleta"')  # La búsqueda es solo con sesión.
        self.ingresar(crear_admin())
        r = self.client.get(reverse("reportes:dashboard"))
        self.assertContains(r, 'id="sf-paleta"')
        self.assertContains(r, 'id="sf-atajos-rutas"')
        self.assertContains(r, 'aria-keyshortcuts="Control+K /"')


class GuiaTests(PruebaBase):
    def test_pasos_del_beneficiario(self):
        b = crear_beneficiario()
        g = guia.resumen(b)
        self.assertEqual(g["total"], 5)
        self.assertEqual(g["siguiente"], 1)  # Datos completos; falta cargar documentos.
        self.ingresar(b)
        self.assertContains(self.client.get(reverse("reportes:dashboard")), "Primeros pasos")
        verificado = crear_beneficiario(verificado=True)
        self.assertEqual(guia.resumen(verificado)["siguiente"], 3)  # Ahora toca pedir alimentos.

    def test_pasos_del_donante_y_guia_completa(self):
        d = crear_donante()
        self.assertEqual(guia.resumen(d)["siguiente"], 1)
        crear_donacion(d)
        self.assertEqual(guia.resumen(d)["hechos"], 2)
        juridico = crear_donante(juridica=True)
        self.assertIn("Cargue los documentos de la empresa", [p.titulo for p in guia.pasos(juridico)])

    def test_pasos_del_administrador(self):
        admin = crear_admin()
        self.assertFalse(guia.pasos(admin)[0].hecho)
        crear_bodega(admin)
        crear_categoria()
        g = guia.resumen(admin)
        self.assertTrue(g["pasos"][0].hecho and g["pasos"][1].hecho)


class DeshacerCarritoTests(PruebaBase):
    def setUp(self):
        admin = crear_admin()
        crear_donacion(crear_donante(), [("Arroz", "10", 100), ("Fríjol", "8", 100)])
        self.ben = self.ingresar(crear_beneficiario(verificado=True, admin=admin))
        for inv in Inventario.objects.all():
            sol_srv.agregar_al_carrito(self.ben, inv, "2")

    def test_quitar_y_deshacer(self):
        item = CarritoItem.objects.filter(beneficiario=self.ben).first()
        r = self.client.post(reverse("solicitudes:quitar", args=[item.pk]), follow=True)
        self.assertContains(r, "Deshacer")
        self.assertEqual(CarritoItem.objects.filter(beneficiario=self.ben).count(), 1)
        self.client.post(reverse("solicitudes:deshacer"))
        self.assertEqual(CarritoItem.objects.filter(beneficiario=self.ben).count(), 2)
        r = self.client.post(reverse("solicitudes:deshacer"), follow=True)
        self.assertContains(r, "No hay nada que deshacer")

    def test_vaciar_y_deshacer_respeta_la_disponibilidad(self):
        self.client.post(reverse("solicitudes:vaciar"))
        self.assertFalse(CarritoItem.objects.filter(beneficiario=self.ben).exists())
        Inventario.objects.filter(inv_nom="Arroz").update(inv_cant_disp=1)
        r = self.client.post(reverse("solicitudes:deshacer"), follow=True)
        self.assertEqual(CarritoItem.objects.filter(beneficiario=self.ben).count(), 1)
        self.assertContains(r, "supera la disponible")


class EstadosVaciosTests(PruebaBase):
    def test_vacios_utiles_distinguen_filtros(self):
        self.ingresar(crear_admin())
        r = self.client.get(reverse("entregas:lista"))
        self.assertContains(r, "Aún no hay entregas")
        self.assertContains(r, "Ver solicitudes pendientes")
        r = self.client.get(reverse("entregas:lista"), {"q": "zzz"})
        self.assertContains(r, "Ninguna entrega coincide con los filtros")
        self.assertEqual(Entrega.objects.count(), 0)
        r = self.client.get(reverse("catalogo:categorias"))
        self.assertContains(r, "Crear la primera categoría")

    def test_donante_sin_donaciones(self):
        self.ingresar(crear_donante())
        r = self.client.get(reverse("donaciones:mis_donaciones"))
        self.assertContains(r, "Registrar mi primera donación")

    def test_asistente_de_donacion_en_pasos(self):
        self.ingresar(crear_donante())
        crear_categoria()
        r = self.client.get(reverse("donaciones:nueva"))
        self.assertContains(r, "data-wizard")
        self.assertContains(r, "Revisar y guardar")
