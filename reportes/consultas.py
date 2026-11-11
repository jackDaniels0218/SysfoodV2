"""Consultas de los reportes del administrador (Actividad 15).

Cada reporte devuelve un diccionario con: titulo, columnas, filas, grafico y resumen.
Las donaciones anónimas nunca muestran la identidad del donante en los reportes.
"""
from collections import Counter, OrderedDict

from django.db.models import Count, Q
from django.utils import timezone

from core import parametros
from core.fechas import filtrar_rango, inicio_dia, inicio_dia_siguiente
from core.formato import numero
from donaciones.models import ANONIMO, Donacion
from entregas.models import Entrega
from inventario.models import Inventario
from solicitudes.models import Solicitud
from usuarios.models import PerfilBeneficiario, Usuario

TIPOS = OrderedDict([
    ("donaciones", "Donaciones por periodo y estado"),
    ("inventario", "Inventario por vencimiento"),
    ("vencidos", "Productos vencidos y retirados"),
    ("solicitudes", "Solicitudes y entregas por estado"),
    ("beneficiarios", "Beneficiarios por estado de verificación"),
    ("necesidad", "Beneficiarios por grupo de necesidad"),
])


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
        filas.append([d.dona_id, _fecha(d.dona_fec_reg), nombre_donante_reporte(d), d.get_dona_estado_display(), d.n, "Sí" if d.dona_anonima else "No"])
        por_estado[d.dona_estado] += 1
        por_mes[timezone.localtime(d.dona_fec_reg).strftime("%Y-%m")] += 1
    return {
        "titulo": TIPOS["donaciones"],
        "columnas": ["N.º", "Fecha", "Donante", "Estado", "Productos", "Anónima"],
        "filas": filas,
        "grafico": _grafico("bar", OrderedDict((k, por_estado[k]) for k, _ in Donacion.ESTADOS), dict(Donacion.ESTADOS), "Donaciones por estado"),
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
        filas.append([i.inv_id, i.inv_nom, i.categoria.cat_nom, i.bodega.bod_nom, i.cantidad_texto(i.inv_cant_disp),
                      i.cantidad_texto(i.inv_cant_reserv), i.inv_fec_venc.strftime("%d/%m/%Y"), i.dias_para_vencer, vigencias[i.inv_est_venc]])
        conteo[i.inv_est_venc] += 1
    return {
        "titulo": TIPOS["inventario"],
        "columnas": ["ID", "Producto", "Categoría", "Bodega", "Disponible", "Reservado", "Vence", "Días", "Vigencia"],
        "filas": filas,
        "grafico": _grafico("doughnut", OrderedDict((k, conteo[k]) for k, _ in Inventario.VIGENCIAS), vigencias, "Inventario por vigencia"),
        "resumen": [("Productos en inventario", len(filas))] + [(n, conteo[k]) for k, n in Inventario.VIGENCIAS],
        "estados": Inventario.VIGENCIAS,
    }


def reporte_vencidos(f):
    qs = Inventario.objects.filter(Q(inv_est_venc=Inventario.VENCIDO) | Q(inv_estado=Inventario.RETIRADO)).select_related("categoria", "bodega", "usuario_baja")
    qs = _filtrar_inventario(qs, f)
    if f.get("desde"):
        qs = qs.filter(Q(inv_fec_venc__gte=f["desde"]) | Q(inv_fec_baja__gte=inicio_dia(f["desde"])))
    if f.get("hasta"):
        qs = qs.filter(Q(inv_fec_venc__lte=f["hasta"]) | Q(inv_fec_baja__lt=inicio_dia_siguiente(f["hasta"])))
    if f.get("estado"):
        qs = qs.filter(inv_mot_baja=f["estado"]) if f["estado"] != "pendiente" else qs.exclude(inv_estado=Inventario.RETIRADO)
    motivos = dict(Inventario.MOTIVOS_BAJA)
    filas, conteo = [], Counter()
    for i in qs.order_by("inv_fec_venc"):
        motivo = motivos.get(i.inv_mot_baja, "Pendiente de retiro")
        cantidad = i.inv_cant_inicial if i.inv_estado == Inventario.RETIRADO else i.inv_cant_disp
        filas.append([i.inv_id, i.inv_nom, i.categoria.cat_nom, i.bodega.bod_nom, i.cantidad_texto(cantidad),
                      i.inv_fec_venc.strftime("%d/%m/%Y"), motivo, _fecha(i.inv_fec_baja), i.usuario_baja.nombre_completo if i.usuario_baja else ""])
        conteo[motivo] += 1
    return {
        "titulo": TIPOS["vencidos"],
        "columnas": ["ID", "Producto", "Categoría", "Bodega", "Cantidad", "Vence", "Motivo", "Fecha de baja", "Retirado por"],
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
        filas.append([s.sol_id, _fecha(s.sol_fec_envio), s.beneficiario.nombre_completo, estados_sol[s.sol_estado],
                      e.ent_cod if e else "", estados_ent[e.ent_estado] if e else "", _fecha(e.ent_fec_entrega) if e else "", dias])
        c_sol[s.sol_estado] += 1
        if e:
            c_ent[e.ent_estado] += 1
    promedio = round(sum(tiempos) / len(tiempos), 1) if tiempos else 0
    return {
        "titulo": TIPOS["solicitudes"],
        "columnas": ["N.º", "Enviada", "Beneficiario", "Solicitud", "Entrega", "Estado entrega", "Entregada", "Días"],
        "filas": filas,
        "grafico": _grafico("bar", OrderedDict((k, c_sol[k]) for k, _ in Solicitud.ESTADOS), estados_sol, "Solicitudes por estado"),
        "grafico2": _grafico("bar", OrderedDict((k, c_ent[k]) for k, _ in Entrega.ESTADOS), estados_ent, "Entregas por estado"),
        "resumen": [("Solicitudes", len(filas)), ("Tiempo promedio de entrega (días)", promedio),
                    ("Entregas completadas", len(tiempos))] + [(estados_sol[k], c_sol[k]) for k, _ in Solicitud.ESTADOS],
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
        filas.append([u.usu_id, u.nombre_completo, f"{b.ben_tipo_doc} {b.ben_num_doc}", b.get_ben_sisben_display(), b.ben_estrato,
                      b.ben_num_personas, "Sí" if b.ben_discapacidad else "No", estados[b.ben_estado_verif], _fecha(u.usu_fec_reg), _fecha(b.ben_fec_verif)])
        conteo[b.ben_estado_verif] += 1
    return {
        "titulo": TIPOS["beneficiarios"],
        "columnas": ["ID", "Nombre", "Documento", "Sisbén", "Estrato", "Personas", "Discapacidad", "Verificación", "Registro", "Fecha verif."],
        "filas": filas,
        "grafico": _grafico("pie", OrderedDict((k, conteo[k]) for k, _ in PerfilBeneficiario.ESTADOS_VERIF), estados, "Beneficiarios por estado"),
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
        filas.append([u.usu_id, u.nombre_completo, numero(b.ben_puntaje, 1), nombres.get(b.ben_grupo, "Sin grupo"), b.get_ben_sisben_display(),
                      b.ben_estrato, b.ben_num_personas, "Sí" if b.ben_discapacidad else "No", verif[b.ben_estado_verif], _fecha(b.ben_fec_puntaje)])
        conteo[b.ben_grupo] += 1
        suma[b.ben_grupo] += float(b.ben_puntaje or 0)
    grafico = _grafico("bar", OrderedDict((g["clave"], conteo[g["clave"]]) for g in grupos), nombres, "Beneficiarios por grupo de necesidad")
    grafico["colores"] = [g["color"] for g in grupos]
    return {
        "titulo": TIPOS["necesidad"],
        "columnas": ["ID", "Nombre", "Puntaje", "Grupo", "Sisbén", "Estrato", "Personas", "Discapacidad", "Verificación", "Calculado"],
        "filas": filas,
        "grafico": grafico,
        "resumen": [("Beneficiarios", len(filas))] + [
            (f"{g['nombre']} (puntaje promedio {numero(suma[g['clave']] / conteo[g['clave']], 1) if conteo[g['clave']] else '—'})", conteo[g["clave"]])
            for g in grupos
        ],
        "estados": [(g["clave"], g["nombre"]) for g in grupos],
    }


GENERADORES = {
    "donaciones": reporte_donaciones,
    "inventario": reporte_inventario,
    "vencidos": reporte_vencidos,
    "solicitudes": reporte_solicitudes,
    "beneficiarios": reporte_beneficiarios,
    "necesidad": reporte_necesidad,
}


def generar(tipo, filtros):
    datos = GENERADORES[tipo](filtros)
    datos.setdefault("estados", Donacion.ESTADOS if tipo == "donaciones" else [])
    datos["tipo"] = tipo
    datos["generado"] = timezone.localtime().strftime("%d/%m/%Y %I:%M %p")
    return datos


def donantes_para_filtro():
    return Usuario.objects.filter(usu_rol=Usuario.DONANTE).select_related("perfil_donante").order_by("usu_nom")
