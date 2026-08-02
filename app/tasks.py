import json
import os
from datetime import datetime, timezone
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.management import call_command
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


@shared_task
def backup_tracker_database():
    """Create a logical Django backup and upload it to the configured Drive folder."""
    credentials_json = os.getenv('GOOGLE_DRIVE_CREDENTIALS_JSON')
    folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
    if not credentials_json or not folder_id:
        return 'Backup skipped: Google Drive is not configured.'

    backup_dir = Path(settings.MEDIA_ROOT).parent / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup_file = backup_dir / f'coloring_tracker_{timestamp}.json'
    call_command('dumpdata', indent=2, output=str(backup_file))

    credentials = service_account.Credentials.from_service_account_info(
        json.loads(credentials_json)
    )
    drive = build('drive', 'v3', credentials=credentials, cache_discovery=False)
    metadata = {'name': backup_file.name, 'parents': [folder_id]}
    drive.files().create(
        body=metadata,
        media_body=MediaFileUpload(str(backup_file), mimetype='application/json'),
        fields='id',
    ).execute()
    return f'Uploaded {backup_file.name}'
