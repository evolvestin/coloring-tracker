"""Stable Telegram backup protocol and deployment routing constants."""

TELEGRAM_BACKUP_CHAT_ID = -1003719098734
TELEGRAM_BACKUP_API_BASE_URL = 'http://telegram-bot-api:8081'
TELEGRAM_BACKUP_LOCAL_FILE_MODE = True
TELEGRAM_BACKUP_PART_SIZE_BYTES = 1_900 * 1024 * 1024
TELEGRAM_BACKUP_SHARED_DIR = '/var/lib/coloring-tracker/telegram-backups'
