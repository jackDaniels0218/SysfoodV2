from django.urls import path

from . import views

app_name = "usuarios"

urlpatterns = [
    path("ingresar/", views.iniciar_sesion, name="login"),
    path("salir/", views.cerrar_sesion, name="logout"),
    path("registro/", views.registro, name="registro"),
    path("recuperar/", views.recuperar, name="recuperar"),
    path("restablecer/<str:token>/", views.restablecer, name="restablecer"),
    path("perfil/", views.perfil, name="perfil"),
    path("documentos/", views.documentos, name="documentos"),
    path("documentos/<int:pk>/eliminar/", views.eliminar_documento, name="eliminar_documento"),
    path("documentos/<int:pk>/ver/", views.ver_documento, name="ver_documento"),
    path("admin/", views.lista, name="lista"),
    path("admin/nuevo/", views.crear, name="crear"),
    path("admin/<int:pk>/", views.revisar_usuario, name="revisar_usuario"),
    path("admin/<int:pk>/editar/", views.editar, name="editar"),
    path("admin/<int:pk>/estado/", views.cambiar_estado, name="cambiar_estado"),
    path("admin/<int:pk>/eliminar/", views.eliminar, name="eliminar"),
    path("admin/<int:pk>/puntaje/", views.recalcular_puntaje, name="recalcular_puntaje"),
    path("admin/<int:pk>/ubicacion/", views.ubicar, name="ubicar"),
    path("ayuda/puntaje/", views.ayuda_puntaje, name="ayuda_puntaje"),
    path("admin/documentos/", views.documentos_pendientes, name="documentos_pendientes"),
    path("admin/documentos/<int:pk>/revisar/", views.revisar_documento, name="revisar_documento"),
]
