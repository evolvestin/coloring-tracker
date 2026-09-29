import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('app', '0019_telegram_backup'),
    ]

    operations = [
        migrations.AddField(
            model_name='trackeruser',
            name='marker_palette_import_allowed',
            field=models.BooleanField(
                default=True,
                help_text='Другие пользователи смогут импортировать палитры этого пользователя.',
                verbose_name='Разрешать импорт палитр',
            ),
        ),
        migrations.CreateModel(
            name='Marker',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('symbol', models.CharField(max_length=32, verbose_name='Значок')),
                ('number', models.CharField(max_length=64, verbose_name='Номер')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_markers', to='app.trackeruser')),
            ],
            options={'ordering': ('number', 'symbol'), 'verbose_name': 'Маркер', 'verbose_name_plural': 'Маркеры'},
        ),
        migrations.CreateModel(
            name='MarkerPalette',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('allow_import', models.BooleanField(default=True, verbose_name='Разрешать импорт этой палитры')),
                ('fingerprint', models.CharField(max_length=64, verbose_name='Отпечаток палитры')),
                ('imported_from', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='imports', to='app.markerpalette', verbose_name='Скопирована из')),
                ('page', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='marker_palettes', to='app.coloringpage')),
                ('user_book', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='marker_palettes', to='app.userbook')),
            ],
            options={'ordering': ('-created_at',), 'verbose_name': 'Палитра маркеров', 'verbose_name_plural': 'Палитры маркеров'},
        ),
        migrations.CreateModel(
            name='MarkerPaletteItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('usage_level', models.CharField(blank=True, choices=[('little', 'Немного'), ('medium', 'Средне'), ('much', 'Много')], max_length=16, verbose_name='Сколько ушло')),
                ('position', models.PositiveIntegerField(default=0, verbose_name='Порядок')),
                ('marker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='palette_items', to='app.marker')),
                ('palette', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='app.markerpalette')),
            ],
            options={'ordering': ('position', 'pk'), 'verbose_name': 'Маркер в палитре', 'verbose_name_plural': 'Маркеры в палитрах'},
        ),
        migrations.AddConstraint(
            model_name='marker',
            constraint=models.UniqueConstraint(fields=('symbol', 'number'), name='unique_marker_symbol_number'),
        ),
        migrations.AddConstraint(
            model_name='markerpalette',
            constraint=models.UniqueConstraint(fields=('user_book', 'page'), name='unique_marker_palette_user_page'),
        ),
        migrations.AddConstraint(
            model_name='markerpaletteitem',
            constraint=models.UniqueConstraint(fields=('palette', 'marker'), name='unique_palette_marker'),
        ),
    ]
