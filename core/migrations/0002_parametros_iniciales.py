from django.db import migrations

from core.parametros import DEFINICIONES


def crear(apps, schema_editor):
    Parametro = apps.get_model("core", "Parametro")
    for clave, (valor, descripcion, _tipo) in DEFINICIONES.items():
        Parametro.objects.get_or_create(par_clave=clave, defaults={"par_valor": valor, "par_desc": descripcion})


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(crear, migrations.RunPython.noop)]
