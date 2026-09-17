import os
import shutil
import subprocess
import tempfile
import zipfile
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from app.models import TelegramBackup
from app.telegram_backup import (
    TelegramBackupError,
    download_backup,
    download_manifest_backup,
    extract_backup_archive,
)


class Command(BaseCommand):
    help = 'Restore PostgreSQL from Telegram. Destructive.'

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true')
        parser.add_argument(
            '--manifest-file-id',
            help='Telegram file_id of the JSON manifest; DB metadata is not required',
        )
        parser.add_argument(
            'reference',
            nargs='?',
            help='Telegram message id or private-channel URL; omitted means latest DB backup',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            raise CommandError('Refusing restore: pass --confirm')
        if not settings.TELEGRAM_BACKUP_ENABLED:
            raise CommandError('Telegram backup is disabled')
        manifest_file_id = options['manifest_file_id']
        reference = options['reference']
        if manifest_file_id and reference:
            raise CommandError('Use either --manifest-file-id or a message reference, not both')
        if reference and not self._is_message_reference(reference):
            manifest_file_id = reference.strip()
        fd, path = tempfile.mkstemp(suffix='.dump')
        os.close(fd)
        extract_dir = tempfile.mkdtemp(prefix='restore-archive-')
        try:
            try:
                if manifest_file_id:
                    download_manifest_backup(manifest_file_id, path)
                else:
                    download_backup(self._select_backup(reference), path)
            except TelegramBackupError as error:
                raise CommandError(f'Telegram restore download failed: {error}') from error

            database = settings.DATABASES['default']
            db_restore_path = path
            extracted_media_dir = None
            if zipfile.is_zipfile(path):
                db_restore_path, extracted_media_dir = extract_backup_archive(path, extract_dir)
            restore_environment = {
                **os.environ,
                'PGPASSWORD': database.get('PASSWORD', ''),
                'PGHOST': database.get('HOST', ''),
                'PGPORT': str(database.get('PORT', '5432')),
                'PGUSER': database.get('USER', ''),
            }
            try:
                result = subprocess.run(
                    [
                        'pg_restore',
                        '--clean',
                        '--if-exists',
                        '--no-owner',
                        '--dbname',
                        database['NAME'],
                        db_restore_path,
                    ],
                    env=restore_environment,
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError as error:
                raise CommandError(
                    'PostgreSQL client tools are not installed in this environment'
                ) from error
            if result.returncode:
                raise CommandError('pg_restore failed: ' + result.stderr[-500:])
            if extracted_media_dir is not None:
                self._restore_media(extracted_media_dir)
            self.stdout.write(self.style.SUCCESS('Restore complete'))
        finally:
            if os.path.exists(path):
                os.unlink(path)
            shutil.rmtree(extract_dir, ignore_errors=True)

    @staticmethod
    def _restore_media(source_dir):
        media_root = settings.MEDIA_ROOT
        media_root.mkdir(parents=True, exist_ok=True)
        for source in source_dir.rglob('*'):
            if source.is_file():
                destination = media_root / source.relative_to(source_dir)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

    def _select_backup(self, reference):
        if not reference:
            backup = TelegramBackup.objects.filter(status=TelegramBackup.Status.UPLOADED).first()
            if backup is None:
                raise CommandError('No uploaded Telegram backup was found in the database')
            return backup

        message_id = self._parse_message_reference(reference)
        backup = (
            TelegramBackup.objects.filter(status=TelegramBackup.Status.UPLOADED)
            .filter(Q(parts__message_id=message_id) | Q(manifest_message_id=message_id))
            .distinct()
            .first()
        )
        if backup is None:
            raise CommandError(
                f'Telegram message {message_id} is not indexed in this database; '
                'use the manifest file_id when backup metadata is absent'
            )
        return backup

    @staticmethod
    def _is_message_reference(reference):
        value = reference.strip()
        if value.isdigit():
            return True
        parsed = urlparse(value)
        return parsed.scheme in ('http', 'https') and parsed.netloc in (
            't.me',
            'www.t.me',
            'telegram.me',
            'www.telegram.me',
        )

    @staticmethod
    def _parse_message_reference(reference):
        value = reference.strip()
        if value.isdigit():
            return int(value)
        parsed = urlparse(value)
        if parsed.scheme not in ('http', 'https') or parsed.netloc not in (
            't.me',
            'www.t.me',
            'telegram.me',
            'www.telegram.me',
        ):
            raise CommandError('Reference must be a Telegram message id or t.me URL')
        parts = [part for part in parsed.path.split('/') if part]
        if (
            len(parts) != 3
            or parts[0] != 'c'
            or not parts[1].isdigit()
            or not parts[2].isdigit()
        ):
            raise CommandError(
                'Only private-channel URLs like https://t.me/c/3980932874/10 are supported'
            )
        expected_channel = str(settings.TELEGRAM_BACKUP_CHAT_ID)
        if expected_channel != f'-100{parts[1]}':
            raise CommandError('Telegram URL points to a different channel')
        return int(parts[2])
