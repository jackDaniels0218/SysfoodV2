from django.core.management.base import BaseCommand, CommandError

from core import tareas


class Command(BaseCommand):
    help = (
        "Ejecuta las tareas automáticas que estén pendientes (vencimientos, puntajes, geocodificación, OCR, "
        "reportes programados). Prográmelo cada hora con cron o el Programador de tareas de Windows."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tarea", help="Ejecuta solo esta tarea: " + ", ".join(tareas.REGISTRO))
        parser.add_argument("--forzar", action="store_true", help="Ejecuta aunque ya haya corrido en este periodo.")
        parser.add_argument("--listar", action="store_true", help="Muestra las tareas y su última ejecución.")

    def handle(self, *args, **op):
        if op["listar"]:
            for fila in tareas.estado():
                self.stdout.write(f"{fila['tarea'].nombre:28} {fila['tarea'].frecuencia:8} {fila['ultima'] or 'nunca'}  {fila['resultado']}")
            return
        if op["tarea"]:
            if op["tarea"] not in tareas.REGISTRO:
                raise CommandError("Tarea desconocida. Opciones: " + ", ".join(tareas.REGISTRO))
            resultado = tareas.ejecutar(op["tarea"], forzar=op["forzar"])
            self.stdout.write(self.style.SUCCESS(f"{op['tarea']}: {tareas._resumen(resultado) if resultado is not None else 'no correspondía ejecutarla'}"))
            return
        if op["forzar"]:
            resultados = {n: tareas.ejecutar(n, forzar=True) for n in tareas.REGISTRO}
        else:
            resultados = tareas.ejecutar_pendientes()
        if not resultados:
            self.stdout.write("No había tareas pendientes.")
        for nombre, resultado in resultados.items():
            self.stdout.write(self.style.SUCCESS(f"{nombre}: {tareas._resumen(resultado)}"))
