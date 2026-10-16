from django.core.management.base import BaseCommand

from core.tareas import ejecutar_control_diario


class Command(BaseCommand):
    help = "Ejecuta el control diario de vencimientos (inventario y documentos). Prográmelo una vez al día."

    def handle(self, *args, **opciones):
        resultado = ejecutar_control_diario(forzar=True)
        self.stdout.write(self.style.SUCCESS(
            f"Control ejecutado: {resultado['proximos']} próximos a vencer, {resultado['vencidos']} vencidos, "
            f"{resultado['documentos_vencidos']} documentos vencidos."
        ))
