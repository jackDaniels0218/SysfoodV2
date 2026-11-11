from django.urls import path

from . import views

app_name = "solicitudes"

urlpatterns = [
    path("catalogo/", views.catalogo, name="catalogo"),
    path("carrito/", views.carrito, name="carrito"),
    path("carrito/agregar/<int:inv_id>/", views.agregar, name="agregar"),
    path("carrito/quitar/<int:item_id>/", views.quitar, name="quitar"),
    path("carrito/vaciar/", views.vaciar, name="vaciar"),
    path("carrito/deshacer/", views.deshacer, name="deshacer"),
    path("carrito/enviar/", views.enviar, name="enviar"),
    path("mis-solicitudes/", views.mis_solicitudes, name="mis_solicitudes"),
    path("mis-solicitudes/<int:pk>/", views.detalle, name="detalle"),
    path("admin/", views.lista_admin, name="lista_admin"),
    path("admin/<int:pk>/", views.admin_detalle, name="admin_detalle"),
]
