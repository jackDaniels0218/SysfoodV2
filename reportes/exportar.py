"""Exportación de reportes a PDF (ReportLab) y Excel (openpyxl), con gráficos."""
import io

from openpyxl import Workbook
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

VERDE = colors.HexColor("#1f7a4d")
PALETA = ["#1f7a4d", "#2f6fb0", "#d08a1e", "#b23b3b", "#6b5ca5", "#3c8d8d", "#8a8a8a"]


def _dibujo_grafico(grafico, ancho=24 * cm, alto=7 * cm):
    etiquetas, datos = grafico["etiquetas"], grafico["datos"]
    d = Drawing(ancho, alto)
    d.add(String(0, alto - 12, grafico.get("titulo", ""), fontSize=10, fillColor=colors.black))
    if not datos or not any(datos):
        d.add(String(0, alto / 2, "Sin datos para graficar", fontSize=9, fillColor=colors.grey))
        return d
    if grafico["tipo"] in ("pie", "doughnut"):
        pie = Pie()
        pie.x, pie.y, pie.width, pie.height = 30, 10, alto - 40, alto - 40
        pie.data = [max(v, 0) for v in datos]
        pie.labels = [f"{e} ({v})" for e, v in zip(etiquetas, datos)]
        pie.sideLabels = True
        for i in range(len(datos)):
            pie.slices[i].fillColor = colors.HexColor(PALETA[i % len(PALETA)])
        d.add(pie)
    else:
        barras = VerticalBarChart()
        barras.x, barras.y, barras.width, barras.height = 40, 30, ancho - 80, alto - 60
        barras.data = [datos]
        barras.categoryAxis.categoryNames = [str(e)[:18] for e in etiquetas]
        barras.categoryAxis.labels.fontSize = 7
        barras.valueAxis.valueMin = 0
        barras.valueAxis.labels.fontSize = 7
        barras.bars[0].fillColor = VERDE
        barras.barLabelFormat = "%d"
        barras.barLabels.fontSize = 7
        barras.barLabels.nudge = 6
        d.add(barras)
    return d


def a_pdf(datos, filtros_texto=""):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=1.2 * cm, rightMargin=1.2 * cm,
                            topMargin=1.2 * cm, bottomMargin=1.2 * cm, title=datos["titulo"], author="SysFood V2")
    estilos = getSampleStyleSheet()
    celda = estilos["BodyText"].clone("celda", fontSize=7.5, leading=9)
    partes = [
        Paragraph(f"<font color='#1f7a4d'><b>SysFood V2</b></font> — {datos['titulo']}", estilos["Title"]),
        Paragraph(f"Generado: {datos['generado']}. {filtros_texto}", estilos["Normal"]),
        Spacer(1, 8),
    ]
    resumen = Table([[str(a), str(b)] for a, b in datos["resumen"]], hAlign="LEFT")
    resumen.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                                 ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef6f1"))]))
    partes += [resumen, Spacer(1, 8), _dibujo_grafico(datos["grafico"])]
    if datos.get("grafico2"):
        partes += [Spacer(1, 4), _dibujo_grafico(datos["grafico2"])]
    partes.append(Spacer(1, 10))
    encabezado = celda.clone("encabezado", textColor=colors.white)
    filas = [[Paragraph(f"<b>{c}</b>", encabezado) for c in datos["columnas"]]]
    filas += [[Paragraph(str(v), celda) for v in fila] for fila in datos["filas"]] or [[Paragraph("Sin registros para los filtros seleccionados.", celda)] + [""] * (len(datos["columnas"]) - 1)]
    tabla = Table(filas, repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VERDE), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8f7")]),
    ]))
    partes.append(tabla)
    doc.build(partes)
    return buffer.getvalue()


def a_excel(datos, filtros_texto=""):
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Reporte"
    hoja["A1"] = f"SysFood V2 — {datos['titulo']}"
    hoja["A1"].font = Font(bold=True, size=14, color="1F7A4D")
    hoja["A2"] = f"Generado: {datos['generado']}. {filtros_texto}"
    fila = 4
    encabezado = PatternFill("solid", fgColor="1F7A4D")
    for col, nombre in enumerate(datos["columnas"], start=1):
        celda = hoja.cell(row=fila, column=col, value=nombre)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = encabezado
        celda.alignment = Alignment(vertical="center")
    for registro in datos["filas"]:
        fila += 1
        for col, valor in enumerate(registro, start=1):
            hoja.cell(row=fila, column=col, value=valor)
    for col in range(1, len(datos["columnas"]) + 1):
        largo = max([len(str(datos["columnas"][col - 1]))] + [len(str(r[col - 1])) for r in datos["filas"][:500]])
        hoja.column_dimensions[get_column_letter(col)].width = min(max(10, largo + 2), 45)
    hoja.freeze_panes = "A5"

    resumen = libro.create_sheet("Resumen")
    resumen.append(["Indicador", "Valor"])
    for a, b in datos["resumen"]:
        resumen.append([str(a), b])
    resumen["A1"].font = resumen["B1"].font = Font(bold=True)
    resumen.column_dimensions["A"].width = 40

    for n, clave in enumerate(("grafico", "grafico2"), start=1):
        g = datos.get(clave)
        if not g:
            continue
        hoja_g = libro.create_sheet(f"Gráfico {n}")
        hoja_g.append(["Categoría", "Cantidad"])
        for etiqueta, valor in zip(g["etiquetas"], g["datos"]):
            hoja_g.append([str(etiqueta), valor])
        total = len(g["datos"]) + 1
        grafico = PieChart() if g["tipo"] in ("pie", "doughnut") else BarChart()
        grafico.title = g.get("titulo") or datos["titulo"]
        grafico.add_data(Reference(hoja_g, min_col=2, min_row=1, max_row=total), titles_from_data=True)
        grafico.set_categories(Reference(hoja_g, min_col=1, min_row=2, max_row=total))
        grafico.height, grafico.width = 9, 18
        hoja_g.add_chart(grafico, "D2")
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()
