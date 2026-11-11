"""Canal opcional de WhatsApp para el asistente (WhatsApp Cloud API de Meta o Twilio).

Está apagado mientras WHATSAPP_PROVEEDOR esté vacío. Por WhatsApp el asistente
responde como a un visitante sin cuenta: el número de teléfono no se asocia a
ningún usuario, así que nunca entrega datos personales por este canal.

Probado solo con mensajes simulados (firmas y formato de Meta y Twilio); falta
probarlo con credenciales reales. Ver README, sección «Asistente de ayuda».
"""
import base64
import hashlib
import hmac
import json
import logging
import urllib.request
from xml.sax.saxutils import escape

from django.conf import settings

log = logging.getLogger("sysfood")

META, TWILIO = "meta", "twilio"


def proveedor():
    return (getattr(settings, "WHATSAPP_PROVEEDOR", "") or "").lower()


# ---------------------------------------------------------------- Meta (WhatsApp Cloud API)

def verificar_suscripcion(parametros_get):
    """Responde al GET de verificación del webhook de Meta. Devuelve el desafío o None."""
    if (parametros_get.get("hub.mode") == "subscribe"
            and settings.WHATSAPP_VERIFY_TOKEN
            and hmac.compare_digest(parametros_get.get("hub.verify_token", ""), settings.WHATSAPP_VERIFY_TOKEN)):
        return parametros_get.get("hub.challenge", "")
    return None


def firma_meta_valida(cuerpo, firma):
    secreto = settings.WHATSAPP_APP_SECRET
    if not secreto or not firma or not firma.startswith("sha256="):
        return False
    esperada = hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(firma[7:], esperada)


def mensajes_meta(cuerpo):
    """[(telefono, texto)] de los mensajes de texto que trae una notificación de Meta."""
    try:
        datos = json.loads(cuerpo.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return []
    mensajes = []
    for entrada in datos.get("entry", []):
        for cambio in entrada.get("changes", []):
            for m in cambio.get("value", {}).get("messages", []) or []:
                if m.get("type") == "text":
                    mensajes.append((m.get("from", ""), m.get("text", {}).get("body", "")))
    return mensajes


def enviar_meta(telefono, texto):
    url = f"https://graph.facebook.com/v20.0/{settings.WHATSAPP_PHONE_ID}/messages"
    cuerpo = json.dumps({
        "messaging_product": "whatsapp", "to": telefono, "type": "text", "text": {"body": texto[:4000]},
    }).encode()
    peticion = urllib.request.Request(url, cuerpo, {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}", "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(peticion, timeout=10) as r:
            return 200 <= r.status < 300
    except Exception as exc:
        log.warning("WhatsApp (Meta): no se pudo enviar la respuesta: %s", exc)
        return False


# ---------------------------------------------------------------- Twilio

def firma_twilio_valida(url, parametros_post, firma):
    """Algoritmo de Twilio: HMAC-SHA1 (base64) de la URL + parámetros ordenados (clave+valor)."""
    token = settings.TWILIO_AUTH_TOKEN
    if not token or not firma:
        return False
    datos = url + "".join(f"{k}{parametros_post[k]}" for k in sorted(parametros_post))
    esperada = base64.b64encode(hmac.new(token.encode(), datos.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(firma, esperada)


def respuesta_twiml(texto):
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(texto[:1500])}</Message></Response>'


def texto_plano(respuesta):
    """Respuesta del asistente en texto para WhatsApp (los enlaces van como URL completa)."""
    partes = [respuesta.texto]
    for enlace in respuesta.enlaces:
        partes.append(f"{enlace['texto']}: {settings.SITE_URL}{enlace['url']}")
    if respuesta.ofrecer_contacto:
        partes.append(f"Para hablar con el administrador ingrese a {settings.SITE_URL} y use el asistente.")
    return "\n".join(partes)
