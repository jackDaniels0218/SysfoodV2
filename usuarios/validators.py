import re

from django.core.exceptions import ValidationError


class ComplejidadValidator:
    """La contraseña debe tener mayúscula, minúscula, número y carácter especial."""

    def validate(self, password, user=None):
        faltantes = []
        if not re.search(r"[A-ZÁÉÍÓÚÑ]", password):
            faltantes.append("una letra mayúscula")
        if not re.search(r"[a-záéíóúñ]", password):
            faltantes.append("una letra minúscula")
        if not re.search(r"\d", password):
            faltantes.append("un número")
        if not re.search(r"[^A-Za-z0-9ÁÉÍÓÚÑáéíóúñ]", password):
            faltantes.append("un carácter especial")
        if faltantes:
            raise ValidationError("La contraseña debe contener " + ", ".join(faltantes) + ".", code="password_complejidad")

    def get_help_text(self):
        return "Use al menos 8 caracteres con mayúscula, minúscula, número y carácter especial."
