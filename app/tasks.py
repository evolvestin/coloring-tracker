import asyncio
import html
import logging
import os
from io import StringIO
from urllib.parse import urlsplit

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from celery import shared_task
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from app.models import ColoringSuggestion

logger = logging.getLogger(__name__)


@shared_task
def backup_tracker_database():
    """Run the database backup command in a Celery worker."""
    output = StringIO()
    call_command('backup_tracker_database', stdout=output)
    return output.getvalue().strip()


def admin_suggestion_url(suggestion_id):
    webapp_url = os.getenv('TELEGRAM_WEBAPP_URL', '').rstrip('/')
    parsed = urlsplit(webapp_url)
    base = f'{parsed.scheme}://{parsed.netloc}' if parsed.scheme and parsed.netloc else webapp_url
    if not base:
        raise RuntimeError('TELEGRAM_WEBAPP_URL обязателен.')
    return f'{base}{reverse("admin:app_coloringsuggestion_change", args=(suggestion_id,))}'


def _code_block(value, max_escaped_length):
    value = value or '—'
    escaped = html.escape(value, quote=False)
    if len(escaped) > max_escaped_length:
        low, high = 0, len(value)
        while low < high:
            middle = (low + high + 1) // 2
            if len(html.escape(value[:middle], quote=False)) <= max_escaped_length - 1:
                low = middle
            else:
                high = middle - 1
        escaped = html.escape(value[:low], quote=False) + '…'
    return f'<pre>{escaped}</pre>'


def suggestion_notification_text(suggestion):
    user = suggestion.user
    display_name = html.escape((user.display_name or 'Пользователь')[:300], quote=False)
    username = html.escape(
        (f'@{user.username}' if user.username else 'без username')[:300], quote=False
    )
    user_link = (
        f'<a href="tg://user?id={user.telegram_id}">Профиль пользователя</a>'
        if user.telegram_id
        else 'Профиль пользователя недоступен в Telegram'
    )
    return (
        f'<b>{display_name}</b> ({username}) предложил раскраску\n\n'
        f'{_code_block(suggestion.title, 900)}\n'
        f'{_code_block(suggestion.source_text, 1800)}\n\n'
        f'<a href="{html.escape(admin_suggestion_url(suggestion.pk), quote=True)}">'
        f'Открыть предложение в админке</a>\n{user_link}'
    )


async def _send_telegram_message(text, chat_id):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token or not chat_id:
        raise RuntimeError('TELEGRAM_BOT_TOKEN и TELEGRAM_SUGGESTIONS_CHAT_ID обязательны.')
    async with Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) as bot:
        await bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=True)


@shared_task
def send_suggestion_notification(suggestion_id):
    suggestion = ColoringSuggestion.objects.select_related('user').get(pk=suggestion_id)
    try:
        asyncio.run(
            _send_telegram_message(
                suggestion_notification_text(suggestion), os.getenv('TELEGRAM_SUGGESTIONS_CHAT_ID')
            )
        )
    except Exception as exc:
        logger.exception('Could not notify Telegram about suggestion %s', suggestion_id)
        suggestion.notification_error = str(exc)[:4000]
        suggestion.save(update_fields=('notification_error', 'updated_at'))
        return False
    suggestion.notification_sent_at = timezone.now()
    suggestion.notification_error = ''
    suggestion.save(update_fields=('notification_sent_at', 'notification_error', 'updated_at'))
    return True


@shared_task
def send_suggestion_reply(suggestion_id):
    suggestion = ColoringSuggestion.objects.select_related('user').get(pk=suggestion_id)
    if not suggestion.admin_reply.strip():
        return False
    try:
        asyncio.run(_send_telegram_message(suggestion.admin_reply, suggestion.user.telegram_id))
    except Exception as exc:
        logger.exception('Could not send reply for suggestion %s', suggestion_id)
        suggestion.reply_error = str(exc)[:4000]
        suggestion.save(update_fields=('reply_error', 'updated_at'))
        return False
    suggestion.reply_sent_at = timezone.now()
    suggestion.reply_error = ''
    suggestion.save(update_fields=('reply_sent_at', 'reply_error', 'updated_at'))
    return True
