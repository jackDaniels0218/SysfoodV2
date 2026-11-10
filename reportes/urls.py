from django.urls import path

from . import views

app_name = "reportes"

urlpatterns = [
    path("panel/", views.dashboard, name="dashboard"),
    path("", views.reportes, name="reportes"),
    path("exportar/<str:formato>/", views.exportar_reporte, name="exportar"),
    path("mapa/", views.mapa, name="mapa"),
    path("mapa/datos/", views.mapa_datos, name="mapa_datos"),
    path("mapa/exportar/<str:formato>/", views.mapa_exportar, name="mapa_exportar"),
]
