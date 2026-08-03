import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, CommandError
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


class Command(BaseCommand):
    help = 'Create a PostgreSQL dump and media backup archive, then update Google Drive.'

    def handle(self, *args, **options):
        credentials_json = os.getenv('GOOGLE_DRIVE_CREDENTIALS_JSON')
        folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
        backup_name = os.getenv('GOOGLE_DRIVE_BACKUP_FILENAME')
        if not credentials_json or not folder_id or not backup_name:
            raise CommandError(
                'Google Drive backup is not configured. Set GOOGLE_DRIVE_CREDENTIALS_JSON, '
                'GOOGLE_DRIVE_FOLDER_ID, and GOOGLE_DRIVE_BACKUP_FILENAME in .env.'
            )

        backup_dir = Path(settings.MEDIA_ROOT).parent / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / backup_name
        database = settings.DATABASES['default']
        dump_environment = os.environ.copy()
        dump_environment['PGPASSWORD'] = database['PASSWORD']

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            db_dump_path = temp_dir_path / 'db.dump'

            try:
                subprocess.run(
                    [
                        'pg_dump',
                        '--format=custom',
                        '--no-owner',
                        '--no-privileges',
                        '--host',
                        database['HOST'],
                        '--port',
                        str(database['PORT']),
                        '--username',
                        database['USER'],
                        '--file',
                        str(db_dump_path),
                        database['NAME'],
                    ],
                    check=True,
                    env=dump_environment,
                )
            except FileNotFoundError as error:
                raise CommandError('pg_dump is not installed in this environment.') from error
            except subprocess.CalledProcessError as error:
                raise CommandError(f'pg_dump failed with exit code {error.returncode}.') from error

            backup_file.unlink(missing_ok=True)
            with zipfile.ZipFile(backup_file, 'w', compression=zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.write(db_dump_path, arcname='db.dump')
                media_dir = Path(settings.MEDIA_ROOT)
                if media_dir.exists():
                    for file_path in media_dir.rglob('*'):
                        if file_path.is_file():
                            arcname = Path('media') / file_path.relative_to(media_dir)
                            zip_file.write(file_path, arcname=arcname)

            try:
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
                        f'Expected exactly one file named {backup_name!r} in the configured '
                        f'Google Drive folder; found {len(matching_files)}.'
                    )

                drive.files().update(
                    fileId=matching_files[0]['id'],
                    media_body=MediaFileUpload(
                        str(backup_file), mimetype='application/octet-stream', resumable=True
                    ),
                    fields='id, name, modifiedTime',
                    supportsAllDrives=True,
                ).execute()
            finally:
                backup_file.unlink(missing_ok=True)

        self.stdout.write(self.style.SUCCESS(f'Updated {backup_name} with database dump and media files.'))