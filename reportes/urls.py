from django.urls import path

from . import views

app_name = "reportes"

urlpatterns = [
    path("panel/", views.dashboard, name="dashboard"),
    path("", views.reportes, name="reportes"),
    path("exportar/<str:formato>/", views.exportar_reporte, name="exportar"),
]
