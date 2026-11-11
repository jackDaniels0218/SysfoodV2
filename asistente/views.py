import json
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from core import parametros
from core.permisos import solo_admin
from core.servicios import auditar, notificar_administradores

from . import conocimiento as kb
from . import motor, whatsapp
from .models import ConsultaChat


def _sesion(request):
    if not request.session.session_key:
        request.session.save()
    return motor.huella_sesion(request.session.session_key)


def _json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return None


def _no_store(respuesta):
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta


@require_GET
@ensure_csrf_cookie
def inicio(request):
    """Saludo inicial y sugerencias según la página y el rol."""
    if not parametros.booleano("chat_activo"):
        raise Http404
    contexto = motor.Contexto.desde(request.user, request.GET.get("pagina", ""))
    nombre = f", {request.user.usu_nom}" if contexto.usuario else ""
    return _no_store(
        JsonResponse(
            {
                "texto": parametros.texto("chat_bienvenida").replace("{nombre}", nombre),
                "sugerencias": kb.sugerencias(contexto.rol, contexto.nombre_url),
                "anonimo": contexto.usuario is None,
            }
        )
    )


@require_POST
def preguntar(request):
    if not parametros.booleano("chat_activo"):
        raise Http404
    datos = _json(request)
    if datos is None:
        return HttpResponseBadRequest("JSON inválido")
    pregunta = str(datos.get("pregunta", ""))[:500]
    contexto = motor.Contexto.desde(request.user, str(datos.get("pagina", "")))
    sesion = _sesion(request)
    if motor.limite_superado(sesion):
        respuesta = motor.Respuesta(
            "Ha hecho muchas preguntas en poco tiempo. Espere un momento o escriba al administrador.",
            ConsultaChat.LIMITE,
            ofrecer_contacto=True,
        )
        consulta = motor.registrar(pregunta, respuesta, contexto, sesion)
        return _no_store(JsonResponse({**respuesta.como_dict(), "id": consulta.pk}, status=429))
    respuesta = motor.responder(pregunta, contexto)
    consulta = motor.registrar(pregunta, respuesta, contexto, sesion)
    return _no_store(JsonResponse({**respuesta.como_dict(), "id": consulta.pk}))


def _consulta_propia(request, pk):
    """Solo quien hizo la pregunta (misma sesión) puede calificarla o escalarla."""
    consulta = get_object_or_404(ConsultaChat, pk=pk)
    if consulta.con_sesion != _sesion(request):
        return None
    return consulta


@require_POST
def calificar(request, pk):
    consulta = _consulta_propia(request, pk)
    if consulta is None:
        return HttpResponseForbidden()
    datos = _json(request) or {}
    consulta.con_util = bool(datos.get("util"))
    consulta.save(update_fields=["con_util"])
    return JsonResponse({"ok": True})


@require_POST
def contactar(request, pk):
    """Envía la consulta al administrador (notificación interna y correo)."""
    consulta = _consulta_propia(request, pk)
    if consulta is None:
        return HttpResponseForbidden()
    datos = _json(request) or {}
    mensaje = str(datos.get("mensaje", "")).strip()[:1000]
    contacto = str(datos.get("contacto", "")).strip()[:150]
    if request.user.is_authenticated:
        contacto = f"{request.user.nombre_completo} <{request.user.usu_correo}>"
    elif not contacto:
        return JsonResponse(
            {"error": "Deje un correo o teléfono para que el administrador pueda responderle."}, status=400
        )
    if consulta.con_escalada:
        return JsonResponse({"texto": "Esta consulta ya se envió al administrador."})
    consulta.con_escalada = True
    consulta.con_mensaje = mensaje
    consulta.con_contacto = contacto
    consulta.save(update_fields=["con_escalada", "con_mensaje", "con_contacto"])
    notificar_administradores(
        "ayuda",
        "Consulta enviada desde el asistente",
        f"Pregunta: {consulta.con_pregunta}\nMensaje: {mensaje or '(sin mensaje)'}\nResponder a: {contacto}",
        url=f"/asistente/consultas/?escaladas=1#c{consulta.pk}",
    )
    auditar(
        request,
        "escalamiento_chat",
        "consulta_chat",
        consulta.pk,
        f"Consulta enviada al administrador: {consulta.con_pregunta[:150]}",
    )
    return JsonResponse({"texto": "Listo, le envié su consulta al administrador. Le responderá lo antes posible."})


# ---------------------------------------------------------------- Panel del administrador


@solo_admin
def panel(request):
    consultas = ConsultaChat.objects.select_related("usuario")
    filtro = request.GET.get("filtro", "")
    if request.GET.get("escaladas"):
        filtro = "escaladas"
    if filtro == "sin_respuesta":
        consultas = consultas.filter(con_fuente=ConsultaChat.SIN_RESPUESTA)
    elif filtro == "escaladas":
        consultas = consultas.filter(con_escalada=True)
    elif filtro == "pendientes":
        consultas = consultas.filter(con_escalada=True, con_atendida=False)
    elif filtro == "no_util":
        consultas = consultas.filter(con_util=False)
    hace_30 = timezone.now() - timedelta(days=30)
    recientes = ConsultaChat.objects.filter(con_fecha__gte=hace_30)
    resumen = recientes.aggregate(
        total=Count("con_id"),
        sin_respuesta=Count("con_id", filter=Q(con_fuente=ConsultaChat.SIN_RESPUESTA)),
        escaladas=Count("con_id", filter=Q(con_escalada=True)),
        pendientes=Count("con_id", filter=Q(con_escalada=True, con_atendida=False)),
        utiles=Count("con_id", filter=Q(con_util=True)),
        no_utiles=Count("con_id", filter=Q(con_util=False)),
    )
    por_fuente = recientes.values("con_fuente").annotate(n=Count("con_id")).order_by("-n")
    nombres = dict(ConsultaChat.FUENTES)
    pagina = Paginator(consultas, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "asistente/panel.html",
        {
            "pagina": pagina,
            "filtro": filtro,
            "resumen": resumen,
            "por_fuente": [(nombres.get(f["con_fuente"], f["con_fuente"]), f["n"]) for f in por_fuente],
            "modo": "Claude" if motor.claude_disponible() else "Reglas y búsqueda",
            "whatsapp": whatsapp.proveedor(),
        },
    )


@solo_admin
@require_POST
def atender(request, pk):
    consulta = get_object_or_404(ConsultaChat, pk=pk)
    consulta.con_atendida = True
    consulta.save(update_fields=["con_atendida"])
    auditar(request, "editar", "consulta_chat", consulta.pk, "Consulta del asistente marcada como atendida")
    messages.success(request, "Consulta marcada como atendida.")
    return redirect(request.POST.get("siguiente") or "asistente:panel")


# ---------------------------------------------------------------- WhatsApp (opcional)


@csrf_exempt
def whatsapp_webhook(request):
    canal = whatsapp.proveedor()
    if canal not in (whatsapp.META, whatsapp.TWILIO) or not parametros.booleano("chat_activo"):
        raise Http404
    if canal == whatsapp.META:
        if request.method == "GET":
            desafio = whatsapp.verificar_suscripcion(request.GET)
            return HttpResponse(desafio) if desafio is not None else HttpResponseForbidden()
        if request.method != "POST" or not whatsapp.firma_meta_valida(
            request.body, request.headers.get("X-Hub-Signature-256", "")
        ):
            return HttpResponseForbidden()
        for telefono, texto in whatsapp.mensajes_meta(request.body):
            respuesta = _responder_whatsapp(telefono, texto)
            if respuesta is not None:
                whatsapp.enviar_meta(telefono, whatsapp.texto_plano(respuesta))
        return HttpResponse("ok")
    # Twilio
    if request.method != "POST":
        return HttpResponseForbidden()
    url = request.build_absolute_uri()
    if not whatsapp.firma_twilio_valida(url, request.POST.dict(), request.headers.get("X-Twilio-Signature", "")):
        return HttpResponseForbidden()
    respuesta = _responder_whatsapp(request.POST.get("From", ""), request.POST.get("Body", ""))
    texto = (
        whatsapp.texto_plano(respuesta) if respuesta else "Ha hecho muchas preguntas en poco tiempo. Intente más tarde."
    )
    return HttpResponse(whatsapp.respuesta_twiml(texto), content_type="application/xml")


def _responder_whatsapp(telefono, texto):
    contexto = motor.Contexto.desde(None, canal=ConsultaChat.WHATSAPP)
    sesion = motor.huella_sesion(f"wa:{telefono}")
    if motor.limite_superado(sesion):
        return None
    respuesta = motor.responder(texto, contexto)
    motor.registrar(texto, respuesta, contexto, sesion)
    return respuesta
