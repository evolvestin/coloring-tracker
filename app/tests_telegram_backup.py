import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from app.models import TelegramBackup
from app.telegram_backup import (
    TelegramBackupError,
    TelegramDocument,
    download_backup,
    download_manifest_backup,
    load_manifest,
    upload_backup,
)


class FakeTelegramClient:
    downloaded_files = {}
    media_group_sizes = []
    captions = {}
    deleted_message_ids = []

    def __init__(self):
        self.next_message_id = 100

    def send_document(self, path, *, filename, caption):
        message_id = self.next_message_id
        self.next_message_id += 1
        file_id = f'file-{message_id}'
        type(self).downloaded_files[file_id] = Path(path).read_bytes()
        type(self).captions[message_id] = caption
        return TelegramDocument(message_id, file_id, f'unique-{message_id}')

    def send_media_group(self, paths, *, filenames, file_ids=None, captions=None):
        type(self).media_group_sizes.append(len(paths))
        documents = []
        for index, (path, filename) in enumerate(zip(paths, filenames, strict=True)):
            caption = captions[index] if captions is not None else ''
            message_id = self.next_message_id
            self.next_message_id += 1
            if file_ids is None or not file_ids[index]:
                document = self.send_document(path, filename=filename, caption=caption)
            else:
                document = TelegramDocument(message_id, file_ids[index], f'unique-{message_id}')
                type(self).captions[message_id] = caption
            documents.append(document)
        return documents

    def edit_message_caption(self, message_id, caption):
        type(self).captions[message_id] = caption

    def delete_message(self, message_id):
        type(self).deleted_message_ids.append(message_id)

    def download_file(self, file_id, destination):
        Path(destination).write_bytes(type(self).downloaded_files[file_id])


class TelegramBackupTests(TestCase):
    def setUp(self):
        FakeTelegramClient.downloaded_files = {}
        FakeTelegramClient.media_group_sizes = []
        FakeTelegramClient.captions = {}
        FakeTelegramClient.deleted_message_ids = []

    def test_upload_publishes_small_dump_as_part_and_manifest(self):
        source = self._temp_file(b'backup-content')
        with tempfile.TemporaryDirectory() as workdir, self.settings(
            TELEGRAM_BACKUP_PART_SIZE_BYTES=100,
            TELEGRAM_BACKUP_SHARED_DIR=workdir,
        ), patch('app.telegram_backup.TelegramBotApi', FakeTelegramClient):
            backup = upload_backup(source, source_filename='coloring-tracker.dump')

        self.assertEqual(backup.status, TelegramBackup.Status.UPLOADED)
        self.assertEqual(backup.part_count, 1)
        self.assertEqual(FakeTelegramClient.media_group_sizes, [2])
        self.assertEqual(
            FakeTelegramClient.captions[backup.manifest_message_id],
            f'<code>{backup.manifest_file_id}</code>',
        )
        manifest = self._load_fake_manifest(backup.manifest_file_id)
        self.assertEqual(manifest['parts'][0]['file_id'], 'file-100')

    def test_media_groups_do_not_have_single_item_remainder(self):
        source = self._temp_file(b'abcdefghijk')
        with tempfile.TemporaryDirectory() as workdir, self.settings(
            TELEGRAM_BACKUP_PART_SIZE_BYTES=1,
            TELEGRAM_BACKUP_SHARED_DIR=workdir,
        ), patch('app.telegram_backup.TelegramBotApi', FakeTelegramClient):
            backup = upload_backup(source)

        self.assertEqual(backup.part_count, 11)
        self.assertEqual(FakeTelegramClient.media_group_sizes, [10, 2])

    def test_media_groups_handle_twenty_plus_parts(self):
        with tempfile.TemporaryDirectory() as workdir, self.settings(
            TELEGRAM_BACKUP_PART_SIZE_BYTES=1,
            TELEGRAM_BACKUP_SHARED_DIR=workdir,
        ), patch('app.telegram_backup.TelegramBotApi', FakeTelegramClient):
            for part_count in (20, 21):
                source = self._temp_file(b'x' * part_count)
                backup = upload_backup(source)
                self.assertEqual(backup.part_count, part_count)

        self.assertEqual(FakeTelegramClient.media_group_sizes, [10, 9, 2, 10, 10, 2])
        self.assertTrue(all(2 <= size <= 10 for size in FakeTelegramClient.media_group_sizes))

    def test_portable_restore_does_not_require_database_index(self):
        source = self._temp_file(b'backup-content')
        with tempfile.TemporaryDirectory() as workdir, self.settings(
            TELEGRAM_BACKUP_PART_SIZE_BYTES=100,
            TELEGRAM_BACKUP_SHARED_DIR=workdir,
        ), patch('app.telegram_backup.TelegramBotApi', FakeTelegramClient):
            backup = upload_backup(source)
            backup.delete()
            destination = self._temp_file(b'')
            download_manifest_backup(backup.manifest_file_id, destination)

        self.assertEqual(Path(destination).read_bytes(), b'backup-content')

    def test_index_restore_checks_part_and_assembled_hashes(self):
        source = self._temp_file(b'backup-content')
        with tempfile.TemporaryDirectory() as workdir, self.settings(
            TELEGRAM_BACKUP_SHARED_DIR=workdir,
        ), patch('app.telegram_backup.TelegramBotApi', FakeTelegramClient):
            backup = upload_backup(source)
            destination = self._temp_file(b'')
            download_backup(backup, destination)
            FakeTelegramClient.downloaded_files[backup.parts.get().file_id] = b'tampered'
            with self.assertRaises(TelegramBackupError):
                download_backup(backup, self._temp_file(b''))

    def test_manifest_rejects_size_mismatch_and_non_integer(self):
        manifest = {
            'format': 'assethub-telegram-backup-v2',
            'backup_id': '00000000-0000-0000-0000-000000000001',
            'source_filename': 'x.dump',
            'size_bytes': 2,
            'sha256': 'a' * 64,
            'parts': [
                {
                    'part_number': 1,
                    'filename': 'x',
                    'size_bytes': 1,
                    'sha256': 'b' * 64,
                    'file_id': 'file-1',
                }
            ],
        }
        path = self._temp_file(json.dumps(manifest).encode())
        with self.assertRaises(TelegramBackupError):
            load_manifest(path)
        manifest['size_bytes'] = '1'
        Path(path).write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaises(TelegramBackupError):
            load_manifest(path)

    @staticmethod
    def _temp_file(content):
        fd, path = tempfile.mkstemp()
        os.close(fd)
        Path(path).write_bytes(content)
        return path

    @staticmethod
    def _load_fake_manifest(file_id):
        path = TelegramBackupTests._temp_file(FakeTelegramClient.downloaded_files[file_id])
        try:
            return load_manifest(path)
        finally:
            os.unlink(path)
