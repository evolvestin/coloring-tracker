import os
import subprocess
import tempfile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from app.telegram_backup import TelegramBackupError, upload_backup


class Command(BaseCommand):
    help = 'Create the PostgreSQL backup and upload it to Telegram.'

    def handle(self, *args, **options):
        if settings.DEBUG:
            raise CommandError('Backup is disabled while DEBUG is enabled')
        if not settings.TELEGRAM_BACKUP_ENABLED:
            raise CommandError('Telegram backup is disabled')
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError('TELEGRAM_BOT_TOKEN is not configured')
        if not settings.TELEGRAM_BACKUP_CHAT_ID:
            raise CommandError('Telegram backup channel ID is not configured')

        os.makedirs(settings.TELEGRAM_BACKUP_SHARED_DIR, exist_ok=True)
        fd, path = tempfile.mkstemp(
            suffix='.dump',
            dir=(
                settings.TELEGRAM_BACKUP_SHARED_DIR
                if settings.TELEGRAM_BACKUP_LOCAL_FILE_MODE
                else None
            ),
        )
        os.close(fd)
        if settings.TELEGRAM_BACKUP_LOCAL_FILE_MODE:
            os.chmod(path, 0o644)
        try:
            database = settings.DATABASES['default']
            dump_environment = {
                **os.environ,
                'PGPASSWORD': database.get('PASSWORD', ''),
                'PGHOST': database.get('HOST', ''),
                'PGPORT': str(database.get('PORT', '5432')),
                'PGUSER': database.get('USER', ''),
            }
            try:
                result = subprocess.run(
                    [
                        'pg_dump',
                        '--format=custom',
                        '--file',
                        path,
                        database['NAME'],
                    ],
                    env=dump_environment,
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError as error:
                raise CommandError('pg_dump is not installed in this environment') from error
            if result.returncode:
                raise CommandError('pg_dump failed: ' + result.stderr[-500:])
            try:
                backup = upload_backup(path, source_filename='coloring-tracker.dump')
            except TelegramBackupError as error:
                raise CommandError(f'Telegram backup failed: {error}') from error
            self.stdout.write(
                self.style.SUCCESS(
                    f'Uploaded Telegram backup {backup.id} '
                    f'({backup.size_bytes} bytes, {backup.part_count} part(s)); '
                    'manifest file_id is available in Django admin'
                )
            )
        finally:
            if os.path.exists(path):
                os.unlink(path)
