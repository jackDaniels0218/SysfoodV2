from django.urls import path

from . import views

app_name = "donaciones"

urlpatterns = [
    path("mis-donaciones/", views.mis_donaciones, name="mis_donaciones"),
    path("nueva/", views.nueva, name="nueva"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/cancelar/", views.cancelar, name="cancelar"),
    path("admin/", views.lista_admin, name="lista_admin"),
]
