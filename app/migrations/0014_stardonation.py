import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('app', '0013_coloringsuggestion_moderation_message'),
    ]

    operations = [
        migrations.CreateModel(
            name='StarDonation',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                    ),
                ),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('amount', models.PositiveIntegerField(verbose_name='Сумма, Stars')),
                (
                    'payload',
                    models.CharField(
                        default=uuid.uuid4,
                        editable=False,
                        max_length=128,
                        unique=True,
                        verbose_name='Платёжный payload',
                    ),
                ),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('pending', 'Ожидает оплаты'),
                            ('succeeded', 'Оплачен'),
                            ('failed', 'Ошибка'),
                        ],
                        default='pending',
                        max_length=16,
                        verbose_name='Статус',
                    ),
                ),
                ('is_test', models.BooleanField(default=False, verbose_name='Тестовый платёж')),
                (
                    'invoice_url',
                    models.URLField(blank=True, max_length=1000, verbose_name='Ссылка на invoice'),
                ),
                (
                    'telegram_payment_charge_id',
                    models.CharField(
                        blank=True,
                        max_length=255,
                        null=True,
                        unique=True,
                        verbose_name='Telegram payment charge ID',
                    ),
                ),
                (
                    'provider_payment_charge_id',
                    models.CharField(
                        blank=True, max_length=255, verbose_name='Provider payment charge ID'
                    ),
                ),
                (
                    'paid_at',
                    models.DateTimeField(blank=True, null=True, verbose_name='Дата оплаты'),
                ),
                ('error', models.TextField(blank=True, verbose_name='Ошибка')),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='star_donations',
                        to='app.trackeruser',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Донат Stars',
                'verbose_name_plural': 'Донаты Stars',
                'ordering': ('-created_at',),
            },
        ),
    ]
