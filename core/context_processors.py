def sysfood(request):
    from . import parametros

    datos = {"notificaciones_sin_leer": 0, "carrito_total": 0, "chat_activo": parametros.booleano("chat_activo")}
    usuario = getattr(request, "user", None)
    if usuario is not None and usuario.is_authenticated:
        datos["notificaciones_sin_leer"] = usuario.notificaciones.filter(not_leida=False).count()
        if usuario.es_beneficiario:
            datos["carrito_total"] = usuario.carrito.count()
    return datos
