"""Lectura de documentos con OCR (Tesseract) y comparación con los datos registrados.

Todo es opcional: si Tesseract, pytesseract o pdf2image no están instalados,
`disponible()` lo indica y el documento sigue el flujo manual de siempre.
La revisión de calidad de imagen solo necesita Pillow y funciona siempre.
"""

import io
import re
import unicodedata
from contextlib import suppress
from datetime import date
from difflib import SequenceMatcher

from core import parametros

MESES = {
    "ene": 1,
    "enero": 1,
    "feb": 2,
    "febrero": 2,
    "mar": 3,
    "marzo": 3,
    "abr": 4,
    "abril": 4,
    "may": 5,
    "mayo": 5,
    "jun": 6,
    "junio": 6,
    "jul": 7,
    "julio": 7,
    "ago": 8,
    "agosto": 8,
    "sep": 9,
    "sept": 9,
    "septiembre": 9,
    "oct": 10,
    "octubre": 10,
    "nov": 11,
    "noviembre": 11,
    "dic": 12,
    "diciembre": 12,
}


# ---------------------------------------------------------------- Disponibilidad del motor


def disponible():
    """(True, versión) si se puede hacer OCR; (False, motivo) si no."""
    try:
        import pytesseract
    except ImportError:
        return False, "pytesseract no está instalado"
    try:
        version = pytesseract.get_tesseract_version()
    except Exception as error:  # Binario ausente o dañado.
        return False, f"Tesseract no está disponible ({error.__class__.__name__})"
    return True, f"Tesseract {version}"


# ---------------------------------------------------------------- Imágenes


def imagenes(contenido, mime, paginas=2):
    """Convierte el archivo en imágenes PIL (las primeras páginas si es PDF)."""
    from PIL import Image, ImageOps

    if mime == "application/pdf":
        try:
            from pdf2image import convert_from_bytes
        except ImportError as error:
            raise ErrorOCR("pdf2image no está instalado; no se pueden leer PDF.") from error
        try:
            return convert_from_bytes(contenido, dpi=200, first_page=1, last_page=paginas)
        except Exception as error:
            raise ErrorOCR(f"No se pudo convertir el PDF en imagen: {error}") from error
    try:
        imagen = Image.open(io.BytesIO(contenido))
        imagen.load()
    except Exception as error:
        raise ImagenIlegible("El archivo de imagen está dañado o no se puede abrir.") from error
    return [ImageOps.exif_transpose(imagen).convert("RGB")]


class ErrorOCR(Exception):
    """El motor no pudo leer (problema técnico): se deja para revisión manual o reintento."""


class ImagenIlegible(Exception):
    """El archivo no sirve: se debe pedir otro de inmediato."""


def nitidez(imagen):
    """Magnitud del laplaciano en el percentil 99,8 (0-256). Independiente de cuánto texto haya."""
    from PIL import ImageFilter

    gris = imagen.convert("L")
    gris.thumbnail((1200, 1200))
    if gris.width < 8 or gris.height < 8:
        return 0
    borde = gris.filter(ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=2, offset=128))
    borde = borde.crop((2, 2, borde.width - 2, borde.height - 2))
    absoluto = [0] * 129
    for valor, n in enumerate(borde.histogram()):
        absoluto[min(abs(valor - 128), 128)] += n
    corte, acumulado = sum(absoluto) * 0.998, 0
    for valor, n in enumerate(absoluto):
        acumulado += n
        if acumulado >= corte:
            return min(valor * 2, 256)
    return 256


def calidad(imagen, cfg=None):
    """Revisa nitidez, resolución, brillo y contraste. Devuelve dict con 'legible' y 'problemas'."""
    from PIL import ImageStat

    cfg = cfg or {}
    minima = cfg.get("nitidez", parametros.entero("ocr_nitidez_minima"))
    resolucion = cfg.get("resolucion", parametros.entero("ocr_resolucion_minima"))
    gris = imagen.convert("L")
    estad = ImageStat.Stat(gris)
    brillo, contraste = estad.mean[0], estad.stddev[0]
    valor_nitidez = nitidez(imagen)
    problemas = []
    if min(imagen.size) < resolucion:
        problemas.append(
            f"la imagen es muy pequeña ({imagen.width}×{imagen.height} px); acérquese o use mejor resolución"
        )
    if valor_nitidez < minima:
        problemas.append("la imagen está borrosa; sostenga el celular firme y enfoque el documento")
    if brillo < 45:
        problemas.append("la imagen está muy oscura; tómela con más luz")
    elif brillo > 250 and contraste < 6:
        problemas.append("la imagen está sobreexpuesta o en blanco")
    elif contraste < 6:
        problemas.append("la imagen no tiene contraste suficiente")
    return {
        "nitidez": valor_nitidez,
        "nitidez_minima": minima,
        "brillo": round(brillo, 1),
        "contraste": round(contraste, 1),
        "ancho": imagen.width,
        "alto": imagen.height,
        "legible": not problemas,
        "problemas": problemas,
    }


# ---------------------------------------------------------------- Lectura


def leer(lista_imagenes):
    """Texto leído y confianza media de Tesseract (0-100)."""
    import pytesseract

    idioma = parametros.texto("ocr_idioma") or "spa"
    limite = parametros.entero("ocr_tiempo_maximo")
    textos, confianzas = [], []
    for imagen in lista_imagenes:
        try:
            datos = pytesseract.image_to_data(imagen, lang=idioma, output_type=pytesseract.Output.DICT, timeout=limite)
        except RuntimeError as error:  # Tiempo agotado.
            raise ErrorOCR(f"La lectura superó {limite} s.") from error
        except Exception as error:
            raise ErrorOCR(f"Tesseract falló: {error}") from error
        palabras = []
        for palabra, conf in zip(datos["text"], datos["conf"], strict=True):
            palabra = (palabra or "").strip()
            try:
                conf = float(conf)
            except (TypeError, ValueError):
                conf = -1
            if palabra and conf >= 0:
                palabras.append(palabra)
                confianzas.append(conf)
        textos.append(" ".join(palabras))
    media = sum(confianzas) / len(confianzas) if confianzas else 0
    return "\n".join(textos).strip(), round(media, 1)


# ---------------------------------------------------------------- Comparación con lo registrado


def plano(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", texto)


def _parecido(a, b):
    return SequenceMatcher(None, a, b).ratio()


def buscar_numero(texto, numero):
    """1 si el número aparece (aunque tenga puntos o espacios); si no, el mayor parecido ≥ 0,8."""
    objetivo = re.sub(r"\D", "", numero or "")
    if not objetivo:
        return 0.0, ""
    compacto = re.sub(r"(?<=\d)[ .,\-](?=\d)", "", texto)
    candidatos = re.findall(r"\d{5,}", compacto)
    if objetivo in candidatos or any(objetivo in c for c in candidatos):
        return 1.0, objetivo
    mejor, leido = 0.0, ""
    for c in candidatos:
        r = _parecido(objetivo, c)
        if r > mejor:
            mejor, leido = r, c
    return (round(mejor, 2) if mejor >= 0.8 else 0.0), leido


def buscar_nombres(texto, nombres):
    """Proporción de palabras del nombre registrado que aparecen en el texto (tolerante a errores de lectura)."""
    palabras_texto = re.findall(r"[a-z]{3,}", plano(texto))
    esperadas = [p for p in re.findall(r"[a-z]{2,}", plano(nombres))]
    if not esperadas:
        return 0.0, ""
    halladas = []
    for p in esperadas:
        mejor = max((_parecido(p, t) for t in palabras_texto), default=0)
        if mejor >= 0.8:
            halladas.append(p)
    return round(len(halladas) / len(esperadas), 2), " ".join(halladas)


def fechas_en(texto):
    encontradas = set()
    t = plano(texto)
    for d, m, a in re.findall(r"\b(\d{1,2})[/\-. ](\d{1,2})[/\-. ](\d{4})\b", t):
        encontradas.add((int(a), int(m), int(d)))
    for a, m, d in re.findall(r"\b(\d{4})[/\-. ](\d{1,2})[/\-. ](\d{1,2})\b", t):
        encontradas.add((int(a), int(m), int(d)))
    for d, mes, a in re.findall(r"\b(\d{1,2})[ \-/.]*(?:de )?([a-z]{3,10})[ \-/.]*(?:de )?(\d{4})\b", t):
        if mes in MESES:
            encontradas.add((int(a), MESES[mes], int(d)))
    validas = set()
    for a, m, d in encontradas:
        with suppress(ValueError):  # Fechas imposibles leídas por el OCR (p. ej., 31 de febrero).
            validas.add(date(a, m, d))
    return validas


def buscar_fecha(texto, esperada):
    if not esperada:
        return 0.0, ""
    fechas = fechas_en(texto)
    if esperada in fechas:
        return 1.0, esperada.strftime("%d/%m/%Y")
    return 0.0, ", ".join(f.strftime("%d/%m/%Y") for f in sorted(fechas)[:3])


# Confusiones típicas del OCR en el número del subgrupo (C8 leído como CB, A1 como Al...).
_DIGITOS_OCR = str.maketrans({"o": "0", "b": "8", "l": "1", "i": "1", "s": "5", "z": "2", "g": "9"})


def grupos_sisben_en(texto):
    """Grupos del Sisbén IV leídos, como [("C", 8), ...]. Primero los que siguen a «grupo sisben»."""
    t = plano(texto)
    hallados = []
    for zona in re.findall(r"grupo\s*(?:sisben)?\s*(?:iv\b|4\b)?\s*:?\s*([a-z0-9 ]{2,6})", t):
        m = re.match(r"([abcd])\s?([0-9oblisz]{1,2})\b", zona)
        if m:
            hallados.append((m.group(1).upper(), int(m.group(2).translate(_DIGITOS_OCR))))
    for letra, sub in re.findall(r"\b([abcd])\s?(\d{1,2})\b", t):
        hallados.append((letra.upper(), int(sub)))
    return list(dict.fromkeys(hallados))


def buscar_grupo_sisben(texto, letra, subgrupo=None):
    """1 si el certificado trae el mismo grupo y subgrupo; 0,5 si solo coincide la letra; 0 si no."""
    if not letra or letra == "NR":
        return 0.0, ""
    hallados = grupos_sisben_en(texto)
    if subgrupo and (letra, subgrupo) in hallados:
        return 1.0, f"{letra}{subgrupo}"
    misma_letra = [f"{g}{s}" for g, s in hallados if g == letra]
    if misma_letra:
        # Sin subgrupo registrado (datos anteriores) basta la letra; con otro subgrupo es una discrepancia.
        return (0.5 if subgrupo else 1.0), misma_letra[0]
    return 0.0, ", ".join(f"{g}{s}" for g, s in hallados[:3])


def buscar_estado_registro(texto):
    """Estado del registro en el Sisbén: 1 si es «válido», 0 si es otro (suspendido, excluido…), 0,5 si no se lee."""
    t = plano(texto)
    malo = re.search(r"registro\s*:?\s*(no valido|suspendido|excluido|en verificacion|retirado)", t)
    if malo:
        return 0.0, malo.group(1).capitalize()
    if re.search(r"registro\s*:?\s*valido", t):
        return 1.0, "Registro válido"
    return 0.5, ""


def vigencia_sisben(texto):
    """Fecha de «Vigencia hasta» del certificado, o None."""
    m = re.search(r"vigencia\s*(?:hasta)?\s*:?\s*(.{6,30})", plano(texto))
    if not m:
        return None
    fechas = fechas_en(m.group(1))
    return max(fechas) if fechas else None


def buscar_vigencia(texto, hoy=None):
    """1 si la vigencia no ha vencido, 0 si venció, 0,5 si no se lee."""
    fecha = vigencia_sisben(texto)
    if fecha is None:
        return 0.5, ""
    hoy = hoy or date.today()
    return (1.0 if fecha >= hoy else 0.0), f"Hasta {fecha.strftime('%d/%m/%Y')}"


def buscar_estrato(texto, estrato):
    hallado = re.search(r"estrato\s*:?\s*(\d)", plano(texto))
    if hallado:
        return (1.0 if int(hallado.group(1)) == estrato else 0.0), f"Estrato {hallado.group(1)}"
    return 0.0, ""


def campos_a_comparar(doc):
    """[(clave, etiqueta, valor esperado legible, función de búsqueda, peso)] según el tipo de documento."""
    usuario = doc.usuario
    perfil = getattr(usuario, "perfil_beneficiario", None)
    nombre = usuario.nombre_completo
    if perfil is None:
        return []
    numero = perfil.ben_num_doc
    base = [
        ("numero", "Número de documento", numero, lambda t: buscar_numero(t, numero), 3),
        ("nombres", "Nombres y apellidos", nombre, lambda t: buscar_nombres(t, nombre), 2),
    ]
    if doc.docv_tipo == "identidad":
        fecha = perfil.ben_fec_exp_doc
        return base + [
            (
                "fecha",
                "Fecha de expedición",
                fecha.strftime("%d/%m/%Y") if fecha else "",
                lambda t: buscar_fecha(t, fecha),
                1,
            )
        ]
    if doc.docv_tipo == "sisben":
        return base + [
            (
                "sisben",
                "Grupo y subgrupo de Sisbén",
                perfil.sisben_codigo,
                lambda t: buscar_grupo_sisben(t, perfil.ben_sisben, perfil.ben_sisben_subgrupo),
                2,
                1.0,  # Obligatorio: sin coincidencia exacta nunca se aprueba solo.
            ),
            # Obligatorios: un registro no válido o un certificado vencido nunca se aprueban solos.
            ("registro", "Estado del registro", "Registro válido", buscar_estado_registro, 1, 0.5),
            ("vigencia", "Vigencia del certificado", "Vigente", buscar_vigencia, 1, 0.5),
        ]
    if doc.docv_tipo == "residencia":
        return [
            base[1],
            ("direccion", "Dirección", perfil.ben_dir, lambda t: buscar_nombres(t, perfil.ben_dir), 2),
            ("estrato", "Estrato", f"Estrato {perfil.ben_estrato}", lambda t: buscar_estrato(t, perfil.ben_estrato), 1),
        ]
    return base  # Discapacidad: número y nombre.


def comparar(doc, texto):
    filas = []
    for clave, etiqueta, esperado, funcion, peso, *minimo in campos_a_comparar(doc):
        coincide, leido = funcion(texto)
        filas.append(
            {
                "campo": clave,
                "etiqueta": etiqueta,
                "esperado": str(esperado),
                "leido": leido,
                "coincide": coincide,
                "peso": peso,
                "minimo": minimo[0] if minimo else 0,
            }
        )
    return filas


def incumple_obligatorios(filas):
    """Campos obligatorios que no alcanzan su mínimo: impiden la aprobación automática."""
    return [f for f in filas if f["coincide"] < f.get("minimo", 0)]


def confianza(filas, confianza_ocr):
    """confianza = 100 × Σ(peso × coincidencia) / Σ peso × (0,7 + 0,3 × legibilidad), con legibilidad = confianza OCR / 100."""
    total = sum(f["peso"] for f in filas)
    if not total:
        return 0.0
    coincidencias = sum(f["peso"] * f["coincide"] for f in filas) / total
    return round(100 * coincidencias * (0.7 + 0.3 * max(0.0, min(confianza_ocr, 100)) / 100), 1)
