from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("usuarios", "0004_verificacion_automatica"),
    ]

    operations = [
        migrations.AddField(
            model_name="perfilbeneficiario",
            name="ben_sisben_subgrupo",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="subgrupo de Sisbén"),
        ),
    ]
