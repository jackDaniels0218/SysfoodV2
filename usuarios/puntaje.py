"""Puntaje automático de necesidad de los beneficiarios (0 a 100) y su grupo.

Algoritmo transparente: suma ponderada de criterios.

    puntaje = Σ (peso_i × valor_i) / Σ peso_i

donde cada valor_i está en una escala de 0 a 100 y los pesos se configuran en
Sistema › Parámetros. Los puntos que aporta cada criterio son
peso_i × valor_i / Σ peso_i, de modo que el desglose suma exactamente el puntaje.

El puntaje apoya la decisión del administrador; no la reemplaza.
"""
from collections import OrderedDict
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from core import parametros
from core.formato import numero
from core.servicios import auditar

CRITERIOS = OrderedDict([
    ("sisben", ("Nivel de Sisbén", "puntaje_peso_sisben")),
    ("estrato", ("Estrato social", "puntaje_peso_estrato")),
    ("personas", ("Personas en el hogar", "puntaje_peso_personas")),
    ("discapacidad", ("Discapacidad", "puntaje_peso_discapacidad")),
    ("solicitudes", ("Solicitudes recientes", "puntaje_peso_solicitudes")),
    ("tiempo", ("Tiempo sin recibir ayuda", "puntaje_peso_tiempo")),
])

NOMBRES_SISBEN = {"A": "A (pobreza extrema)", "B": "B (pobreza moderada)", "C": "C (vulnerable)", "D": "D (no pobre)", "NR": "No registrado"}


class Config:
    """Parámetros del puntaje leídos una sola vez (para recalcular por lotes)."""

    def __init__(self, valores=None):
        v = valores if valores is not None else parametros.todos()
        self.pesos = OrderedDict((c, parametros.entero(clave, v)) for c, (_, clave) in CRITERIOS.items())
        self.escala_sisben = parametros.escala("puntaje_escala_sisben", v)
        self.escala_estrato = parametros.escala("puntaje_escala_estrato", v)
        self.personas_tope = parametros.entero("puntaje_personas_tope", v)
        self.discapacidad_sin_soporte = parametros.entero("puntaje_discapacidad_sin_soporte", v)
        self.dias_solicitudes = parametros.entero("puntaje_dias_solicitudes", v)
        self.solicitudes_tope = parametros.entero("puntaje_solicitudes_tope", v)
        self.dias_sin_ayuda_tope = parametros.entero("puntaje_dias_sin_ayuda_tope", v)
        self.grupos = parametros.grupos("grupos_necesidad", v)

    @property
    def suma_pesos(self):
        return sum(self.pesos.values())


def _redondear(valor, decimales="0.01"):
    return Decimal(str(valor)).quantize(Decimal(decimales), rounding=ROUND_HALF_UP)


def _proporcion(n, tope):
    return min(max(n, 0), tope) / tope * 100 if tope else 0


# ---------------------------------------------------------------- Datos de entrada

def datos_de(perfil, hoy=None, cfg=None):
    """Toma del sistema los datos que usa el puntaje (solo del propio beneficiario)."""
    from entregas.models import Entrega
    from solicitudes.models import Solicitud

    from .models import DocumentoValidacion

    cfg = cfg or Config()
    hoy = hoy or timezone.localdate()
    usuario_id = perfil.usuario_id
    desde = timezone.now() - timedelta(days=cfg.dias_solicitudes)
    solicitudes = (
        Solicitud.objects.filter(beneficiario_id=usuario_id, sol_fec_envio__gte=desde)
        .exclude(sol_estado=Solicitud.CANCELADA).count()
    )
    ultima = (
        Entrega.objects.filter(solicitud__beneficiario_id=usuario_id, ent_estado=Entrega.ENTREGADO, ent_fec_entrega__isnull=False)
        .order_by("-ent_fec_entrega").values_list("ent_fec_entrega", flat=True).first()
    )
    soporte = perfil.ben_discapacidad and DocumentoValidacion.objects.filter(
        usuario_id=usuario_id, docv_tipo=DocumentoValidacion.DISCAPACIDAD, docv_estado=DocumentoValidacion.APROBADO,
    ).exists()
    return {
        "sisben": perfil.ben_sisben,
        "estrato": perfil.ben_estrato,
        "personas": perfil.ben_num_personas,
        "discapacidad": bool(perfil.ben_discapacidad),
        "soporte_discapacidad": bool(soporte),
        "solicitudes_recientes": solicitudes,
        "dias_sin_ayuda": (hoy - timezone.localdate(ultima)).days if ultima else None,
    }


# ---------------------------------------------------------------- Cálculo (función pura)

def calcular(datos, cfg):
    """Devuelve (puntaje, desglose). No consulta la base de datos: se puede usar en ejemplos y pruebas."""
    valores = OrderedDict()
    sisben = datos["sisben"]
    valores["sisben"] = (cfg.escala_sisben.get(str(sisben).upper(), 0), f"Sisbén {NOMBRES_SISBEN.get(sisben, sisben)}")
    estrato = str(datos["estrato"])
    valores["estrato"] = (cfg.escala_estrato.get(estrato, 0), f"Estrato {estrato}")
    personas = datos["personas"] or 0
    valores["personas"] = (_proporcion(personas, cfg.personas_tope), f"{personas} persona{'s' if personas != 1 else ''} (100 desde {cfg.personas_tope})")
    if not datos["discapacidad"]:
        valores["discapacidad"] = (0, "No declara discapacidad")
    elif datos["soporte_discapacidad"]:
        valores["discapacidad"] = (100, "Sí, con certificado aprobado")
    else:
        valores["discapacidad"] = (cfg.discapacidad_sin_soporte, "Sí, certificado aún no aprobado")
    n = datos["solicitudes_recientes"]
    valores["solicitudes"] = (
        _proporcion(n, cfg.solicitudes_tope),
        f"{n} solicitud{'es' if n != 1 else ''} en los últimos {cfg.dias_solicitudes} días (100 desde {cfg.solicitudes_tope})",
    )
    dias = datos["dias_sin_ayuda"]
    if dias is None:
        valores["tiempo"] = (100, "Nunca ha recibido una entrega")
    else:
        valores["tiempo"] = (_proporcion(dias, cfg.dias_sin_ayuda_tope), f"{dias} día{'s' if dias != 1 else ''} desde la última entrega (100 desde {cfg.dias_sin_ayuda_tope})")

    suma = cfg.suma_pesos
    desglose, total = [], Decimal("0")
    for clave, (nombre, _) in CRITERIOS.items():
        escala, texto = valores[clave]
        peso = cfg.pesos[clave]
        puntos = _redondear(peso * escala / suma) if suma else Decimal("0")
        maximo = _redondear(peso * 100 / suma) if suma else Decimal("0")
        total += puntos
        desglose.append({
            "clave": clave, "nombre": nombre, "valor": texto, "escala": float(_redondear(escala, "0.1")),
            "peso": peso, "puntos": float(puntos), "maximo": float(maximo),
        })
    return min(total, Decimal("100.00")), desglose


def grupo_para(puntaje, grupos):
    for grupo in grupos:  # Ordenados de mayor a menor mínimo.
        if float(puntaje) >= grupo["minimo"]:
            return grupo
    return grupos[-1]


def grupo_por_clave(clave, grupos=None):
    grupos = grupos if grupos is not None else parametros.grupos()
    return next((g for g in grupos if g["clave"] == clave), None)


def texto_desglose(desglose):
    return "; ".join(f"{d['nombre']}: {numero(d['puntos'])}/{numero(d['maximo'])} ({d['valor']})" for d in desglose)


# ---------------------------------------------------------------- Persistencia y auditoría

def recalcular(perfil, motivo, cfg=None, usuario=None, request=None, hoy=None):
    """Calcula, guarda y audita el puntaje y el grupo. Devuelve (cambio_puntaje, cambio_grupo)."""
    from .models import PerfilBeneficiario

    cfg = cfg or Config()
    puntaje, desglose = calcular(datos_de(perfil, hoy, cfg), cfg)
    grupo = grupo_para(puntaje, cfg.grupos)
    anterior = PerfilBeneficiario.objects.filter(pk=perfil.pk).values("ben_puntaje", "ben_grupo").first() or {}
    puntaje_ant, grupo_ant = anterior.get("ben_puntaje"), anterior.get("ben_grupo") or ""
    ahora = timezone.now()
    PerfilBeneficiario.objects.filter(pk=perfil.pk).update(
        ben_puntaje=puntaje, ben_grupo=grupo["clave"], ben_puntaje_detalle=desglose, ben_fec_puntaje=ahora,
    )
    perfil.ben_puntaje, perfil.ben_grupo, perfil.ben_puntaje_detalle, perfil.ben_fec_puntaje = puntaje, grupo["clave"], desglose, ahora
    cambio_puntaje = puntaje_ant is None or _redondear(puntaje_ant) != puntaje
    cambio_grupo = grupo_ant != grupo["clave"]
    if cambio_puntaje:
        previo = "sin puntaje" if puntaje_ant is None else numero(puntaje_ant)
        auditar(request, "calculo_puntaje", "beneficiario", perfil.pk,
                f"Puntaje {previo} → {numero(puntaje)}. Motivo: {motivo}. Desglose: {texto_desglose(desglose)}"[:4000], usuario=usuario)
    if cambio_grupo:
        nombre_ant = (grupo_por_clave(grupo_ant, cfg.grupos) or {}).get("nombre", grupo_ant or "sin grupo")
        auditar(request, "clasificacion", "beneficiario", perfil.pk,
                f"Grupo «{nombre_ant}» → «{grupo['nombre']}» (puntaje {numero(puntaje)}, mínimo del grupo {numero(grupo['minimo'])}). Motivo: {motivo}.",
                usuario=usuario)
    return cambio_puntaje, cambio_grupo


def recalcular_usuario(usuario_id, motivo, request=None):
    from .models import PerfilBeneficiario

    perfil = PerfilBeneficiario.objects.filter(pk=usuario_id).first()
    if perfil is not None:
        recalcular(perfil, motivo, request=request)
    return perfil


def recalcular_todos(motivo, usuario=None):
    from .models import PerfilBeneficiario

    cfg = Config()
    resumen = {"recalculados": 0, "puntajes_cambiados": 0, "grupos_cambiados": 0}
    for perfil in PerfilBeneficiario.objects.all().iterator():
        with transaction.atomic():
            cambio_puntaje, cambio_grupo = recalcular(perfil, motivo, cfg, usuario=usuario)
        resumen["recalculados"] += 1
        resumen["puntajes_cambiados"] += int(cambio_puntaje)
        resumen["grupos_cambiados"] += int(cambio_grupo)
    return resumen


def tarea_recalculo_nocturno():
    return recalcular_todos("Recálculo nocturno programado")


@parametros.al_cambiar("puntaje_")
@parametros.al_cambiar("grupos_necesidad")
def _al_cambiar_parametro(clave, usuario):
    r = recalcular_todos(f"Cambio del parámetro {clave}", usuario=usuario)
    return (f"Se recalculó el puntaje de {r['recalculados']} beneficiario(s): {r['puntajes_cambiados']} cambiaron de puntaje "
            f"y {r['grupos_cambiados']} de grupo.")


# ---------------------------------------------------------------- Ejemplos para la ayuda

EJEMPLOS = [
    ("Hogar numeroso en pobreza extrema que nunca ha recibido ayuda",
     {"sisben": "A", "estrato": 1, "personas": 6, "discapacidad": True, "soporte_discapacidad": True,
      "solicitudes_recientes": 1, "dias_sin_ayuda": None}),
    ("Familia vulnerable que recibió una entrega hace 20 días",
     {"sisben": "C", "estrato": 2, "personas": 4, "discapacidad": False, "soporte_discapacidad": False,
      "solicitudes_recientes": 2, "dias_sin_ayuda": 20}),
    ("Persona sola de estrato 3 atendida hace 5 días",
     {"sisben": "D", "estrato": 3, "personas": 1, "discapacidad": False, "soporte_discapacidad": False,
      "solicitudes_recientes": 3, "dias_sin_ayuda": 5}),
]


def ejemplos(cfg=None):
    cfg = cfg or Config()
    resultado = []
    for titulo, datos in EJEMPLOS:
        puntaje, desglose = calcular(datos, cfg)
        resultado.append({"titulo": titulo, "puntaje": puntaje, "desglose": desglose, "grupo": grupo_para(puntaje, cfg.grupos)})
    return resultado
