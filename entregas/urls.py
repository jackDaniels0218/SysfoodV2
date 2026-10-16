from django.urls import path

from . import views

app_name = "entregas"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/avanzar/", views.avanzar, name="avanzar"),
    path("<int:pk>/cancelar/", views.cancelar, name="cancelar"),
    path("<int:pk>/actualizar/", views.actualizar, name="actualizar"),
    path("seguimiento/", views.seguimiento, name="seguimiento"),
]
