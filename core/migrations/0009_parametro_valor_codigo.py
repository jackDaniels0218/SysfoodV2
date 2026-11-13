from django.db import migrations, models

# Valores que tenían estos parámetros en el código antes de existir sysfood/rnf.py. Sirven de
# referencia: si rnf.py ya trae otro valor, se aplica al terminar migrate (core.apps).
VALORES_ANTERIORES = {
    "intentos_ingreso": "5",
    "minutos_bloqueo": "15",
    "vigencia_token_minutos": "60",
    "tam_max_archivo_mb": "5",
    "formatos_permitidos": "pdf,jpg,png",
    "mapa_desplazamiento_m": "300",
}


def marcar(apps, schema_editor):
    Parametro = apps.get_model("core", "Parametro")
    for clave, valor in VALORES_ANTERIORES.items():
        Parametro.objects.filter(par_clave=clave).update(par_valor_codigo=valor)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0008_accion_envio_reporte"),
    ]

    operations = [
        migrations.AddField(
            model_name="parametro",
            name="par_valor_codigo",
            field=models.CharField(
                blank=True, default="", editable=False, max_length=500, verbose_name="valor en el código"
            ),
        ),
        migrations.RunPython(marcar, migrations.RunPython.noop),
    ]
