from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("politica-de-datos/", views.politica_datos, name="politica_datos"),
    path("notificaciones/", views.notificaciones, name="notificaciones"),
    path("notificaciones/<int:pk>/leer/", views.notificacion_leer, name="notificacion_leer"),
    path("notificaciones/leer-todas/", views.notificaciones_leer_todas, name="notificaciones_leer_todas"),
    path("parametros/", views.parametros_lista, name="parametros"),
    path("parametros/<int:pk>/", views.parametro_editar, name="parametro_editar"),
    path("trazabilidad/", views.trazabilidad, name="trazabilidad"),
    path("tareas/", views.tareas_lista, name="tareas"),
    path("buscar/", views.buscar, name="buscar"),
    path("filtros/guardar/", views.filtro_guardar, name="filtro_guardar"),
    path("filtros/<int:pk>/eliminar/", views.filtro_eliminar, name="filtro_eliminar"),
]
