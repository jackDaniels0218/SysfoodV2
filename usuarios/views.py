from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, ProtectedError, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core import parametros
from core.permisos import solo_admin
from core.servicios import auditar, enviar_correo

from . import puntaje, servicios, ubicacion, verificacion
from .forms import (
    AdminUsuarioForm, DocumentoForm, LoginForm, NuevaPasswordForm, PerfilBeneficiarioForm,
    PerfilDonanteForm, PerfilUsuarioForm, RecuperarForm, RegistroForm, RevisionDocumentoForm,
)
from .models import DocumentoValidacion, PerfilBeneficiario, PerfilDonante, Usuario


def _formularios_perfil(rol, data=None, usuario=None):
    don = PerfilDonanteForm(data, prefix="don", instance=getattr(usuario, "perfil_donante", None) if usuario else None)
    ben = PerfilBeneficiarioForm(data, prefix="ben", instance=getattr(usuario, "perfil_beneficiario", None) if usuario else None)
    return don, ben


def _guardar_perfil(usuario, don, ben):
    if usuario.es_donante:
        perfil = don.save(commit=False)
        perfil.usuario = usuario
        perfil.save()
    elif usuario.es_beneficiario:
        perfil = ben.save(commit=False)
        perfil.usuario = usuario
        perfil.save()


def _perfil_valido(rol, don, ben):
    if rol == Usuario.DONANTE:
        return don.is_valid()
    if rol == Usuario.BENEFICIARIO:
        return ben.is_valid()
    return True


# ---------------------------------------------------------------- Acceso

def iniciar_sesion(request):
    if request.user.is_authenticated:
        return redirect("core:inicio")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        correo = form.cleaned_data["correo"].strip().lower()
        usuario = Usuario.objects.filter(usu_correo__iexact=correo).first()
        ahora = timezone.now()
        if usuario and usuario.usu_estado == Usuario.BLOQUEADO and usuario.usu_bloqueo_hasta and usuario.usu_bloqueo_hasta <= ahora:
            usuario.usu_estado = Usuario.ACTIVO
            usuario.usu_intentos = 0
            usuario.usu_bloqueo_hasta = None
            usuario.save(update_fields=["usu_estado", "usu_intentos", "usu_bloqueo_hasta"])
        if usuario is None or not usuario.check_password(form.cleaned_data["password"]):
            mensaje = "Correo o contraseña incorrectos."
            if usuario and usuario.usu_estado == Usuario.ACTIVO:
                usuario.usu_intentos += 1
                maximo = parametros.entero("intentos_ingreso")
                campos = ["usu_intentos"]
                if usuario.usu_intentos >= maximo:
                    minutos = parametros.entero("minutos_bloqueo")
                    usuario.usu_estado = Usuario.BLOQUEADO
                    usuario.usu_bloqueo_hasta = ahora + timedelta(minutes=minutos)
                    campos += ["usu_estado", "usu_bloqueo_hasta"]
                    mensaje = f"Superó {maximo} intentos fallidos. La cuenta quedó bloqueada por {minutos} minutos."
                    auditar(request, "cambio_estado", "usuario", usuario.pk, "Bloqueo temporal por intentos fallidos", usuario=usuario)
                usuario.save(update_fields=campos)
            auditar(request, "ingreso_fallido", "usuario", usuario.pk if usuario else "", f"Intento de ingreso con {correo}", usuario=usuario)
            form.add_error(None, mensaje)
        elif usuario.usu_estado == Usuario.INACTIVO:
            form.add_error(None, "Su cuenta está inactiva. Comuníquese con el administrador.")
        elif usuario.usu_estado == Usuario.BLOQUEADO:
            if usuario.usu_bloqueo_hasta:
                hora = timezone.localtime(usuario.usu_bloqueo_hasta).strftime("%I:%M %p")
                form.add_error(None, f"Su cuenta está bloqueada temporalmente hasta las {hora}.")
            else:
                form.add_error(None, "Su cuenta está bloqueada. Comuníquese con el administrador.")
        else:
            usuario.usu_intentos = 0
            usuario.save(update_fields=["usu_intentos"])
            login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
            auditar(request, "ingreso", "usuario", usuario.pk, "Inicio de sesión")
            destino = request.GET.get("next") or ""
            if destino.startswith("/") and not destino.startswith("//"):
                return redirect(destino)
            return redirect("core:inicio")
    return render(request, "usuarios/login.html", {"form": form})


@require_POST
def cerrar_sesion(request):
    if request.user.is_authenticated:
        auditar(request, "salida", "usuario", request.user.pk, "Cierre de sesión")
    logout(request)
    messages.info(request, "Cerró sesión correctamente.")
    return redirect("usuarios:login")


def registro(request):
    if request.user.is_authenticated:
        return redirect("core:inicio")
    form = RegistroForm(request.POST or None)
    don, ben = _formularios_perfil(None, request.POST or None)
    if request.method == "POST":
        rol = request.POST.get("usu_rol")
        if form.is_valid() & _perfil_valido(rol, don, ben):
            with transaction.atomic():
                usuario = form.save(commit=False)
                usuario.usu_rol = form.cleaned_data["usu_rol"]
                usuario.usu_acepta_datos = True
                usuario.usu_fec_acepta = timezone.now()
                usuario.save()
                _guardar_perfil(usuario, don, ben)
                auditar(request, "crear", "usuario", usuario.pk, f"Registro de {usuario.get_usu_rol_display()}", usuario=usuario)
            login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
            auditar(request, "ingreso", "usuario", usuario.pk, "Inicio de sesión tras el registro")
            if usuario.es_beneficiario:
                messages.success(request, "Cuenta creada. Cargue sus documentos para que el administrador verifique su cuenta.")
                return redirect("usuarios:documentos")
            messages.success(request, "Cuenta creada. ¡Gracias por unirse a SysFood!")
            return redirect("core:inicio")
        messages.error(request, "Revise los campos marcados.")
    return render(request, "usuarios/registro.html", {"form": form, "don": don, "ben": ben})


def recuperar(request):
    form = RecuperarForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = Usuario.objects.filter(usu_correo__iexact=form.cleaned_data["correo"].strip()).first()
        if usuario and usuario.usu_estado != Usuario.INACTIVO:
            minutos = parametros.entero("vigencia_token_minutos")
            token = usuario.generar_token_recuperacion(minutos)
            enlace = settings.SITE_URL + reverse("usuarios:restablecer", args=[token])
            enviar_correo(
                [usuario.usu_correo], "Recuperación de contraseña",
                f"Hola {usuario.usu_nom},\n\nPara definir una nueva contraseña ingrese a:\n{enlace}\n\n"
                f"El enlace se puede usar una sola vez y vence en {minutos} minutos. "
                "Si usted no lo solicitó, ignore este mensaje.",
            )
            auditar(request, "recuperacion", "usuario", usuario.pk, "Solicitud de recuperación de contraseña", usuario=usuario)
        messages.info(request, "Si el correo está registrado, recibirá un enlace para restablecer la contraseña.")
        return redirect("usuarios:login")
    return render(request, "usuarios/recuperar.html", {"form": form})


def restablecer(request, token):
    usuario = Usuario.buscar_por_token(token)
    if usuario is None or not usuario.token_valido(token):
        messages.error(request, "El enlace no es válido, ya fue usado o venció. Solicite uno nuevo.")
        return redirect("usuarios:recuperar")
    form = NuevaPasswordForm(usuario, request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario.set_password(form.cleaned_data["password1"])
        usuario.invalidar_token()
        usuario.usu_intentos = 0
        if usuario.usu_estado == Usuario.BLOQUEADO:
            usuario.usu_estado = Usuario.ACTIVO
            usuario.usu_bloqueo_hasta = None
        usuario.save()
        auditar(request, "recuperacion", "usuario", usuario.pk, "Contraseña restablecida con token", usuario=usuario)
        messages.success(request, "Contraseña actualizada. Ya puede iniciar sesión.")
        return redirect("usuarios:login")
    return render(request, "usuarios/restablecer.html", {"form": form})


# ---------------------------------------------------------------- Perfil propio

@login_required
def perfil(request):
    usuario = request.user
    form = PerfilUsuarioForm(request.POST or None, instance=usuario)
    don, ben = _formularios_perfil(usuario.usu_rol, request.POST or None, usuario)
    if request.method == "POST":
        if form.is_valid() & _perfil_valido(usuario.usu_rol, don, ben):
            with transaction.atomic():
                usuario = form.save()
                _guardar_perfil(usuario, don, ben)
                if usuario.es_beneficiario:
                    servicios.recalcular_verificacion(usuario)
                auditar(request, "editar", "usuario", usuario.pk, "Actualización de datos propios")
            if form.cleaned_data.get("password1"):
                login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, "Sus datos fueron actualizados.")
            return redirect("usuarios:perfil")
        messages.error(request, "Revise los campos marcados.")
    return render(request, "usuarios/perfil.html", {"form": form, "don": don, "ben": ben})


# ---------------------------------------------------------------- Documentos del titular

@login_required
def documentos(request):
    usuario = request.user
    tipos = servicios.tipos_permitidos(usuario)
    if not tipos:
        raise PermissionDenied("Su cuenta no requiere documentos de validación.")
    form = DocumentoForm(tipos, request.POST or None, request.FILES or None, initial={"docv_tipo": request.GET.get("tipo")})
    quiere_json = "application/json" in request.headers.get("Accept", "")
    if request.method == "POST":
        if form.is_valid():
            try:
                doc = servicios.cargar_documento(
                    usuario, form.cleaned_data["docv_tipo"], form.cleaned_data["archivo"], form.cleaned_data["docv_fec_venc"],
                )
            except ValidationError as error:
                form.add_error("archivo", error)
            else:
                auditar(request, "crear", "documento_validacion", doc.pk, f"Carga de {doc.get_docv_tipo_display()}")
                verificacion.verificar(doc)
                doc.refresh_from_db()
                nivel, mensaje = _mensaje_carga(doc)
                getattr(messages, nivel)(request, mensaje)
                if quiere_json:
                    return JsonResponse({"ok": True, "nivel": nivel, "mensaje": mensaje, "destino": reverse("usuarios:documentos")})
                return redirect("usuarios:documentos")
        if quiere_json:
            errores = [e for lista in form.errors.values() for e in lista]
            return JsonResponse({"ok": False, "mensaje": " ".join(errores) or "Revise el archivo."}, status=400)
    resumen = servicios.resumen_documentos(usuario)
    obligatorios = [r for r in resumen if r["obligatorio"]]
    contexto = {
        "form": form,
        "resumen": resumen,
        "perfil": getattr(usuario, "perfil_beneficiario", None),
        "max_mb": parametros.entero("tam_max_archivo_mb"),
        "formatos": ", ".join(f.upper() for f in parametros.lista("formatos_permitidos")),
        "formatos_lista": parametros.lista("formatos_permitidos"),
        "obligatorios_total": len(obligatorios),
        "obligatorios_listos": sum(1 for r in obligatorios if r["doc"] and r["doc"].docv_estado in ("cargado", "aprobado")),
        "obligatorios_aprobados": sum(1 for r in obligatorios if r["doc"] and r["doc"].docv_estado == "aprobado"),
    }
    return render(request, "usuarios/documentos.html", contexto)


def _mensaje_carga(doc):
    """Mensaje claro para el titular según lo que decidió el sistema."""
    nombre = doc.get_docv_tipo_display()
    if doc.docv_estado == DocumentoValidacion.APROBADO and doc.docv_verif_auto:
        return "success", f"{nombre} cargado y pre-aprobado automáticamente: el sistema confirmó sus datos."
    if doc.docv_estado == DocumentoValidacion.RECHAZADO and doc.docv_verif_auto:
        return "warning", f"{nombre} no fue aceptado. {doc.docv_obs.replace('Rechazado automáticamente. ', '')}"
    if doc.docv_decision_auto == DocumentoValidacion.MEDIA:
        return "success", f"{nombre} cargado. El administrador lo revisará porque algunos datos no se leyeron con claridad."
    return "success", f"{nombre} cargado correctamente. El administrador lo revisará."


@login_required
@require_POST
def eliminar_documento(request, pk):
    doc = get_object_or_404(DocumentoValidacion, pk=pk, usuario=request.user)
    try:
        servicios.eliminar_documento(doc)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        auditar(request, "eliminar", "documento_validacion", pk, f"Eliminación de {doc.get_docv_tipo_display()}")
        messages.success(request, "Documento eliminado.")
    return redirect("usuarios:documentos")


@login_required
def ver_documento(request, pk):
    """Entrega el archivo solo al titular o al administrador. Nunca es público."""
    doc = get_object_or_404(DocumentoValidacion, pk=pk)
    if not (request.user.es_admin or doc.usuario_id == request.user.pk):
        raise PermissionDenied("No puede ver este documento.")
    ruta = doc.ruta_absoluta
    if not ruta.exists():
        raise Http404("El archivo no se encuentra en el almacenamiento.")
    respuesta = FileResponse(open(ruta, "rb"), content_type=doc.docv_mime)
    respuesta["Content-Disposition"] = f'inline; filename="documento_{doc.pk}.{ruta.suffix.lstrip(".")}"'
    respuesta["Cache-Control"] = "private, no-store"
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta


# ---------------------------------------------------------------- Administración de usuarios

@solo_admin
def lista(request):
    usuarios = Usuario.objects.select_related("perfil_beneficiario", "perfil_donante").order_by("-usu_fec_reg")
    q = request.GET.get("q", "").strip()
    if q:
        usuarios = usuarios.filter(
            Q(usu_nom__icontains=q) | Q(usu_ape__icontains=q) | Q(usu_correo__icontains=q)
            | Q(perfil_donante__don_doc_nit__icontains=q) | Q(perfil_beneficiario__ben_num_doc__icontains=q)
            | Q(perfil_donante__don_raz_soc__icontains=q)
        )
    for campo, filtro in (("rol", "usu_rol"), ("estado", "usu_estado"), ("verif", "perfil_beneficiario__ben_estado_verif"),
                          ("grupo", "perfil_beneficiario__ben_grupo")):
        valor = request.GET.get(campo)
        if valor:
            usuarios = usuarios.filter(**{filtro: valor})
    if request.GET.get("orden") == "puntaje":
        usuarios = usuarios.order_by(F("perfil_beneficiario__ben_puntaje").desc(nulls_last=True), "usu_nom")
    pagina = Paginator(usuarios, 20).get_page(request.GET.get("page"))
    return render(request, "usuarios/admin_lista.html", {
        "pagina": pagina, "roles": Usuario.ROLES, "estados": Usuario.ESTADOS,
        "verifs": PerfilBeneficiario.ESTADOS_VERIF, "grupos": parametros.grupos(),
    })


@solo_admin
def crear(request):
    form = AdminUsuarioForm(request.POST or None, initial={"usu_estado": Usuario.ACTIVO})
    don, ben = _formularios_perfil(None, request.POST or None)
    if request.method == "POST":
        rol = request.POST.get("usu_rol")
        if form.is_valid() & _perfil_valido(rol, don, ben):
            with transaction.atomic():
                usuario = form.save(commit=False)
                usuario.usu_acepta_datos = True
                usuario.usu_fec_acepta = timezone.now()
                usuario.save()
                _guardar_perfil(usuario, don, ben)
                auditar(request, "crear", "usuario", usuario.pk, f"Creación de {usuario.get_usu_rol_display()} {usuario.usu_correo}")
            messages.success(request, f"Usuario {usuario.nombre_completo} creado.")
            return redirect("usuarios:revisar_usuario", usuario.pk)
        messages.error(request, "Revise los campos marcados.")
    return render(request, "usuarios/admin_form.html", {"form": form, "don": don, "ben": ben, "titulo": "Nuevo usuario"})


@solo_admin
def editar(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    estado_ant = usuario.usu_estado
    form = AdminUsuarioForm(request.POST or None, instance=usuario, password_obligatoria=False)
    don, ben = _formularios_perfil(usuario.usu_rol, request.POST or None, usuario)
    if request.method == "POST":
        if form.is_valid() & _perfil_valido(usuario.usu_rol, don, ben):
            with transaction.atomic():
                usuario = form.save(commit=False)
                if usuario.usu_estado == Usuario.ACTIVO:
                    usuario.usu_intentos = 0
                    usuario.usu_bloqueo_hasta = None
                if usuario.pk == request.user.pk and usuario.usu_estado != Usuario.ACTIVO:
                    messages.error(request, "No puede desactivar ni bloquear su propia cuenta.")
                    return redirect("usuarios:editar", pk)
                usuario.save()
                _guardar_perfil(usuario, don, ben)
                if usuario.es_beneficiario:
                    servicios.recalcular_verificacion(usuario)
                auditar(request, "editar", "usuario", usuario.pk, f"Edición de {usuario.usu_correo}")
                if estado_ant != usuario.usu_estado:
                    auditar(request, "cambio_estado", "usuario", usuario.pk, f"{estado_ant} → {usuario.usu_estado}")
            messages.success(request, "Usuario actualizado.")
            return redirect("usuarios:revisar_usuario", usuario.pk)
        messages.error(request, "Revise los campos marcados.")
    return render(request, "usuarios/admin_form.html", {"form": form, "don": don, "ben": ben, "objeto": usuario, "titulo": "Editar usuario"})


@solo_admin
@require_POST
def cambiar_estado(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    nuevo = request.POST.get("estado")
    if nuevo not in dict(Usuario.ESTADOS):
        raise Http404
    if usuario.pk == request.user.pk and nuevo != Usuario.ACTIVO:
        messages.error(request, "No puede desactivar ni bloquear su propia cuenta.")
        return redirect("usuarios:revisar_usuario", pk)
    anterior = usuario.usu_estado
    usuario.usu_estado = nuevo
    if nuevo == Usuario.ACTIVO:
        usuario.usu_intentos = 0
        usuario.usu_bloqueo_hasta = None
    usuario.save()
    auditar(request, "cambio_estado", "usuario", usuario.pk, f"{anterior} → {nuevo}")
    messages.success(request, f"El usuario quedó {usuario.get_usu_estado_display().lower()}.")
    return redirect("usuarios:revisar_usuario", pk)


@solo_admin
@require_POST
def eliminar(request, pk):
    """Elimina solo si no tiene registros asociados; si los tiene, lo desactiva (baja lógica)."""
    usuario = get_object_or_404(Usuario, pk=pk)
    if usuario.pk == request.user.pk:
        messages.error(request, "No puede eliminar su propia cuenta.")
        return redirect("usuarios:revisar_usuario", pk)
    correo = usuario.usu_correo
    try:
        with transaction.atomic():
            if servicios.usuario_tiene_registros(usuario):
                raise ProtectedError("registros", [])
            usuario.delete()
    except ProtectedError:
        usuario.usu_estado = Usuario.INACTIVO
        usuario.save(update_fields=["usu_estado"])
        auditar(request, "cambio_estado", "usuario", pk, "Desactivado: tiene registros asociados")
        messages.warning(request, "El usuario tiene registros asociados, por eso se desactivó en lugar de eliminarse.")
        return redirect("usuarios:revisar_usuario", pk)
    auditar(request, "eliminar", "usuario", pk, f"Eliminación de {correo}")
    messages.success(request, "Usuario eliminado.")
    return redirect("usuarios:lista")


@solo_admin
def revisar_usuario(request, pk):
    usuario = get_object_or_404(Usuario.objects.select_related("perfil_beneficiario", "perfil_donante"), pk=pk)
    return render(request, "usuarios/admin_detalle.html", {
        "objeto": usuario,
        "resumen": servicios.resumen_documentos(usuario),
        "documentos": usuario.documentos.select_related("revisor"),
        "estados": Usuario.ESTADOS,
        "mapa_config": ubicacion.configuracion_mapa() if usuario.es_beneficiario else None,
    })


@solo_admin
@require_POST
def recalcular_puntaje(request, pk):
    perfil = get_object_or_404(PerfilBeneficiario, pk=pk)
    with transaction.atomic():
        cambio_puntaje, cambio_grupo = puntaje.recalcular(perfil, "Recálculo solicitado por el administrador", request=request)
    if cambio_puntaje or cambio_grupo:
        messages.success(request, "Puntaje recalculado. El cambio quedó registrado en la bitácora.")
    else:
        messages.info(request, "Puntaje recalculado: no hubo cambios.")
    return redirect(reverse("usuarios:revisar_usuario", args=[pk]) + "#puntaje")


@solo_admin
@require_POST
def ubicar(request, pk):
    """El administrador corrige la ubicación (coordenadas) o pide reintentar la geocodificación."""
    perfil = get_object_or_404(PerfilBeneficiario, pk=pk)
    if request.POST.get("accion") == "reintentar":
        PerfilBeneficiario.objects.filter(pk=pk).update(ben_geo_estado=PerfilBeneficiario.GEO_PENDIENTE, ben_geo_intentos=0)
        estado = ubicacion.geocodificar_beneficiario(pk, "Reintento solicitado por el administrador")
        if estado == PerfilBeneficiario.GEO_OK:
            messages.success(request, "Dirección ubicada en el mapa.")
        else:
            messages.warning(request, "No se pudo ubicar la dirección. Corrija la dirección o indique las coordenadas.")
    else:
        lat = ubicacion.coordenada(request.POST.get("lat"), -90, 90)
        lng = ubicacion.coordenada(request.POST.get("lng"), -180, 180)
        if lat is None or lng is None:
            messages.error(request, "Coordenadas inválidas. Use latitud entre -90 y 90 y longitud entre -180 y 180.")
        else:
            ubicacion.ubicar_manualmente(perfil, lat, lng, request.user, request)
            messages.success(request, "Ubicación guardada.")
    return redirect(reverse("usuarios:revisar_usuario", args=[pk]) + "#ubicacion")


@login_required
def ayuda_puntaje(request):
    """Explicación del algoritmo con los parámetros vigentes y ejemplos calculados en vivo."""
    cfg = puntaje.Config()
    suma = cfg.suma_pesos or 1
    criterios = [
        {"clave": c, "nombre": nombre, "peso": cfg.pesos[c], "maximo": round(cfg.pesos[c] * 100 / suma, 2)}
        for c, (nombre, _) in puntaje.CRITERIOS.items()
    ]
    grupos = cfg.grupos
    rangos = []
    for i, g in enumerate(grupos):
        rangos.append({**g, "hasta": 100 if i == 0 else grupos[i - 1]["minimo"]})
    return render(request, "usuarios/ayuda_puntaje.html", {
        "cfg": cfg, "criterios": criterios, "suma": cfg.suma_pesos, "grupos": rangos,
        "ejemplos": puntaje.ejemplos(cfg), "nombres_sisben": puntaje.NOMBRES_SISBEN,
    })


@solo_admin
def documentos_pendientes(request):
    """Cola del administrador: primero los de confianza media (con discrepancias), luego los de revisión manual."""
    docs = (DocumentoValidacion.objects.filter(docv_estado=DocumentoValidacion.CARGADO)
            .select_related("usuario__perfil_beneficiario").order_by("docv_fec_carga"))
    orden = {DocumentoValidacion.MEDIA: 0, "": 1}
    docs = sorted(docs, key=lambda d: (orden.get(d.docv_decision_auto, 2), d.docv_fec_carga))
    usuarios = {}
    for d in docs:
        usuarios.setdefault(d.usuario, []).append(d)
    automaticos = (DocumentoValidacion.objects.filter(docv_verif_auto=True, docv_fec_revision__gte=timezone.now() - timedelta(days=30))
                   .select_related("usuario").order_by("-docv_fec_revision")[:30])
    return render(request, "usuarios/admin_documentos.html", {
        "usuarios": usuarios.items(), "total": len(docs), "automaticos": automaticos,
        "media": sum(1 for d in docs if d.docv_decision_auto == DocumentoValidacion.MEDIA),
    })


@solo_admin
@require_POST
def revisar_documento(request, pk):
    doc = get_object_or_404(DocumentoValidacion, pk=pk)
    form = RevisionDocumentoForm(request.POST)
    if not form.is_valid():
        for errores in form.errors.values():
            messages.error(request, errores[0])
        return redirect("usuarios:revisar_usuario", doc.usuario_id)
    aprobar = form.cleaned_data["decision"] == "aprobar"
    try:
        servicios.revisar_documento(doc, request.user, aprobar, form.cleaned_data["observacion"])
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        auditar(request, "cambio_estado", "documento_validacion", doc.pk,
                f"{doc.get_docv_tipo_display()} {'aprobado' if aprobar else 'rechazado'}. {doc.docv_obs}".strip())
        messages.success(request, f"Documento {'aprobado' if aprobar else 'rechazado'}.")
    siguiente = request.POST.get("siguiente")
    if siguiente == "pendientes":
        return redirect("usuarios:documentos_pendientes")
    return redirect("usuarios:revisar_usuario", doc.usuario_id)
