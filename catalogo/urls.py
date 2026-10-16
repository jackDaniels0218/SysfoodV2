from django.urls import path

from . import views

app_name = "catalogo"

urlpatterns = [
    path("categorias/", views.categorias, name="categorias"),
    path("categorias/nueva/", views.categoria_form, name="categoria_nueva"),
    path("categorias/<int:pk>/editar/", views.categoria_form, name="categoria_editar"),
    path("categorias/<int:pk>/eliminar/", views.categoria_eliminar, name="categoria_eliminar"),
    path("bodegas/", views.bodegas, name="bodegas"),
    path("bodegas/nueva/", views.bodega_form, name="bodega_nueva"),
    path("bodegas/<int:pk>/editar/", views.bodega_form, name="bodega_editar"),
    path("bodegas/<int:pk>/eliminar/", views.bodega_eliminar, name="bodega_eliminar"),
]
