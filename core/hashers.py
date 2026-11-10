from django.contrib.auth.hashers import PBKDF2PasswordHasher


class PBKDF2Pruebas(PBKDF2PasswordHasher):
    """Solo para las pruebas automáticas: el mismo algoritmo con pocas iteraciones."""

    iterations = 1000
