# Generated by Django 4.2.11 on 2025-06-21 23:39

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_alter_appconfiguration_options_order_adjusted_price'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='appconfiguration',
            options={'verbose_name_plural': 'Configuraciones de la Aplicación'},
        ),
        migrations.RemoveField(
            model_name='order',
            name='adjusted_price',
        ),
    ]
