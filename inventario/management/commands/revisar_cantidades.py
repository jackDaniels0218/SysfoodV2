"""Informe de cantidades no conformes: decimales en unidades contables (latas, cajas, unidades…).

Uso: python manage.py revisar_cantidades
Los registros listados vienen de antes de la regla (la migración los conservó para no perder datos).
Corríjalos con un ajuste de inventario a un número entero. El panel de inventario muestra el mismo conteo.
"""
from django.core.management.base import BaseCommand

from core import formato
from inventario import unidades


class Command(BaseCommand):
    help = "Lista los registros con decimales en unidades que se cuentan en enteros."

    def handle(self, *args, **opciones):
        total = 0
        for tabla, registros in unidades.no_conformes().items():
            if not registros:
                continue
            self.stdout.write(self.style.WARNING(f"{tabla}: {len(registros)}"))
            for r in registros:
                self.stdout.write(f"  - {self._describir(r)}")
            total += len(registros)
        if total:
            self.stdout.write(self.style.WARNING(f"Total: {total} registro(s) por corregir."))
        else:
            self.stdout.write(self.style.SUCCESS("Todas las cantidades son coherentes con su unidad."))

    def _describir(self, r):
        nombre = type(r).__name__
        if nombre == "Inventario":
            return f"Inventario #{r.pk} «{r.inv_nom}»: disponible {formato.numero(r.inv_cant_disp)} {r.inv_unidad}"
        if nombre == "DetalleDonacion":
            return f"Donación #{r.donacion_id}, producto «{r.dd_nom}»: {formato.numero(r.dd_cantidad)} {r.dd_unidad}"
        if nombre == "CarritoItem":
            return f"Carrito de usuario #{r.beneficiario_id}: {formato.numero(r.car_cant)} {r.inventario.inv_unidad} de «{r.inventario.inv_nom}»"
        if nombre == "SolicitudDetalle":
            return f"Solicitud #{r.solicitud_id}: {formato.numero(r.sd_cant)} {r.inventario.inv_unidad} de «{r.inventario.inv_nom}»"
        return f"Entrega #{r.entrega_id}: {formato.numero(r.de_cant_asig)} {r.inventario.inv_unidad} de «{r.inventario.inv_nom}»"
