from django.conf import settings
from django.db import migrations, models


def copiar_archivos(apps, schema_editor):
    """Guarda en la base los archivos que todavía estén en el disco."""
    Documento = apps.get_model("usuarios", "DocumentoValidacion")
    Archivo = apps.get_model("usuarios", "ArchivoDocumento")
    for doc in Documento.objects.all().only("pk", "docv_ruta").iterator():
        ruta = settings.PROTECTED_MEDIA_ROOT / doc.docv_ruta
        if doc.docv_ruta and ruta.is_file():
            Archivo.objects.update_or_create(documento_id=doc.pk, defaults={"arc_contenido": ruta.read_bytes()})


class Migration(migrations.Migration):
    dependencies = [
        ("usuarios", "0005_sisben_subgrupo"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArchivoDocumento",
            fields=[
                (
                    "documento",
                    models.OneToOneField(
                        db_column="docv_id",
                        on_delete=models.deletion.CASCADE,
                        primary_key=True,
                        related_name="archivo",
                        serialize=False,
                        to="usuarios.documentovalidacion",
                    ),
                ),
                ("arc_contenido", models.BinaryField(verbose_name="contenido")),
            ],
            options={
                "verbose_name": "archivo de documento",
                "db_table": "archivo_documento",
            },
        ),
        migrations.RunPython(copiar_archivos, migrations.RunPython.noop),
    ]
