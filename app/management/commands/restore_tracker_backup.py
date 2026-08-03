import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.db import connections
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


class Command(BaseCommand):
    help = (
        'Restore the database and media files from the configured backup archive in Google Drive.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Required: delete all current database data before restoring the backup.',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            raise CommandError(
                'Refusing to overwrite the database. Re-run with --confirm after verifying '
                'that the current data may be deleted.'
            )

        credentials_json = os.getenv('GOOGLE_DRIVE_CREDENTIALS_JSON')
        folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
        backup_name = os.getenv('GOOGLE_DRIVE_BACKUP_FILENAME')
        if not credentials_json or not folder_id or not backup_name:
            raise CommandError(
                'Google Drive backup is not configured. Set GOOGLE_DRIVE_CREDENTIALS_JSON, '
                'GOOGLE_DRIVE_FOLDER_ID, and GOOGLE_DRIVE_BACKUP_FILENAME in .env.'
            )

        credentials = service_account.Credentials.from_service_account_info(
            json.loads(credentials_json)
        )
        drive = build('drive', 'v3', credentials=credentials, cache_discovery=False)
        escaped_name = backup_name.replace("'", "\\'")
        matching_files = (
            drive.files()
            .list(
                q=(f"'{folder_id}' in parents and name = '{escaped_name}' and trashed = false"),
                spaces='drive',
                fields='files(id, name)',
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()['files']
        )
        if len(matching_files) != 1:
            raise CommandError(
                f'Expected exactly one file named {backup_name!r} in the configured Google Drive '
                f'folder; found {len(matching_files)}.'
            )

        backup_dir = Path(settings.MEDIA_ROOT).parent / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / backup_name
        try:
            backup_file.unlink(missing_ok=True)
            request = drive.files().get_media(
                fileId=matching_files[0]['id'], supportsAllDrives=True
            )
            with backup_file.open('wb') as destination:
                downloader = MediaIoBaseDownload(destination, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

            database = settings.DATABASES['default']
            restore_environment = os.environ.copy()
            restore_environment['PGPASSWORD'] = database['PASSWORD']

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dir_path = Path(temp_dir)
                if zipfile.is_zipfile(backup_file):
                    with zipfile.ZipFile(backup_file, 'r') as zip_file:
                        zip_file.extractall(temp_dir_path)
                    db_dump_file = temp_dir_path / 'db.dump'
                    extracted_media_dir = temp_dir_path / 'media'
                    if extracted_media_dir.exists():
                        target_media_dir = Path(settings.MEDIA_ROOT)
                        target_media_dir.mkdir(parents=True, exist_ok=True)
                        for file_path in extracted_media_dir.rglob('*'):
                            if file_path.is_file():
                                destination = target_media_dir / file_path.relative_to(
                                    extracted_media_dir
                                )
                                destination.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(file_path, destination)
                else:
                    db_dump_file = backup_file

                connections.close_all()
                self.stdout.write(
                    f'Downloaded {backup_name}; restoring PostgreSQL database and media files.'
                )
                try:
                    subprocess.run(
                        [
                            'pg_restore',
                            '--clean',
                            '--if-exists',
                            '--no-owner',
                            '--no-privileges',
                            '--exit-on-error',
                            '--host',
                            database['HOST'],
                            '--port',
                            str(database['PORT']),
                            '--username',
                            database['USER'],
                            '--dbname',
                            database['NAME'],
                            str(db_dump_file),
                        ],
                        check=True,
                        env=restore_environment,
                    )
                except FileNotFoundError as error:
                    raise CommandError(
                        'pg_restore is not installed in this environment.'
                    ) from error
                except subprocess.CalledProcessError as error:
                    raise CommandError(
                        f'pg_restore failed with exit code {error.returncode}.'
                    ) from error
        finally:
            backup_file.unlink(missing_ok=True)

        self.stdout.write(self.style.SUCCESS(f'Database and media restored from {backup_name}.'))
