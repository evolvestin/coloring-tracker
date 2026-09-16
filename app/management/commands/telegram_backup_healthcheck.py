from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from app.telegram_backup import TelegramBackupError, TelegramBotApi


class Command(BaseCommand):
    help = 'Check Telegram backup configuration and channel access without uploading data.'

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BACKUP_ENABLED:
            raise CommandError('Telegram backup is disabled')
        try:
            chat = TelegramBotApi().probe()
        except TelegramBackupError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            self.style.SUCCESS(
                f'Telegram backup channel is reachable: {chat.get("id")} '
                f'({chat.get("type")}, {chat.get("title", "")})'
            )
        )
