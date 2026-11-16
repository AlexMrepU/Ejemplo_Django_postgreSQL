from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Agrega las columnas que faltaban en Main_user (nombre y cedula).

    El default '' solo sirve para rellenar filas que ya existan al migrar;
    no queda en el modelo (preserve_default=False). Si la tabla tuviera más de
    una fila, la restricción UNIQUE de cedula fallaría: en ese caso hay que
    vaciar la tabla o asignar cédulas distintas antes de migrar.
    """

    dependencies = [
        ('Main', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='nombre',
            field=models.CharField(default='', max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='user',
            name='cedula',
            field=models.CharField(default='', max_length=10, unique=True),
            preserve_default=False,
        ),
    ]
