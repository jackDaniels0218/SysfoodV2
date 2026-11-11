"""Actividad 3 y 4: categorías y bodegas."""

from django.urls import reverse

from catalogo.models import Bodega, Categoria
from core.tests.utilidades import PruebaBase, crear_admin, crear_bodega, crear_categoria, crear_donacion, crear_donante


class CategoriasTests(PruebaBase):
    def setUp(self):
        self.admin = self.ingresar(crear_admin())

    def test_crear_editar_y_validar(self):
        r = self.client.post(
            reverse("catalogo:categoria_nueva"),
            {
                "cat_nom": "Lácteos",
                "cat_desc": "Leche",
                "cat_perecedero": "on",
                "cat_dias_alerta": "5",
                "cat_estado": "activa",
            },
        )
        self.assertRedirects(r, reverse("catalogo:categorias"))
        c = Categoria.objects.get(cat_nom="Lácteos")
        self.assertTrue(c.cat_perecedero)
        self.assertEqual(c.dias_alerta(), 5)
        r = self.client.post(reverse("catalogo:categoria_nueva"), {"cat_nom": "lácteos", "cat_estado": "activa"})
        self.assertContains(r, "Ya existe una categoría")
        self.client.post(
            reverse("catalogo:categoria_editar", args=[c.pk]), {"cat_nom": "Lácteos", "cat_estado": "activa"}
        )
        c.refresh_from_db()
        self.assertEqual(c.dias_alerta(), 7)  # Vacío: usa el parámetro general.

    def test_categoria_con_productos_se_inactiva(self):
        cat = crear_categoria()
        crear_donacion(crear_donante(), categoria=cat)
        self.client.post(reverse("catalogo:categoria_eliminar", args=[cat.pk]))
        cat.refresh_from_db()
        self.assertEqual(cat.cat_estado, "inactiva")
        libre = crear_categoria()
        self.client.post(reverse("catalogo:categoria_eliminar", args=[libre.pk]))
        self.assertFalse(Categoria.objects.filter(pk=libre.pk).exists())

    def test_categoria_inactiva_no_se_ofrece_al_donar(self):
        inactiva = crear_categoria("Descontinuada")
        inactiva.cat_estado = "inactiva"
        inactiva.save()
        crear_categoria("Granos")
        self.ingresar(crear_donante())
        r = self.client.get(reverse("donaciones:nueva"))
        self.assertContains(r, "Granos")
        self.assertNotContains(r, "Descontinuada")


class BodegasTests(PruebaBase):
    def setUp(self):
        self.admin = self.ingresar(crear_admin())

    def test_crear_bodega_con_responsable(self):
        r = self.client.post(
            reverse("catalogo:bodega_nueva"),
            {
                "bod_nom": "Central",
                "bod_dir": "Cl 1",
                "bod_capacidad": "1 t",
                "responsable": self.admin.pk,
                "bod_estado": "activa",
            },
        )
        self.assertRedirects(r, reverse("catalogo:bodegas"))
        self.assertEqual(Bodega.objects.get(bod_nom="Central").responsable, self.admin)

    def test_bodega_con_inventario_se_inactiva(self):
        bodega = crear_bodega(self.admin)
        crear_donacion(crear_donante())
        self.client.post(reverse("catalogo:bodega_eliminar", args=[bodega.pk]))
        bodega.refresh_from_db()
        self.assertEqual(bodega.bod_estado, "inactiva")
        vacia = crear_bodega(self.admin)
        self.client.post(reverse("catalogo:bodega_eliminar", args=[vacia.pk]))
        self.assertFalse(Bodega.objects.filter(pk=vacia.pk).exists())
