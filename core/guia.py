"""Guía de primeros pasos: los pasos de cada rol y cuáles ya cumplió el usuario.

Se muestra en el panel hasta que se completan todos los pasos. Cada paso dice qué
falta y lleva directo a la pantalla donde se hace.
"""
from collections import namedtuple

from django.urls import reverse

Paso = namedtuple("Paso", "titulo texto url accion hecho")


def _beneficiario(u):
    from entregas.models import Entrega
    from usuarios.models import DocumentoValidacion as Doc

    perfil = u.perfil_beneficiario
    requeridos = set(Doc.TIPOS_BENEFICIARIO[:3]) | ({Doc.DISCAPACIDAD} if perfil.ben_discapacidad else set())
    cargados = set(u.documentos.exclude(docv_estado=Doc.RECHAZADO).values_list("docv_tipo", flat=True))
    faltan = len(requeridos - cargados)
    tiene_solicitud = u.solicitudes.exists()
    return [
        Paso("Complete sus datos", "Dirección, personas del hogar, Sisbén y estrato: con ellos se calcula su prioridad.",
             reverse("usuarios:perfil"), "Revisar mis datos", bool(perfil.ben_dir and perfil.ben_num_personas)),
        Paso("Cargue sus documentos",
             f"Falta{'n' if faltan != 1 else ''} {faltan} documento{'s' if faltan != 1 else ''}. Puede tomarles una foto con el celular."
             if faltan else "Ya cargó todos los documentos requeridos.",
             reverse("usuarios:documentos"), "Ir a documentos", faltan == 0),
        Paso("Espere la verificación", "El sistema lee sus documentos al instante; si hay dudas, el administrador los revisa.",
             reverse("usuarios:documentos"), "Ver el estado", perfil.verificado),
        Paso("Pida alimentos", "Elija productos del catálogo, agréguelos al carrito y envíe la solicitud.",
             reverse("solicitudes:catalogo"), "Ir al catálogo", tiene_solicitud),
        Paso("Siga su entrega", "Con el código de seguimiento verá cuándo está lista para recoger o en camino.",
             reverse("entregas:seguimiento"), "Ver seguimiento", Entrega.objects.filter(solicitud__beneficiario=u).exists()),
    ]


def _donante(u):
    from usuarios.models import DocumentoValidacion as Doc

    pasos = [
        Paso("Revise sus datos", "Verifique su teléfono y dirección para que el administrador pueda contactarle.",
             reverse("usuarios:perfil"), "Revisar mis datos", True),
    ]
    perfil = getattr(u, "perfil_donante", None)
    if perfil is not None and perfil.don_tipo_persona == "juridica":
        cargados = set(u.documentos.exclude(docv_estado=Doc.RECHAZADO).values_list("docv_tipo", flat=True))
        pasos.append(Paso("Cargue los documentos de la empresa", "Cámara de Comercio y RUT.", reverse("usuarios:documentos"),
                          "Ir a documentos", set(Doc.TIPOS_DONANTE_JURIDICO) <= cargados))
    donaciones = u.donaciones.all()
    pasos += [
        Paso("Registre su primera donación", "Agregue cada producto con su cantidad y fecha de vencimiento. Puede ser anónima.",
             reverse("donaciones:nueva"), "Donar ahora", donaciones.exists()),
        Paso("Vea a dónde llega", "Cuando sus productos se reservan o entregan, recibe un aviso y lo ve en el detalle.",
             reverse("donaciones:mis_donaciones"), "Mis donaciones", donaciones.filter(dona_estado__in=["reservada", "entregada"]).exists()),
    ]
    return pasos


def _administrador(u):
    from catalogo.models import Bodega, Categoria

    from . import parametros

    return [
        Paso("Cree una bodega", "Las donaciones ingresan a una bodega activa.", reverse("catalogo:bodegas"), "Ir a bodegas",
             Bodega.objects.filter(bod_estado="activa").exists()),
        Paso("Defina las categorías", "Con días de alerta de vencimiento propios si lo necesita.", reverse("catalogo:categorias"),
             "Ir a categorías", Categoria.objects.exists()),
        Paso("Elija la bodega predeterminada", "Parámetro «bodega_predeterminada»: donde entran los productos donados.",
             reverse("core:parametros") + "#inventario", "Ir a parámetros", bool(parametros.texto("bodega_predeterminada"))),
        Paso("Revise los pesos del puntaje", "Ajuste cómo se prioriza a los beneficiarios (Sisbén, estrato, hogar…).",
             reverse("core:parametros") + "#puntaje-de-necesidad", "Ver parámetros", _vio_parametros(u)),
    ]


def _vio_parametros(u):
    from .models import Bitacora

    return Bitacora.objects.filter(usuario=u, bit_accion="cambio_parametro").exists()


def pasos(usuario):
    if usuario.es_admin:
        return _administrador(usuario)
    if usuario.es_donante:
        return _donante(usuario)
    if usuario.es_beneficiario and hasattr(usuario, "perfil_beneficiario"):
        return _beneficiario(usuario)
    return []


def resumen(usuario):
    """{pasos, hechos, total, siguiente, completa} para la plantilla."""
    lista = pasos(usuario)
    hechos = sum(p.hecho for p in lista)
    siguiente = next((i for i, p in enumerate(lista) if not p.hecho), None)
    return {"pasos": lista, "hechos": hechos, "total": len(lista), "siguiente": siguiente,
            "completa": bool(lista) and hechos == len(lista), "porcentaje": round(100 * hechos / len(lista)) if lista else 100}
