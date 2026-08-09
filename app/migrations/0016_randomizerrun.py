# Generated manually because the local virtual environment does not include Django.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('app', '0015_stardonation_notification_chat_id_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='RandomizerRun',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'page',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='randomizer_runs',
                        to='app.coloringpage',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='randomizer_runs',
                        to='app.trackeruser',
                    ),
                ),
                (
                    'user_book',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='randomizer_runs',
                        to='app.userbook',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Запуск рандомизатора',
                'verbose_name_plural': 'Запуски рандомизатора',
                'ordering': ('-created_at',),
            },
        ),
    ]
