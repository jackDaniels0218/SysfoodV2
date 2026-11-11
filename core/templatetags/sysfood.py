from django import template
from django.utils.html import format_html

from core import formato

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


@register.filter
def numero(valor, decimales=None):
    """62.50 → 62,5 (coma decimal, sin ceros sobrantes)."""
    return formato.numero(valor, decimales if decimales in (None, "") else int(decimales))


@register.filter
def cantidad(valor, unidad):
    """Cantidad con su unidad según la regla de la unidad: 50 kg, 24 latas, 1 lata, 2,5 L."""
    from inventario.unidades import formatear

    return formatear(valor, unidad)


@register.filter
def porcentaje(parte, total):
    """Porcentaje 0-100 como texto con punto decimal (apto para CSS: width:…%). Un float se localizaría a «76,1»."""
    try:
        valor = max(0.0, min(100.0, float(parte) / float(total) * 100)) if float(total) else 0.0
    except (TypeError, ValueError, ZeroDivisionError):
        valor = 0.0
    return f"{valor:.1f}".rstrip("0").rstrip(".")


def texto_sobre(color):
    """Color de texto (blanco u oscuro) con contraste suficiente sobre un fondo #RRGGBB (WCAG)."""
    try:
        r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    except (TypeError, ValueError):
        return "#fff"

    def canal(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    luminancia = 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)
    return "#14261d" if luminancia > 0.36 else "#fff"


@register.simple_tag
def grupo_badge(perfil, mostrar_puntaje=True):
    """Insignia del grupo de necesidad con su color parametrizado."""
    if perfil is None or perfil.ben_puntaje is None:
        return format_html('<span class="badge bg-light text-dark border">Sin puntaje</span>')
    grupo = perfil.grupo
    if grupo is None:
        return format_html('<span class="badge bg-secondary">{}</span>', formato.numero(perfil.ben_puntaje, 1))
    puntaje = format_html(' <span class="sf-badge-puntaje">{}</span>', formato.numero(perfil.ben_puntaje, 1)) if mostrar_puntaje else ""
    return format_html(
        '<span class="badge sf-grupo" style="background:{};color:{}" title="Puntaje de necesidad: {} de 100">{}{}</span>',
        grupo["color"], texto_sobre(grupo["color"]), formato.numero(perfil.ben_puntaje, 1), grupo["nombre"], puntaje,
    )


@register.simple_tag
def grupo_estilo(grupo):
    if not grupo:
        return ""
    return format_html("background:{};color:{}", grupo["color"], texto_sobre(grupo["color"]))
