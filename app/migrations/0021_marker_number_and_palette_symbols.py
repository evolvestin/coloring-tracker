from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('app', '0020_marker_palettes')]

    operations = [
        migrations.RemoveConstraint(
            model_name='marker',
            name='unique_marker_symbol_number',
        ),
        migrations.AlterField(
            model_name='marker',
            name='symbol',
            field=models.CharField(blank=True, max_length=32, verbose_name='Базовый значок'),
        ),
        migrations.AddField(
            model_name='markerpaletteitem',
            name='symbol',
            field=models.CharField(default='', max_length=32, verbose_name='Значок в палитре'),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name='marker',
            constraint=models.UniqueConstraint(fields=('number',), name='unique_marker_number'),
        ),
    ]
