from django.urls import path

from . import views

app_name = "reportes"

urlpatterns = [
    path("panel/", views.dashboard, name="dashboard"),
    path("", views.reportes, name="reportes"),
    path("exportar/<str:formato>/", views.exportar_reporte, name="exportar"),
    path("estadisticas/", views.catalogo, name="catalogo"),
    path("programar/", views.programar, name="programar"),
    path("programados/", views.programados_lista, name="programados"),
    path("programados/<int:pk>/<str:accion>/", views.programado_accion, name="programado_accion"),
    path("mapa/", views.mapa, name="mapa"),
    path("mapa/datos/", views.mapa_datos, name="mapa_datos"),
    path("mapa/exportar/<str:formato>/", views.mapa_exportar, name="mapa_exportar"),
]
