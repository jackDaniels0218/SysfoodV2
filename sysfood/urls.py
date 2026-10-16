from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    path("cuentas/", include("usuarios.urls")),
    path("catalogo/", include("catalogo.urls")),
    path("donaciones/", include("donaciones.urls")),
    path("inventario/", include("inventario.urls")),
    path("solicitudes/", include("solicitudes.urls")),
    path("entregas/", include("entregas.urls")),
    path("reportes/", include("reportes.urls")),
]

handler403 = "core.errores.prohibido"
handler404 = "core.errores.no_encontrado"
handler500 = "core.errores.error_servidor"
