from django import template

register = template.Library()


@register.filter
def obtener(diccionario, clave):
    """Valor de un diccionario por clave (para plantillas)."""
    try:
        return diccionario.get(clave)
    except AttributeError:
        return None


@register.filter
def decimal_input(valor):
    """Formatea un Decimal para un input numérico (punto decimal, sin ceros sobrantes)."""
    if valor is None:
        return ""
    texto = format(valor, "f")
    return texto.rstrip("0").rstrip(".") if "." in texto else texto
