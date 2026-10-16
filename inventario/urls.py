from django.urls import path

from . import views

app_name = "inventario"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/ajustar/", views.ajustar, name="ajustar"),
    path("<int:pk>/baja/", views.baja, name="baja"),
    path("retirar-vencidos/", views.retirar_vencidos, name="retirar_vencidos"),
]
