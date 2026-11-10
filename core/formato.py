"""Formato de números para mostrar en pantalla (convención colombiana: 1.500,25)."""
from decimal import Decimal, InvalidOperation


def numero(valor, decimales=None):
    """62.50 → «62,5»; 1500 → «1.500»; 2.5 → «2,5». Con `decimales` fija la precisión máxima."""
    if valor is None or valor == "":
        return ""
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return str(valor)
    if decimales is not None:
        d = d.quantize(Decimal(1).scaleb(-decimales)) if decimales > 0 else d.quantize(Decimal(1))
    texto = format(d, "f")
    entero, _, fraccion = texto.partition(".")
    fraccion = fraccion.rstrip("0")
    signo = "-" if entero.startswith("-") else ""
    entero = entero.lstrip("-")
    grupos = []
    while len(entero) > 3:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    grupos.insert(0, entero)
    resultado = signo + ".".join(grupos)
    if resultado in ("-0", ""):
        resultado = "0"
    return f"{resultado},{fraccion}" if fraccion else resultado
