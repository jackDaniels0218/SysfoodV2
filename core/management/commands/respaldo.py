import io
import zipfile
from datetime import datetime

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

EXCLUIR = ["contenttypes", "auth.permission", "sessions"]


class Command(BaseCommand):
    help = "Genera un respaldo (.zip) con los datos de la base de datos y los documentos cargados."

    def add_arguments(self, parser):
        parser.add_argument("--salida", help="Ruta del archivo .zip (por defecto en la carpeta backups/).")

    def handle(self, *args, **opciones):
        settings.BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        destino = opciones.get("salida") or settings.BACKUP_ROOT / f"sysfood_{datetime.now():%Y%m%d_%H%M%S}.zip"
        datos = io.StringIO()
        call_command("dumpdata", exclude=EXCLUIR, natural_foreign=False, indent=None, stdout=datos)
        total_docs = 0
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("datos.json", datos.getvalue())
            raiz = settings.PROTECTED_MEDIA_ROOT
            if raiz.exists():
                for archivo in raiz.rglob("*"):
                    if archivo.is_file() and archivo.name != ".gitkeep":
                        zf.write(archivo, "protegido/" + archivo.relative_to(raiz).as_posix())
                        total_docs += 1
        self.stdout.write(self.style.SUCCESS(f"Respaldo creado: {destino} ({total_docs} documentos)."))
        return str(destino)
