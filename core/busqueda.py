"""Búsqueda global (atajo / o Ctrl+K).

Cada rol busca solo en lo que puede ver:
- Administrador: páginas, usuarios, donaciones, inventario, solicitudes y entregas.
  Las donaciones anónimas nunca coinciden por el nombre del donante (no se revela por la búsqueda).
- Donante: páginas y sus propias donaciones.
- Beneficiario: páginas, productos del catálogo (si está verificado), sus solicitudes y entregas.
"""

import re
import unicodedata
from urllib.parse import urlencode

from django.db.models import Q
from django.urls import reverse

LIMITE = 5

# (título, nombre de URL, palabras clave, roles)
PAGINAS = [
    ("Panel", "reportes:dashboard", "inicio resumen tablero", ("administrador", "donante", "beneficiario")),
    ("Mis datos", "usuarios:perfil", "perfil cuenta direccion telefono", ("administrador", "donante", "beneficiario")),
    ("Notificaciones", "core:notificaciones", "avisos campana mensajes", ("administrador", "donante", "beneficiario")),
    ("Cuentas de usuario", "usuarios:lista", "usuarios beneficiarios donantes cuentas", ("administrador",)),
    (
        "Documentos por revisar",
        "usuarios:documentos_pendientes",
        "verificacion documentos cola ocr",
        ("administrador",),
    ),
    ("Inventario", "inventario:lista", "existencias productos bodega vencimiento", ("administrador",)),
    ("Donaciones", "donaciones:lista_admin", "donaciones donantes", ("administrador",)),
    ("Categorías", "catalogo:categorias", "categorias tipos", ("administrador",)),
    ("Bodegas", "catalogo:bodegas", "bodegas almacenes", ("administrador",)),
    ("Solicitudes", "solicitudes:lista_admin", "solicitudes pedidos aprobar", ("administrador",)),
    ("Entregas", "entregas:lista", "entregas despachos", ("administrador",)),
    (
        "Reportes y estadísticas",
        "reportes:reportes",
        "reportes estadisticas graficos exportar pdf excel csv",
        ("administrador",),
    ),
    ("Envíos programados", "reportes:programados", "correo reportes programados", ("administrador",)),
    ("Mapa de beneficiarios", "reportes:mapa", "mapa calor ubicacion", ("administrador",)),
    ("Trazabilidad y auditoría", "core:trazabilidad", "bitacora auditoria kardex historial", ("administrador",)),
    ("Parámetros", "core:parametros", "configuracion parametros ajustes", ("administrador",)),
    ("Tareas automáticas", "core:tareas", "tareas programadas", ("administrador",)),
    ("Consultas del asistente", "asistente:panel", "chat ayuda consultas", ("administrador",)),
    ("Donar", "donaciones:nueva", "nueva donacion registrar donar", ("donante",)),
    ("Mis donaciones", "donaciones:mis_donaciones", "donaciones historial", ("donante",)),
    ("Catálogo", "solicitudes:catalogo", "alimentos productos pedir", ("beneficiario",)),
    ("Carrito", "solicitudes:carrito", "carrito canasta", ("beneficiario",)),
    ("Mis solicitudes", "solicitudes:mis_solicitudes", "solicitudes pedidos", ("beneficiario",)),
    ("Seguimiento de entregas", "entregas:seguimiento", "seguimiento codigo entrega", ("beneficiario",)),
    ("Documentos", "usuarios:documentos", "documentos cargar verificacion", ("beneficiario", "donante")),
    (
        "¿Cómo se calcula el puntaje?",
        "usuarios:ayuda_puntaje",
        "puntaje prioridad necesidad",
        ("administrador", "beneficiario"),
    ),
]


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in texto if not unicodedata.combining(c)).strip()


def _numero(consulta):
    m = re.fullmatch(r"#?\s*(\d{1,9})", consulta.strip())
    return int(m.group(1)) if m else None


def _paginas(consulta, rol):
    q = _normalizar(consulta)
    resultados = []
    for titulo, nombre, claves, roles in PAGINAS:
        if rol in roles and (q in _normalizar(titulo) or any(p.startswith(q) for p in claves.split())):
            resultados.append(
                {"titulo": titulo, "detalle": "Ir a la página", "url": reverse(nombre), "icono": "arrow-return-right"}
            )
    return resultados[:LIMITE]


def buscar(usuario, consulta):
    """[(grupo, [resultado])] con resultado = {titulo, detalle, url, icono}."""
    from donaciones.models import Donacion
    from entregas.models import Entrega
    from inventario.models import Inventario
    from solicitudes.models import Solicitud
    from usuarios.models import Usuario

    consulta = (consulta or "").strip()[:80]
    if len(consulta) < 2 and _numero(consulta) is None:
        return []
    rol = usuario.usu_rol
    numero_id = _numero(consulta)
    grupos = [("Páginas", _paginas(consulta, rol))]

    if usuario.es_admin:
        usuarios = Usuario.objects.filter(
            Q(usu_nom__icontains=consulta)
            | Q(usu_ape__icontains=consulta)
            | Q(usu_correo__icontains=consulta)
            | Q(perfil_beneficiario__ben_num_doc=consulta)
            | Q(perfil_donante__don_doc_nit=consulta)
        ).distinct()[:LIMITE]
        grupos.append(
            (
                "Usuarios",
                [
                    {
                        "titulo": u.nombre_completo,
                        "detalle": f"{u.get_usu_rol_display()} · {u.usu_correo}",
                        "url": reverse("usuarios:revisar_usuario", args=[u.pk]),
                        "icono": "person",
                    }
                    for u in usuarios
                ],
            )
        )
        donaciones = (
            Donacion.objects.filter(
                Q(pk=numero_id)
                if numero_id
                else (
                    Q(dona_anonima=False)
                    & (
                        Q(donante__usu_nom__icontains=consulta)
                        | Q(donante__usu_ape__icontains=consulta)
                        | Q(donante__perfil_donante__don_raz_soc__icontains=consulta)
                    )
                )
                | Q(detalles__dd_nom__icontains=consulta)
            )
            .distinct()
            .order_by("-dona_fec_reg")[:LIMITE]
        )
        grupos.append(
            (
                "Donaciones",
                [
                    {
                        "titulo": f"Donación #{d.pk}",
                        "detalle": f"{d.nombre_publico} · {d.get_dona_estado_display()}",
                        "url": reverse("donaciones:detalle", args=[d.pk]),
                        "icono": "gift",
                    }
                    for d in donaciones
                ],
            )
        )
        inventario = (
            Inventario.objects.filter(Q(inv_nom__icontains=consulta) | Q(detalle__dd_lote__icontains=consulta))
            .exclude(inv_estado=Inventario.RETIRADO)
            .order_by("inv_fec_venc")[:LIMITE]
        )
        grupos.append(
            (
                "Inventario",
                [
                    {
                        "titulo": i.inv_nom,
                        "detalle": f"{i.cantidad_texto(i.inv_cant_disp)} · vence {i.inv_fec_venc:%d/%m/%Y}",
                        "url": reverse("inventario:detalle", args=[i.pk]),
                        "icono": "box-seam",
                    }
                    for i in inventario
                ],
            )
        )
        solicitudes = (
            Solicitud.objects.filter(
                Q(pk=numero_id)
                if numero_id
                else Q(beneficiario__usu_nom__icontains=consulta) | Q(beneficiario__usu_ape__icontains=consulta)
            )
            .select_related("beneficiario")
            .order_by("-sol_fec_envio")[:LIMITE]
        )
        grupos.append(
            (
                "Solicitudes",
                [
                    {
                        "titulo": f"Solicitud #{s.pk}",
                        "detalle": f"{s.beneficiario.nombre_completo} · {s.get_sol_estado_display()}",
                        "url": reverse("solicitudes:admin_detalle", args=[s.pk]),
                        "icono": "cart-check",
                    }
                    for s in solicitudes
                ],
            )
        )
        entregas = Entrega.objects.filter(ent_cod__iexact=consulta)[:LIMITE]
        grupos.append(
            (
                "Entregas",
                [
                    {
                        "titulo": f"Entrega {e.ent_cod}",
                        "detalle": e.get_ent_estado_display(),
                        "url": reverse("entregas:detalle", args=[e.pk]),
                        "icono": "truck",
                    }
                    for e in entregas
                ],
            )
        )
    elif usuario.es_donante:
        donaciones = usuario.donaciones.filter(
            Q(pk=numero_id) if numero_id else Q(detalles__dd_nom__icontains=consulta)
        ).distinct()[:LIMITE]
        grupos.append(
            (
                "Mis donaciones",
                [
                    {
                        "titulo": f"Donación #{d.pk}",
                        "detalle": d.get_dona_estado_display(),
                        "url": reverse("donaciones:detalle", args=[d.pk]),
                        "icono": "gift",
                    }
                    for d in donaciones
                ],
            )
        )
    elif usuario.es_beneficiario:
        perfil = getattr(usuario, "perfil_beneficiario", None)
        if perfil is not None and perfil.verificado:
            productos = Inventario.catalogo().filter(inv_nom__icontains=consulta).order_by("inv_fec_venc")[:LIMITE]
            grupos.append(
                (
                    "Catálogo",
                    [
                        {
                            "titulo": i.inv_nom,
                            "detalle": f"Disponible: {i.cantidad_texto(i.inv_cant_disp)}",
                            "url": reverse("solicitudes:catalogo") + "?" + urlencode({"q": i.inv_nom}),
                            "icono": "basket",
                        }
                        for i in productos
                    ],
                )
            )
        solicitudes = usuario.solicitudes.filter(pk=numero_id) if numero_id else usuario.solicitudes.none()
        grupos.append(
            (
                "Mis solicitudes",
                [
                    {
                        "titulo": f"Solicitud #{s.pk}",
                        "detalle": s.get_sol_estado_display(),
                        "url": reverse("solicitudes:detalle", args=[s.pk]),
                        "icono": "cart-check",
                    }
                    for s in solicitudes[:LIMITE]
                ],
            )
        )
        entregas = Entrega.objects.filter(solicitud__beneficiario=usuario, ent_cod__iexact=consulta)[:LIMITE]
        grupos.append(
            (
                "Mis entregas",
                [
                    {
                        "titulo": f"Entrega {e.ent_cod}",
                        "detalle": e.get_ent_estado_display(),
                        "url": reverse("entregas:seguimiento") + f"?codigo={e.ent_cod}",
                        "icono": "truck",
                    }
                    for e in entregas
                ],
            )
        )
    return [(g, r) for g, r in grupos if r]
