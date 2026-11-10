from django.db import migrations

from core.parametros import DEFINICIONES


def crear(apps, schema_editor):
    Parametro = apps.get_model("core", "Parametro")
    for clave, definicion in DEFINICIONES.items():
        Parametro.objects.get_or_create(par_clave=clave, defaults={"par_valor": definicion[0], "par_desc": definicion[1]})


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(crear, migrations.RunPython.noop)]
