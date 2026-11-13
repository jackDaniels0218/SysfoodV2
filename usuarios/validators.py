import re

from django.core.exceptions import ValidationError

from sysfood import rnf


class ComplejidadValidator:
    """Tipos de carácter que exige la contraseña, según sysfood/rnf.py (CONTRASENA_EXIGE_*)."""

    def validate(self, password, user=None):
        reglas = (
            (rnf.CONTRASENA_EXIGE_MAYUSCULA, r"[A-ZÁÉÍÓÚÑ]", "una letra mayúscula"),
            (rnf.CONTRASENA_EXIGE_MINUSCULA, r"[a-záéíóúñ]", "una letra minúscula"),
            (rnf.CONTRASENA_EXIGE_NUMERO, r"\d", "un número"),
            (rnf.CONTRASENA_EXIGE_ESPECIAL, r"[^A-Za-z0-9ÁÉÍÓÚÑáéíóúñ]", "un carácter especial"),
        )
        faltantes = [texto for exige, patron, texto in reglas if exige and not re.search(patron, password)]
        if faltantes:
            raise ValidationError(
                "La contraseña debe contener " + ", ".join(faltantes) + ".", code="password_complejidad"
            )

    def get_help_text(self):
        return "La contraseña debe " + rnf.requisitos_contrasena() + "."
