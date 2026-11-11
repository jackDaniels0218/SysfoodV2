"""Control de acceso por rol, validado en el servidor en cada vista."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def rol_requerido(*roles):
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.usu_rol not in roles:
                raise PermissionDenied("No tiene permiso para acceder a esta página.")
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador


def beneficiario_verificado(vista):
    """Solo beneficiarios con documentos verificados (catálogo, carrito, solicitudes)."""

    @wraps(vista)
    @rol_requerido("beneficiario")
    def envoltura(request, *args, **kwargs):
        perfil = request.user.perfil_beneficiario
        if perfil.ben_estado_verif != "verificado":
            messages.warning(
                request,
                "Su cuenta aún no está verificada. Cargue sus documentos y espere la revisión del administrador.",
            )
            return redirect("usuarios:documentos")
        return vista(request, *args, **kwargs)

    return envoltura


solo_admin = rol_requerido("administrador")
solo_donante = rol_requerido("donante")
solo_beneficiario = rol_requerido("beneficiario")
