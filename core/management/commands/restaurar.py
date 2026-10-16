import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Restaura un respaldo generado con 'respaldo'. REEMPLAZA todos los datos actuales."

    def add_arguments(self, parser):
        parser.add_argument("archivo", help="Archivo .zip del respaldo.")
        parser.add_argument("--si", action="store_true", help="No pedir confirmación.")

    def handle(self, *args, **opciones):
        archivo = Path(opciones["archivo"])
        if not archivo.exists():
            raise CommandError(f"No existe el archivo {archivo}.")
        if not opciones["si"]:
            respuesta = input("Se reemplazarán TODOS los datos actuales. Escriba SI para continuar: ")
            if respuesta.strip().upper() != "SI":
                raise CommandError("Restauración cancelada.")
        with zipfile.ZipFile(archivo) as zf, tempfile.TemporaryDirectory() as tmp:
            nombres = zf.namelist()
            if "datos.json" not in nombres:
                raise CommandError("El archivo no es un respaldo válido de SysFood.")
            for nombre in nombres:
                ruta = PurePosixPath(nombre)
                if ruta.is_absolute() or ".." in ruta.parts:
                    raise CommandError(f"Ruta no permitida en el respaldo: {nombre}")
            zf.extractall(tmp)
            with transaction.atomic():
                call_command("flush", interactive=False, verbosity=0)
                call_command("loaddata", str(Path(tmp) / "datos.json"), verbosity=0)
            origen = Path(tmp) / "protegido"
            raiz = settings.PROTECTED_MEDIA_ROOT
            if (raiz / "documentos").exists():
                shutil.rmtree(raiz / "documentos")
            raiz.mkdir(parents=True, exist_ok=True)
            if origen.exists():
                shutil.copytree(origen, raiz, dirs_exist_ok=True)
        self.stdout.write(self.style.SUCCESS(f"Respaldo restaurado desde {archivo}."))
