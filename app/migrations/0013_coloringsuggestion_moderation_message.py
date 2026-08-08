from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('app', '0012_image_originals'),
    ]

    operations = [
        migrations.AddField(
            model_name='coloringsuggestion',
            name='moderation_chat_id',
            field=models.BigIntegerField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name='ID группы модераторов',
            ),
        ),
        migrations.AddField(
            model_name='coloringsuggestion',
            name='moderation_message_id',
            field=models.PositiveBigIntegerField(
                blank=True,
                null=True,
                verbose_name='ID сообщения в группе модераторов',
            ),
        ),
    ]
