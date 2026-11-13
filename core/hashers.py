from django.contrib.auth.hashers import PBKDF2PasswordHasher

from sysfood import rnf


class PBKDF2SysFood(PBKDF2PasswordHasher):
    """PBKDF2-SHA256 con sal y las iteraciones de sysfood/rnf.py.

    Usa el mismo nombre de algoritmo que el de Django, así que las contraseñas ya guardadas siguen
    sirviendo; si cambian las iteraciones, Django las vuelve a calcular cuando el usuario ingresa.
    """

    iterations = rnf.CONTRASENA_ITERACIONES_PBKDF2


class PBKDF2Pruebas(PBKDF2PasswordHasher):
    """Solo para las pruebas automáticas: el mismo algoritmo con pocas iteraciones."""

    iterations = 1000
