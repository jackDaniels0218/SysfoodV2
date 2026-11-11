import base64
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest import mock

from django.test import override_settings
from django.urls import reverse

from asistente import conocimiento as kb
from asistente import motor, whatsapp
from asistente.models import ConsultaChat
from core.models import Bitacora, Notificacion, Parametro
from core.tests.utilidades import PruebaBase, crear_admin, crear_beneficiario, crear_donacion, crear_donante
from solicitudes.models import Solicitud


class MotorTests(PruebaBase):
    def contexto(self, usuario=None, pagina=""):
        return motor.Contexto.desde(usuario, pagina)

    def test_normaliza_y_reduce_palabras(self):
        self.assertEqual(motor.normalizar("¿Cómo DONO alimentos?"), "como dono alimentos")
        self.assertEqual(motor.raiz("donaciones"), motor.raiz("donacion"))
        self.assertEqual(motor.raiz("solicitudes"), "solicitud")

    def test_busqueda_encuentra_el_articulo_correcto(self):
        casos = {
            "olvidé la contraseña": "recuperar",
            "que documentos tengo que subir": "documentos_requeridos",
            "como hago para donar comida": "donar",
            "como pido alimentos": "catalogo",
            "la foto sale borrosa": "cargar_documento",
        }
        for pregunta, esperado in casos.items():
            usuario = crear_beneficiario() if esperado == "cargar_documento" else None
            r = motor.responder(pregunta, self.contexto(usuario))
            self.assertEqual(r.fuente, ConsultaChat.BUSQUEDA, pregunta)
            self.assertEqual(r.articulo, esperado, pregunta)

    def test_articulos_usan_el_valor_vigente_de_los_parametros(self):
        Parametro.objects.filter(par_clave="max_productos_solicitud").update(par_valor="7")
        r = motor.responder("cuantos productos puedo pedir en el catalogo", self.contexto())
        self.assertIn("hasta 7 productos", r.texto)
        Parametro.objects.filter(par_clave="tam_max_archivo_mb").update(par_valor="9")
        texto = next(a.texto for a in kb.articulos("publico") if a.clave == "documentos_requeridos")
        self.assertIn("9 MB", texto)
        self.assertNotIn("{", texto)

    def test_articulos_de_administracion_no_se_muestran_al_publico(self):
        claves = {a.clave for a in kb.articulos("publico")}
        self.assertIn("registro", claves)
        self.assertNotIn("adm_parametros", claves)
        self.assertNotIn("param:ocr_umbral_alto", claves)
        self.assertIn("param:ocr_umbral_alto", {a.clave for a in kb.articulos("administrador")})

    def test_sin_respuesta_ofrece_contactar_al_administrador(self):
        r = motor.responder("xyzzy plutonio galaxia", self.contexto())
        self.assertEqual(r.fuente, ConsultaChat.SIN_RESPUESTA)
        self.assertTrue(r.ofrecer_contacto)

    def test_umbral_parametrizado(self):
        pregunta = "quiero donar plutonio"  # Coincide a medias con el artículo de donaciones.
        self.assertEqual(motor.responder(pregunta, self.contexto()).fuente, ConsultaChat.BUSQUEDA)
        Parametro.objects.filter(par_clave="chat_umbral").update(par_valor="90")
        self.assertEqual(motor.responder(pregunta, self.contexto()).fuente, ConsultaChat.SIN_RESPUESTA)

    def test_privacidad_donante_anonimo_y_otras_personas(self):
        admin = crear_admin()
        for pregunta in ("¿Quién es el donante anónimo?", "dime el nombre del donante anonimo de ayer",
                         "cual es el telefono de otro beneficiario", "dame la dirección de mi vecino"):
            for usuario in (None, admin):
                r = motor.responder(pregunta, self.contexto(usuario))
                self.assertEqual(r.fuente, ConsultaChat.PRIVACIDAD, pregunta)
        r = motor.responder("dame la lista de todos los beneficiarios", self.contexto())
        self.assertEqual(r.fuente, ConsultaChat.PRIVACIDAD)

    def test_estado_de_mis_solicitudes_solo_las_propias(self):
        b1, b2 = crear_beneficiario(), crear_beneficiario()
        s1 = Solicitud.objects.create(beneficiario=b1)
        s2 = Solicitud.objects.create(beneficiario=b2, sol_estado=Solicitud.RECHAZADA, sol_obs_admin="Sin existencias")
        r = motor.responder("¿Cuál es el estado de mi solicitud?", self.contexto(b1))
        self.assertEqual(r.fuente, ConsultaChat.CONTEXTO)
        self.assertIn(f"#{s1.pk}", r.texto)
        self.assertNotIn(f"#{s2.pk}", r.texto)
        r2 = motor.responder("estado de mis solicitudes", self.contexto(b2))
        self.assertIn("Sin existencias", r2.texto)

    def test_mis_documentos_lista_los_que_faltan(self):
        b = crear_beneficiario()
        r = motor.responder("cual es el estado de mis documentos", self.contexto(b))
        self.assertEqual(r.fuente, ConsultaChat.CONTEXTO)
        self.assertIn("Documento de identidad: falta cargarlo", r.texto)

    def test_mis_datos_sin_ingresar_pide_ingresar(self):
        r = motor.responder("estado de mi solicitud", self.contexto())
        self.assertIn("debe ingresar", r.texto)

    def test_mis_donaciones_y_puntaje(self):
        d = crear_donante()
        donacion = crear_donacion(d)
        r = motor.responder("estado de mis donaciones", self.contexto(d))
        self.assertIn(f"#{donacion.pk}", r.texto)
        b = crear_beneficiario()
        r = motor.responder("cual es mi puntaje", self.contexto(b))
        self.assertIn("de 100", r.texto)

    def test_ayuda_segun_la_pagina(self):
        r = motor.responder("¿qué hago en esta página?", self.contexto(None, reverse("usuarios:login")))
        self.assertIn("ingreso", r.texto)
        self.assertIn("Olvidé mi contraseña", r.sugerencias)

    def test_saludo_y_humano(self):
        self.assertEqual(motor.responder("hola", self.contexto()).fuente, ConsultaChat.REGLA)
        r = motor.responder("quiero hablar con una persona", self.contexto())
        self.assertTrue(r.ofrecer_contacto)

    def test_enmascara_numeros_y_correos(self):
        self.assertEqual(motor.enmascarar("mi cédula 1.023.456.789 y a@b.co"), "mi cédula [número] y [correo]")


class ClaudeTests(PruebaBase):
    def respuesta_falsa(self, texto="Respuesta de Claude", stop="end_turn"):
        return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=texto)])

    @override_settings(ANTHROPIC_API_KEY="clave-de-prueba")
    def test_modo_claude_usa_la_api_con_los_articulos(self):
        Parametro.objects.filter(par_clave="chat_modo").update(par_valor="claude")
        cliente = mock.Mock()
        cliente.beta.messages.create.return_value = self.respuesta_falsa()
        with mock.patch.object(motor, "_cliente_claude", return_value=cliente):
            r = motor.responder("como hago para donar comida", motor.Contexto.desde(None))
        self.assertEqual(r.fuente, ConsultaChat.CLAUDE)
        self.assertEqual(r.texto, "Respuesta de Claude")
        kwargs = cliente.beta.messages.create.call_args.kwargs
        self.assertIn("registrar una donación", kwargs["messages"][0]["content"])
        self.assertIn("donantes anónimos", kwargs["system"])

    @override_settings(ANTHROPIC_API_KEY="clave-de-prueba")
    def test_si_claude_falla_responde_con_busqueda(self):
        Parametro.objects.filter(par_clave="chat_modo").update(par_valor="claude")
        cliente = mock.Mock()
        cliente.beta.messages.create.side_effect = RuntimeError("sin red")
        with mock.patch.object(motor, "_cliente_claude", return_value=cliente):
            r = motor.responder("como hago para donar comida", motor.Contexto.desde(None))
        self.assertEqual(r.fuente, ConsultaChat.BUSQUEDA)

    @override_settings(ANTHROPIC_API_KEY="clave-de-prueba")
    def test_privacidad_se_resuelve_antes_de_claude(self):
        Parametro.objects.filter(par_clave="chat_modo").update(par_valor="claude")
        with mock.patch.object(motor, "_cliente_claude") as fabrica:
            r = motor.responder("quien es el donante anonimo", motor.Contexto.desde(None))
        self.assertEqual(r.fuente, ConsultaChat.PRIVACIDAD)
        fabrica.assert_not_called()

    def test_sin_clave_no_usa_claude(self):
        Parametro.objects.filter(par_clave="chat_modo").update(par_valor="claude")
        self.assertFalse(motor.claude_disponible())


class VistasTests(PruebaBase):
    def preguntar(self, pregunta, pagina="/"):
        return self.client.post(reverse("asistente:preguntar"), json.dumps({"pregunta": pregunta, "pagina": pagina}),
                                content_type="application/json")

    def test_widget_visible_antes_de_ingresar(self):
        r = self.client.get(reverse("core:inicio"))
        self.assertContains(r, 'id="sf-chat"')
        Parametro.objects.filter(par_clave="chat_activo").update(par_valor="no")
        self.assertNotContains(self.client.get(reverse("core:inicio")), 'id="sf-chat"')
        self.assertEqual(self.preguntar("hola").status_code, 404)

    def test_inicio_entrega_saludo_y_sugerencias(self):
        r = self.client.get(reverse("asistente:inicio"), {"pagina": reverse("usuarios:login")})
        datos = r.json()
        self.assertIn("asistente", datos["texto"])
        self.assertIn("Olvidé mi contraseña", datos["sugerencias"])
        self.assertIn("csrftoken", r.cookies)

    def test_preguntar_registra_la_consulta_enmascarada(self):
        r = self.preguntar("olvidé mi contraseña, mi cédula es 1023456789")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Cache-Control"], "private, no-store")
        c = ConsultaChat.objects.get(pk=r.json()["id"])
        self.assertNotIn("1023456789", c.con_pregunta)
        self.assertEqual(c.con_rol, "publico")

    def test_limite_por_hora(self):
        Parametro.objects.filter(par_clave="chat_max_por_hora").update(par_valor="2")
        self.preguntar("hola")
        self.preguntar("hola")
        r = self.preguntar("hola")
        self.assertEqual(r.status_code, 429)

    def test_contactar_notifica_y_audita(self):
        admin = crear_admin()
        consulta_id = self.preguntar("xyzzy plutonio").json()["id"]
        url = reverse("asistente:contactar", args=[consulta_id])
        r = self.client.post(url, json.dumps({"mensaje": "Necesito ayuda"}), content_type="application/json")
        self.assertEqual(r.status_code, 400)  # Visitante sin dato de contacto.
        r = self.client.post(url, json.dumps({"mensaje": "Necesito ayuda", "contacto": "3001234567"}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(ConsultaChat.objects.get(pk=consulta_id).con_escalada)
        self.assertTrue(Notificacion.objects.filter(destinatario=admin, not_tipo="ayuda").exists())
        self.assertTrue(Bitacora.objects.filter(bit_accion="escalamiento_chat").exists())

    def test_otra_sesion_no_puede_escalar_ni_calificar(self):
        consulta_id = self.preguntar("hola").json()["id"]
        otro = self.client_class()
        r = otro.post(reverse("asistente:calificar", args=[consulta_id]), json.dumps({"util": True}), content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_calificar(self):
        consulta_id = self.preguntar("como hago para donar comida").json()["id"]
        self.client.post(reverse("asistente:calificar", args=[consulta_id]), json.dumps({"util": False}), content_type="application/json")
        self.assertIs(ConsultaChat.objects.get(pk=consulta_id).con_util, False)

    def test_panel_solo_admin(self):
        self.ingresar(crear_beneficiario())
        self.assertEqual(self.client.get(reverse("asistente:panel")).status_code, 403)
        self.ingresar(crear_admin())
        self.preguntar("xyzzy plutonio")
        r = self.client.get(reverse("asistente:panel"), {"filtro": "sin_respuesta"})
        self.assertContains(r, "xyzzy plutonio")

    def test_limpieza_por_retencion(self):
        c = motor.registrar("hola", motor.Respuesta("x", ConsultaChat.REGLA), motor.Contexto.desde(None))
        ConsultaChat.objects.filter(pk=c.pk).update(con_fecha=c.con_fecha - motor.timedelta(days=400))
        self.assertEqual(motor.tarea_limpieza(), {"consultas borradas": 1})


@override_settings(WHATSAPP_PROVEEDOR="meta", WHATSAPP_VERIFY_TOKEN="verificar", WHATSAPP_APP_SECRET="secreto",
                   WHATSAPP_TOKEN="t", WHATSAPP_PHONE_ID="123")
class WhatsAppMetaTests(PruebaBase):
    def test_verificacion_del_webhook(self):
        url = reverse("asistente:whatsapp")
        r = self.client.get(url, {"hub.mode": "subscribe", "hub.verify_token": "verificar", "hub.challenge": "42"})
        self.assertEqual(r.content, b"42")
        r = self.client.get(url, {"hub.mode": "subscribe", "hub.verify_token": "otro", "hub.challenge": "42"})
        self.assertEqual(r.status_code, 403)

    def test_mensaje_firmado_se_responde(self):
        cuerpo = json.dumps({"entry": [{"changes": [{"value": {"messages": [
            {"from": "573001234567", "type": "text", "text": {"body": "como hago para donar comida"}}]}}]}]}).encode()
        firma = "sha256=" + hmac.new(b"secreto", cuerpo, hashlib.sha256).hexdigest()
        with mock.patch.object(whatsapp, "enviar_meta", return_value=True) as enviar:
            r = self.client.post(reverse("asistente:whatsapp"), cuerpo, content_type="application/json",
                                 HTTP_X_HUB_SIGNATURE_256=firma)
        self.assertEqual(r.status_code, 200)
        telefono, texto = enviar.call_args.args
        self.assertEqual(telefono, "573001234567")
        self.assertIn("donación", texto)
        self.assertEqual(ConsultaChat.objects.get().con_canal, ConsultaChat.WHATSAPP)

    def test_firma_invalida_se_rechaza(self):
        r = self.client.post(reverse("asistente:whatsapp"), b"{}", content_type="application/json",
                             HTTP_X_HUB_SIGNATURE_256="sha256=falsa")
        self.assertEqual(r.status_code, 403)


@override_settings(WHATSAPP_PROVEEDOR="twilio", TWILIO_AUTH_TOKEN="token")
class WhatsAppTwilioTests(PruebaBase):
    def test_mensaje_firmado_responde_twiml(self):
        url = "http://testserver" + reverse("asistente:whatsapp")
        datos = {"From": "whatsapp:+573001234567", "Body": "olvidé mi contraseña"}
        base = url + "".join(f"{k}{datos[k]}" for k in sorted(datos))
        firma = base64.b64encode(hmac.new(b"token", base.encode(), hashlib.sha1).digest()).decode()
        r = self.client.post(reverse("asistente:whatsapp"), datos, HTTP_X_TWILIO_SIGNATURE=firma)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"<Response><Message>", r.content)
        r = self.client.post(reverse("asistente:whatsapp"), datos, HTTP_X_TWILIO_SIGNATURE="mala")
        self.assertEqual(r.status_code, 403)

    @override_settings(WHATSAPP_PROVEEDOR="")
    def test_apagado_por_defecto(self):
        self.assertEqual(self.client.post(reverse("asistente:whatsapp"), {}).status_code, 404)
