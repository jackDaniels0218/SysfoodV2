from django.conf import settings
from django.db import models


class ConsultaChat(models.Model):
    """Pregunta hecha al asistente de ayuda y su respuesta (sirve para auditar y mejorar la base de conocimiento).

    Los números largos (documentos, teléfonos) se enmascaran antes de guardar la pregunta.
    """

    REGLA, BUSQUEDA, CLAUDE, CONTEXTO, PRIVACIDAD, SIN_RESPUESTA, LIMITE = (
        "regla",
        "busqueda",
        "claude",
        "contexto",
        "privacidad",
        "sin_respuesta",
        "limite",
    )
    FUENTES = [
        (REGLA, "Regla"),
        (BUSQUEDA, "Búsqueda en la base de conocimiento"),
        (CLAUDE, "API de Claude"),
        (CONTEXTO, "Datos propios del usuario"),
        (PRIVACIDAD, "Bloqueada por privacidad"),
        (SIN_RESPUESTA, "Sin respuesta"),
        (LIMITE, "Límite de consultas"),
    ]
    WEB, WHATSAPP = "web", "whatsapp"
    CANALES = [(WEB, "Web"), (WHATSAPP, "WhatsApp")]

    con_id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="usu_id",
        related_name="+",
    )
    con_sesion = models.CharField("sesión (huella)", max_length=64, blank=True, db_index=True)
    con_canal = models.CharField("canal", max_length=10, choices=CANALES, default=WEB)
    con_rol = models.CharField("rol", max_length=15, blank=True)
    con_pagina = models.CharField("página", max_length=200, blank=True)
    con_pregunta = models.CharField("pregunta", max_length=500)
    con_respuesta = models.TextField("respuesta", blank=True)
    con_fuente = models.CharField("fuente", max_length=15, choices=FUENTES, db_index=True)
    con_articulo = models.CharField("artículo usado", max_length=60, blank=True)
    con_similitud = models.PositiveSmallIntegerField("similitud (0-100)", null=True, blank=True)
    con_util = models.BooleanField("le fue útil", null=True, blank=True)
    con_escalada = models.BooleanField("enviada al administrador", default=False, db_index=True)
    con_contacto = models.CharField("contacto para responder", max_length=150, blank=True)
    con_mensaje = models.TextField("mensaje para el administrador", blank=True)
    con_atendida = models.BooleanField("atendida", default=False)
    con_fecha = models.DateTimeField("fecha", auto_now_add=True, db_index=True)

    class Meta:
        db_table = "consulta_chat"
        ordering = ["-con_fecha", "-con_id"]
        verbose_name = "consulta del asistente"

    def __str__(self):
        return f"{self.con_fecha:%Y-%m-%d} {self.con_pregunta[:40]}"
