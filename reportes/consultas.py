"""Consultas de los reportes del administrador (Actividad 15).

Cada reporte devuelve un diccionario con: titulo, columnas, filas, grafico y resumen.
Las donaciones anónimas nunca muestran la identidad del donante en los reportes.
"""

from collections import Counter, OrderedDict, namedtuple

from django.db.models import Count, Q
from django.utils import timezone

from core import parametros
from core.fechas import filtrar_rango, inicio_dia, inicio_dia_siguiente
from core.formato import numero
from donaciones.models import ANONIMO, Donacion
from entregas.models import Entrega
from inventario.models import Inventario
from solicitudes.models import Solicitud
from usuarios.models import DocumentoValidacion, PerfilBeneficiario, Usuario


def _fecha(valor):
    return timezone.localtime(valor).strftime("%d/%m/%Y") if valor else ""


def _rango(qs, filtros, campo):
    return filtrar_rango(qs, campo, filtros.get("desde"), filtros.get("hasta"))


def _grafico(tipo, conteo, etiquetas_legibles=None, titulo=""):
    etiquetas_legibles = etiquetas_legibles or {}
    claves = list(conteo.keys())
    return {
        "tipo": tipo,
        "titulo": titulo,
        "etiquetas": [etiquetas_legibles.get(k, k) for k in claves],
        "datos": [conteo[k] for k in claves],
    }


def nombre_donante_reporte(donacion):
    return ANONIMO if donacion.dona_anonima else donacion.nombre_donante(donacion.donante)


def reporte_donaciones(f):
    qs = _rango(Donacion.objects.select_related("donante__perfil_donante"), f, "dona_fec_reg")
    if f.get("estado"):
        qs = qs.filter(dona_estado=f["estado"])
    if f.get("donante"):
        qs = qs.filter(donante_id=f["donante"])
    if f.get("categoria"):
        qs = qs.filter(detalles__categoria_id=f["categoria"]).distinct()
    if f.get("bodega"):
        qs = qs.filter(detalles__inventario__bodega_id=f["bodega"]).distinct()
    qs = qs.annotate(n=Count("detalles", distinct=True)).order_by("dona_fec_reg")
    filas, por_estado, por_mes = [], Counter(), Counter()
    for d in qs:
        filas.append(
            [
                d.dona_id,
                _fecha(d.dona_fec_reg),
                nombre_donante_reporte(d),
                d.get_dona_estado_display(),
                d.n,
                "Sí" if d.dona_anonima else "No",
            ]
        )
        por_estado[d.dona_estado] += 1
        por_mes[timezone.localtime(d.dona_fec_reg).strftime("%Y-%m")] += 1
    return {
        "titulo": TIPOS["donaciones"],
        "columnas": ["N.º", "Fecha", "Donante", "Estado", "Productos", "Anónima"],
        "filas": filas,
        "grafico": _grafico(
            "bar",
            OrderedDict((k, por_estado[k]) for k, _ in Donacion.ESTADOS),
            dict(Donacion.ESTADOS),
            "Donaciones por estado",
        ),
        "grafico2": _grafico("line", OrderedDict(sorted(por_mes.items())), titulo="Donaciones por mes"),
        "resumen": [("Total de donaciones", len(filas))] + [(n, por_estado[k]) for k, n in Donacion.ESTADOS],
    }


def _filtrar_inventario(qs, f):
    if f.get("categoria"):
        qs = qs.filter(categoria_id=f["categoria"])
    if f.get("bodega"):
        qs = qs.filter(bodega_id=f["bodega"])
    if f.get("donante"):
        qs = qs.filter(detalle__donacion__donante_id=f["donante"])
    return qs


def reporte_inventario(f):
    qs = Inventario.objects.exclude(inv_estado=Inventario.RETIRADO).select_related("categoria", "bodega")
    qs = _filtrar_inventario(_rango(qs, f, "inv_fec_ingreso"), f)
    if f.get("estado"):
        qs = qs.filter(inv_est_venc=f["estado"])
    qs = qs.order_by("inv_fec_venc")
    vigencias = dict(Inventario.VIGENCIAS)
    filas, conteo = [], Counter()
    for i in qs:
        filas.append(
            [
                i.inv_id,
                i.inv_nom,
                i.categoria.cat_nom,
                i.bodega.bod_nom,
                i.cantidad_texto(i.inv_cant_disp),
                i.cantidad_texto(i.inv_cant_reserv),
                i.inv_fec_venc.strftime("%d/%m/%Y"),
                i.dias_para_vencer,
                vigencias[i.inv_est_venc],
            ]
        )
        conteo[i.inv_est_venc] += 1
    return {
        "titulo": TIPOS["inventario"],
        "columnas": ["ID", "Producto", "Categoría", "Bodega", "Disponible", "Reservado", "Vence", "Días", "Vigencia"],
        "filas": filas,
        "grafico": _grafico(
            "doughnut",
            OrderedDict((k, conteo[k]) for k, _ in Inventario.VIGENCIAS),
            vigencias,
            "Inventario por vigencia",
        ),
        "resumen": [("Productos en inventario", len(filas))] + [(n, conteo[k]) for k, n in Inventario.VIGENCIAS],
        "estados": Inventario.VIGENCIAS,
    }


def reporte_vencidos(f):
    qs = Inventario.objects.filter(
        Q(inv_est_venc=Inventario.VENCIDO) | Q(inv_estado=Inventario.RETIRADO)
    ).select_related("categoria", "bodega", "usuario_baja")
    qs = _filtrar_inventario(qs, f)
    if f.get("desde"):
        qs = qs.filter(Q(inv_fec_venc__gte=f["desde"]) | Q(inv_fec_baja__gte=inicio_dia(f["desde"])))
    if f.get("hasta"):
        qs = qs.filter(Q(inv_fec_venc__lte=f["hasta"]) | Q(inv_fec_baja__lt=inicio_dia_siguiente(f["hasta"])))
    if f.get("estado"):
        qs = (
            qs.filter(inv_mot_baja=f["estado"])
            if f["estado"] != "pendiente"
            else qs.exclude(inv_estado=Inventario.RETIRADO)
        )
    motivos = dict(Inventario.MOTIVOS_BAJA)
    filas, conteo = [], Counter()
    for i in qs.order_by("inv_fec_venc"):
        motivo = motivos.get(i.inv_mot_baja, "Pendiente de retiro")
        cantidad = i.inv_cant_inicial if i.inv_estado == Inventario.RETIRADO else i.inv_cant_disp
        filas.append(
            [
                i.inv_id,
                i.inv_nom,
                i.categoria.cat_nom,
                i.bodega.bod_nom,
                i.cantidad_texto(cantidad),
                i.inv_fec_venc.strftime("%d/%m/%Y"),
                motivo,
                _fecha(i.inv_fec_baja),
                i.usuario_baja.nombre_completo if i.usuario_baja else "",
            ]
        )
        conteo[motivo] += 1
    return {
        "titulo": TIPOS["vencidos"],
        "columnas": [
            "ID",
            "Producto",
            "Categoría",
            "Bodega",
            "Cantidad",
            "Vence",
            "Motivo",
            "Fecha de baja",
            "Retirado por",
        ],
        "filas": filas,
        "grafico": _grafico("bar", OrderedDict(conteo.most_common()), titulo="Productos por motivo"),
        "resumen": [("Total", len(filas))] + list(conteo.most_common()),
        "estados": [("pendiente", "Pendiente de retiro")] + Inventario.MOTIVOS_BAJA,
    }


def reporte_solicitudes(f):
    qs = _rango(Solicitud.objects.select_related("beneficiario", "entrega"), f, "sol_fec_envio")
    if f.get("estado"):
        qs = qs.filter(Q(sol_estado=f["estado"]) | Q(entrega__ent_estado=f["estado"]))
    if f.get("bodega"):
        qs = qs.filter(entrega__bodega_id=f["bodega"])
    if f.get("categoria"):
        qs = qs.filter(detalles__inventario__categoria_id=f["categoria"]).distinct()
    if f.get("donante"):
        qs = qs.filter(detalles__inventario__detalle__donacion__donante_id=f["donante"]).distinct()
    estados_sol, estados_ent = dict(Solicitud.ESTADOS), dict(Entrega.ESTADOS)
    filas, c_sol, c_ent, tiempos = [], Counter(), Counter(), []
    for s in qs.order_by("sol_fec_envio"):
        e = getattr(s, "entrega", None)
        dias = ""
        if e and e.ent_fec_entrega:
            dias = round((e.ent_fec_entrega - s.sol_fec_envio).total_seconds() / 86400, 1)
            tiempos.append(dias)
        filas.append(
            [
                s.sol_id,
                _fecha(s.sol_fec_envio),
                s.beneficiario.nombre_completo,
                estados_sol[s.sol_estado],
                e.ent_cod if e else "",
                estados_ent[e.ent_estado] if e else "",
                _fecha(e.ent_fec_entrega) if e else "",
                dias,
            ]
        )
        c_sol[s.sol_estado] += 1
        if e:
            c_ent[e.ent_estado] += 1
    promedio = round(sum(tiempos) / len(tiempos), 1) if tiempos else 0
    return {
        "titulo": TIPOS["solicitudes"],
        "columnas": ["N.º", "Enviada", "Beneficiario", "Solicitud", "Entrega", "Estado entrega", "Entregada", "Días"],
        "filas": filas,
        "grafico": _grafico(
            "bar", OrderedDict((k, c_sol[k]) for k, _ in Solicitud.ESTADOS), estados_sol, "Solicitudes por estado"
        ),
        "grafico2": _grafico(
            "bar", OrderedDict((k, c_ent[k]) for k, _ in Entrega.ESTADOS), estados_ent, "Entregas por estado"
        ),
        "resumen": [
            ("Solicitudes", len(filas)),
            ("Tiempo promedio de entrega (días)", promedio),
            ("Entregas completadas", len(tiempos)),
        ]
        + [(estados_sol[k], c_sol[k]) for k, _ in Solicitud.ESTADOS],
        "estados": Solicitud.ESTADOS + Entrega.ESTADOS,
    }


def reporte_beneficiarios(f):
    qs = _rango(PerfilBeneficiario.objects.select_related("usuario"), f, "usuario__usu_fec_reg")
    if f.get("estado"):
        qs = qs.filter(ben_estado_verif=f["estado"])
    estados = dict(PerfilBeneficiario.ESTADOS_VERIF)
    filas, conteo = [], Counter()
    for b in qs.order_by("usuario__usu_fec_reg"):
        u = b.usuario
        filas.append(
            [
                u.usu_id,
                u.nombre_completo,
                f"{b.ben_tipo_doc} {b.ben_num_doc}",
                b.sisben_texto,
                b.ben_estrato,
                b.ben_num_personas,
                "Sí" if b.ben_discapacidad else "No",
                estados[b.ben_estado_verif],
                _fecha(u.usu_fec_reg),
                _fecha(b.ben_fec_verif),
            ]
        )
        conteo[b.ben_estado_verif] += 1
    return {
        "titulo": TIPOS["beneficiarios"],
        "columnas": [
            "ID",
            "Nombre",
            "Documento",
            "Sisbén",
            "Estrato",
            "Personas",
            "Discapacidad",
            "Verificación",
            "Registro",
            "Fecha verif.",
        ],
        "filas": filas,
        "grafico": _grafico(
            "pie",
            OrderedDict((k, conteo[k]) for k, _ in PerfilBeneficiario.ESTADOS_VERIF),
            estados,
            "Beneficiarios por estado",
        ),
        "resumen": [("Beneficiarios", len(filas))] + [(n, conteo[k]) for k, n in PerfilBeneficiario.ESTADOS_VERIF],
        "estados": PerfilBeneficiario.ESTADOS_VERIF,
    }


def reporte_necesidad(f):
    grupos = parametros.grupos()
    nombres = {g["clave"]: g["nombre"] for g in grupos}
    qs = _rango(PerfilBeneficiario.objects.select_related("usuario"), f, "usuario__usu_fec_reg")
    if f.get("estado"):
        qs = qs.filter(ben_grupo=f["estado"])
    verif = dict(PerfilBeneficiario.ESTADOS_VERIF)
    filas, conteo, suma = [], Counter(), Counter()
    for b in qs.order_by("-ben_puntaje", "usuario__usu_nom"):
        u = b.usuario
        filas.append(
            [
                u.usu_id,
                u.nombre_completo,
                numero(b.ben_puntaje, 1),
                nombres.get(b.ben_grupo, "Sin grupo"),
                b.sisben_texto,
                b.ben_estrato,
                b.ben_num_personas,
                "Sí" if b.ben_discapacidad else "No",
                verif[b.ben_estado_verif],
                _fecha(b.ben_fec_puntaje),
            ]
        )
        conteo[b.ben_grupo] += 1
        suma[b.ben_grupo] += float(b.ben_puntaje or 0)
    grafico = _grafico(
        "bar",
        OrderedDict((g["clave"], conteo[g["clave"]]) for g in grupos),
        nombres,
        "Beneficiarios por grupo de necesidad",
    )
    grafico["colores"] = [g["color"] for g in grupos]
    return {
        "titulo": TIPOS["necesidad"],
        "columnas": [
            "ID",
            "Nombre",
            "Puntaje",
            "Grupo",
            "Sisbén",
            "Estrato",
            "Personas",
            "Discapacidad",
            "Verificación",
            "Calculado",
        ],
        "filas": filas,
        "grafico": grafico,
        "resumen": [("Beneficiarios", len(filas))]
        + [
            (
                f"{g['nombre']} (puntaje promedio {numero(suma[g['clave']] / conteo[g['clave']], 1) if conteo[g['clave']] else '—'})",
                conteo[g["clave"]],
            )
            for g in grupos
        ],
        "estados": [(g["clave"], g["nombre"]) for g in grupos],
    }


def generar(tipo, filtros):
    datos = GENERADORES[tipo](filtros)
    datos.setdefault("estados", Donacion.ESTADOS if tipo == "donaciones" else [])
    datos["tipo"] = tipo
    datos["generado"] = timezone.localtime().strftime("%d/%m/%Y %I:%M %p")
    return datos


def donantes_para_filtro():
    return Usuario.objects.filter(usu_rol=Usuario.DONANTE).select_related("perfil_donante").order_by("usu_nom")


# ---------------------------------------------------------------- Estadísticas nuevas (mejora 7)


def _horas(inicio, fin):
    return round((fin - inicio).total_seconds() / 3600, 1) if inicio and fin else None


def _promedio(valores):
    return round(sum(valores) / len(valores), 1) if valores else 0


def _mediana(valores):
    if not valores:
        return 0
    ordenados = sorted(valores)
    mitad = len(ordenados) // 2
    return ordenados[mitad] if len(ordenados) % 2 else round((ordenados[mitad - 1] + ordenados[mitad]) / 2, 1)


MODOS = [("auto", "Automática"), ("manual", "Manual")]


def _documentos_revisados(f):
    qs = DocumentoValidacion.objects.select_related("usuario").filter(
        docv_estado__in=[DocumentoValidacion.APROBADO, DocumentoValidacion.RECHAZADO],
        docv_fec_revision__isnull=False,
    )
    qs = _rango(qs, f, "docv_fec_revision")
    if f.get("estado") == "auto":
        qs = qs.filter(docv_verif_auto=True)
    elif f.get("estado") == "manual":
        qs = qs.filter(docv_verif_auto=False)
    return qs.order_by("docv_fec_revision")


def reporte_verificaciones(f):
    tipos, estados = dict(DocumentoValidacion.TIPOS), dict(DocumentoValidacion.ESTADOS)
    decisiones = dict(DocumentoValidacion.DECISIONES)
    filas, por_modo, por_resultado, por_decision = [], Counter(), Counter(), Counter()
    for d in _documentos_revisados(f):
        modo = "auto" if d.docv_verif_auto else "manual"
        filas.append(
            [
                d.docv_id,
                tipos.get(d.docv_tipo, d.docv_tipo),
                d.usuario.nombre_completo,
                estados[d.docv_estado],
                dict(MODOS)[modo],
                decisiones.get(d.docv_decision_auto, "—"),
                numero(d.docv_ocr_confianza, 1) if d.docv_ocr_confianza is not None else "—",
                _fecha(d.docv_fec_carga),
                _fecha(d.docv_fec_revision),
            ]
        )
        por_modo[modo] += 1
        por_resultado[f"{dict(MODOS)[modo]} · {estados[d.docv_estado].lower()}"] += 1
        if d.docv_decision_auto:
            por_decision[d.docv_decision_auto] += 1
    total = len(filas)
    porcentaje = round(100 * por_modo["auto"] / total, 1) if total else 0
    orden = [f"{m} · {e}" for _, m in MODOS for e in ("aprobado", "rechazado")]
    return {
        "titulo": TIPOS["verificaciones"],
        "columnas": [
            "N.º",
            "Documento",
            "Titular",
            "Resultado",
            "Verificación",
            "Semáforo OCR",
            "Confianza",
            "Cargado",
            "Revisado",
        ],
        "filas": filas,
        "grafico": _grafico(
            "doughnut",
            OrderedDict((k, por_modo[k]) for k, _ in MODOS),
            dict(MODOS),
            "Verificaciones automáticas y manuales",
        ),
        "grafico2": _grafico(
            "bar", OrderedDict((k, por_resultado[k]) for k in orden), titulo="Resultado según el tipo de verificación"
        ),
        "resumen": [
            ("Documentos revisados", total),
            ("Automáticas", por_modo["auto"]),
            ("Manuales", por_modo["manual"]),
            ("Porcentaje automático", f"{numero(porcentaje, 1)} %"),
        ]
        + [(f"Semáforo: {decisiones[k]}", por_decision[k]) for k, _ in DocumentoValidacion.DECISIONES],
        "estados": MODOS,
    }


def reporte_tiempo_verificacion(f):
    tipos = dict(DocumentoValidacion.TIPOS)
    filas, por_modo, por_tipo, por_mes = [], {"auto": [], "manual": []}, {}, {}
    for d in _documentos_revisados(f):
        horas = _horas(d.docv_fec_carga, d.docv_fec_revision)
        if horas is None:
            continue
        modo = "auto" if d.docv_verif_auto else "manual"
        filas.append(
            [
                d.docv_id,
                tipos.get(d.docv_tipo, d.docv_tipo),
                dict(MODOS)[modo],
                _fecha(d.docv_fec_carga),
                _fecha(d.docv_fec_revision),
                numero(horas, 1),
            ]
        )
        por_modo[modo].append(horas)
        por_tipo.setdefault(tipos.get(d.docv_tipo, d.docv_tipo), []).append(horas)
        por_mes.setdefault(timezone.localtime(d.docv_fec_revision).strftime("%Y-%m"), []).append(horas)
    todas = por_modo["auto"] + por_modo["manual"]
    return {
        "titulo": TIPOS["tiempo_verificacion"],
        "columnas": ["N.º", "Documento", "Verificación", "Cargado", "Revisado", "Horas"],
        "filas": filas,
        "grafico": _grafico(
            "bar",
            OrderedDict((t, _promedio(v)) for t, v in sorted(por_tipo.items())),
            titulo="Horas promedio por tipo de documento",
        ),
        "grafico2": _grafico(
            "line", OrderedDict((m, _promedio(v)) for m, v in sorted(por_mes.items())), titulo="Horas promedio por mes"
        ),
        "resumen": [
            ("Documentos revisados", len(todas)),
            ("Promedio general (horas)", numero(_promedio(todas), 1)),
            ("Mediana (horas)", numero(_mediana(todas), 1)),
            ("Promedio automáticas (horas)", numero(_promedio(por_modo["auto"]), 1)),
            ("Promedio manuales (horas)", numero(_promedio(por_modo["manual"]), 1)),
        ],
        "estados": MODOS,
    }


def reporte_zonas(f):
    """Beneficiarios ubicados por zona o barrio: la versión en tabla del mapa de calor."""
    grupos = parametros.grupos()
    qs = PerfilBeneficiario.objects.exclude(ben_zona="").annotate(
        n_sol=Count("usuario__solicitudes", distinct=True),
    )
    qs = _rango(qs, f, "usuario__usu_fec_reg")
    if f.get("estado"):
        qs = qs.filter(ben_grupo=f["estado"])
    zonas = {}
    for b in qs:
        z = zonas.setdefault(
            b.ben_zona, {"n": 0, "verificados": 0, "puntajes": [], "personas": 0, "solicitudes": 0, "criticos": 0}
        )
        z["n"] += 1
        z["verificados"] += b.ben_estado_verif == PerfilBeneficiario.VERIFICADO
        z["personas"] += b.ben_num_personas or 0
        z["solicitudes"] += b.n_sol
        if b.ben_puntaje is not None:
            z["puntajes"].append(float(b.ben_puntaje))
        if grupos and b.ben_grupo == grupos[0]["clave"]:
            z["criticos"] += 1
    ordenadas = sorted(zonas.items(), key=lambda kv: (-kv[1]["n"], kv[0]))
    filas = [
        [
            zona,
            z["n"],
            z["verificados"],
            z["personas"],
            numero(_promedio(z["puntajes"]), 1),
            z["criticos"],
            z["solicitudes"],
        ]
        for zona, z in ordenadas
    ]
    principales = ordenadas[:12]
    sin_ubicar = PerfilBeneficiario.objects.filter(ben_zona="").count()
    return {
        "titulo": TIPOS["zonas"],
        "columnas": [
            "Zona o barrio",
            "Beneficiarios",
            "Verificados",
            "Personas",
            "Puntaje promedio",
            f"En «{grupos[0]['nombre']}»" if grupos else "Prioridad máxima",
            "Solicitudes",
        ],
        "filas": filas,
        "grafico": _grafico(
            "bar", OrderedDict((z, d["n"]) for z, d in principales), titulo="Beneficiarios por zona (12 con más)"
        ),
        "grafico2": _grafico(
            "bar",
            OrderedDict((z, _promedio(d["puntajes"])) for z, d in principales),
            titulo="Puntaje de necesidad promedio por zona",
        ),
        "resumen": [
            ("Zonas con beneficiarios", len(filas)),
            ("Beneficiarios ubicados", sum(z["n"] for z in zonas.values())),
            ("Sin zona (pendientes de ubicar)", sin_ubicar),
        ],
        "estados": [(g["clave"], g["nombre"]) for g in grupos],
        "enlace": ("Ver en el mapa de calor", "reportes:mapa"),
    }


def reporte_chat(f):
    from asistente.models import ConsultaChat

    qs = _rango(ConsultaChat.objects.select_related("usuario"), f, "con_fecha")
    if f.get("estado"):
        qs = qs.filter(con_fuente=f["estado"])
    fuentes = dict(ConsultaChat.FUENTES)
    filas, por_fuente, por_dia, preguntas_sin = [], Counter(), Counter(), Counter()
    utiles = no_utiles = escaladas = 0
    for c in qs.order_by("con_fecha"):
        filas.append(
            [
                c.con_id,
                _fecha(c.con_fecha),
                c.get_con_canal_display(),
                (c.con_rol or "publico").capitalize(),
                c.con_pregunta,
                fuentes.get(c.con_fuente, c.con_fuente),
                {True: "Sí", False: "No"}.get(c.con_util, "—"),
                "Sí" if c.con_escalada else "No",
            ]
        )
        por_fuente[c.con_fuente] += 1
        por_dia[timezone.localtime(c.con_fecha).strftime("%Y-%m-%d")] += 1
        utiles += c.con_util is True
        no_utiles += c.con_util is False
        escaladas += c.con_escalada
        if c.con_fuente == ConsultaChat.SIN_RESPUESTA:
            preguntas_sin[c.con_pregunta.strip().lower()[:80]] += 1
    total = len(filas)
    respondidas = total - por_fuente[ConsultaChat.SIN_RESPUESTA] - por_fuente[ConsultaChat.LIMITE]
    resumen = [
        ("Consultas", total),
        ("Respondidas", f"{respondidas} ({numero(100 * respondidas / total, 1) if total else 0} %)"),
        ("Sin respuesta", por_fuente[ConsultaChat.SIN_RESPUESTA]),
        ("Enviadas al administrador", escaladas),
        ("Les sirvió / no les sirvió", f"{utiles} / {no_utiles}"),
    ]
    resumen += [(f"Sin respuesta frecuente: «{p}»", n) for p, n in preguntas_sin.most_common(3)]
    return {
        "titulo": TIPOS["chat"],
        "columnas": ["N.º", "Fecha", "Canal", "Rol", "Pregunta", "Cómo se respondió", "Útil", "Escalada"],
        "filas": filas,
        "grafico": _grafico(
            "doughnut",
            OrderedDict((k, por_fuente[k]) for k, _ in ConsultaChat.FUENTES if por_fuente[k]),
            fuentes,
            "Consultas según cómo se respondieron",
        ),
        "grafico2": _grafico("line", OrderedDict(sorted(por_dia.items())), titulo="Consultas por día"),
        "resumen": resumen,
        "estados": ConsultaChat.FUENTES,
    }


# ---------------------------------------------------------------- Registro único de estadísticas
#
# Cada estadística se declara una sola vez aquí: título, grupo, descripción, filtros que admite y su
# función. La página de reportes, las exportaciones (PDF, Excel, CSV), el catálogo de estadísticas y los
# envíos programados por correo se construyen a partir de este registro.

Estadistica = namedtuple("Estadistica", "clave titulo grupo descripcion filtros generador enlace")

FECHAS = ("desde", "hasta")
TODOS_LOS_FILTROS = FECHAS + ("estado", "categoria", "donante", "bodega")


def _e(clave, titulo, grupo, descripcion, filtros, generador, enlace=None):
    return Estadistica(clave, titulo, grupo, descripcion, tuple(filtros), generador, enlace)


ESTADISTICAS = OrderedDict(
    (e.clave, e)
    for e in [
        _e(
            "donaciones",
            "Donaciones por periodo y estado",
            "Donaciones e inventario",
            "Donaciones registradas, su estado y su evolución mes a mes. Las anónimas nunca muestran al donante.",
            TODOS_LOS_FILTROS,
            reporte_donaciones,
        ),
        _e(
            "inventario",
            "Inventario por vencimiento",
            "Donaciones e inventario",
            "Existencias vigentes, próximas a vencer y vencidas, con cantidades según su unidad.",
            TODOS_LOS_FILTROS,
            reporte_inventario,
        ),
        _e(
            "vencidos",
            "Productos vencidos y retirados",
            "Donaciones e inventario",
            "Productos dados de baja o pendientes de retiro, con el motivo.",
            FECHAS + ("categoria", "donante", "bodega"),
            reporte_vencidos,
        ),
        _e(
            "solicitudes",
            "Solicitudes y entregas por estado",
            "Solicitudes y entregas",
            "Solicitudes, entregas generadas y tiempo promedio desde la solicitud hasta la entrega.",
            TODOS_LOS_FILTROS,
            reporte_solicitudes,
        ),
        _e(
            "beneficiarios",
            "Beneficiarios por estado de verificación",
            "Beneficiarios",
            "Beneficiarios registrados según su estado de verificación.",
            FECHAS + ("estado",),
            reporte_beneficiarios,
        ),
        _e(
            "necesidad",
            "Beneficiarios por grupo de necesidad",
            "Beneficiarios",
            "Distribución por grupo de prioridad según el puntaje automático, con el puntaje promedio de cada grupo.",
            FECHAS + ("estado",),
            reporte_necesidad,
        ),
        _e(
            "zonas",
            "Beneficiarios por zona",
            "Beneficiarios",
            "Beneficiarios ubicados en cada zona o barrio con su puntaje promedio: la versión en tabla del mapa de calor.",
            FECHAS + ("estado",),
            reporte_zonas,
            ("Mapa de calor", "reportes:mapa"),
        ),
        _e(
            "verificaciones",
            "Verificaciones automáticas y manuales",
            "Verificación de documentos",
            "Documentos aprobados o rechazados por el sistema (OCR) frente a los que revisó el administrador, y su semáforo.",
            FECHAS + ("estado",),
            reporte_verificaciones,
        ),
        _e(
            "tiempo_verificacion",
            "Tiempo promedio de verificación",
            "Verificación de documentos",
            "Horas entre la carga de un documento y su aprobación o rechazo, por tipo, por mes y según el tipo de verificación.",
            FECHAS + ("estado",),
            reporte_tiempo_verificacion,
        ),
        _e(
            "chat",
            "Consultas del asistente de ayuda",
            "Asistente de ayuda",
            "Preguntas al chat, cómo se respondieron, cuáles quedaron sin respuesta y cuáles se enviaron al administrador.",
            FECHAS + ("estado",),
            reporte_chat,
        ),
    ]
)

TIPOS = OrderedDict((clave, e.titulo) for clave, e in ESTADISTICAS.items())
GENERADORES = {clave: e.generador for clave, e in ESTADISTICAS.items()}


NOMBRES_FILTRO = {
    "desde": "fechas",
    "estado": "estado o grupo",
    "categoria": "categoría",
    "donante": "donante",
    "bodega": "bodega",
}


def filtros_texto(estadistica):
    return ", ".join(NOMBRES_FILTRO[f] for f in estadistica.filtros if f in NOMBRES_FILTRO).capitalize()


def por_grupo():
    grupos = OrderedDict()
    for e in ESTADISTICAS.values():
        grupos.setdefault(e.grupo, []).append(e)
    return grupos


# Indicadores de los paneles (no exportables): se listan en el catálogo para tener el inventario completo.
EN_PANELES = [
    (
        "Panel del administrador",
        "Usuarios por rol y estado; donaciones y entregas por estado (gráficos); inventario disponible, "
        "próximo a vencer, vencido y reservado; documentos y solicitudes pendientes; mapa de calor.",
    ),
    (
        "Panel del donante",
        "Sus donaciones por estado (gráfico) y cantidades donadas, entregadas y disponibles por unidad.",
    ),
    ("Panel del beneficiario", "Sus solicitudes por estado y sus entregas recientes."),
    ("Inventario", "Disponibles, próximos a vencer, vencidos por retirar, con reservas y cantidades por revisar."),
    ("Consultas del asistente", "Consultas de 30 días, sin respuesta, enviadas al administrador y calificación."),
]
