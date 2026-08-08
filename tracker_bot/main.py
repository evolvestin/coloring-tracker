import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import BaseFilter, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from asgiref.sync import sync_to_async

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'coloring_tracker.settings')
import django

django.setup()

from django.utils import timezone  # noqa: E402

from app.models import ColoringSuggestion  # noqa: E402


def configured_moderation_chat_id():
    value = os.getenv('TELEGRAM_SUGGESTIONS_CHAT_ID', '').strip()
    try:
        return int(value) if value else None
    except ValueError:
        logging.getLogger(__name__).error(
            'TELEGRAM_SUGGESTIONS_CHAT_ID must be a numeric Telegram chat id.'
        )
        return None


class ModerationReplyFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.reply_to_message and message.chat.id == configured_moderation_chat_id())


@sync_to_async
def suggestion_for_reply(chat_id, message_id):
    return (
        ColoringSuggestion.objects.select_related('user')
        .filter(moderation_chat_id=chat_id, moderation_message_id=message_id)
        .first()
    )


@sync_to_async
def mark_reply_sent(suggestion_id):
    ColoringSuggestion.objects.filter(pk=suggestion_id).update(
        reply_sent_at=timezone.now(), reply_error='', updated_at=timezone.now()
    )


@sync_to_async
def mark_reply_error(suggestion_id, error):
    ColoringSuggestion.objects.filter(pk=suggestion_id).update(
        reply_error=str(error)[:4000], updated_at=timezone.now()
    )


async def copy_moderator_reply(message: Message):
    moderation_chat_id = configured_moderation_chat_id()
    reply_to = message.reply_to_message
    if not moderation_chat_id or not reply_to or message.chat.id != moderation_chat_id:
        return

    suggestion = await suggestion_for_reply(moderation_chat_id, reply_to.message_id)
    if not suggestion:
        return
    if not suggestion.user.telegram_id:
        await mark_reply_error(suggestion.pk, 'У пользователя нет Telegram ID.')
        return

    try:
        await message.copy_to(chat_id=suggestion.user.telegram_id)
    except Exception as exc:
        logging.getLogger(__name__).exception(
            'Could not copy moderator reply for suggestion %s', suggestion.pk
        )
        await mark_reply_error(suggestion.pk, exc)
        return
    await mark_reply_sent(suggestion.pk)


async def start(message: Message):
    app_url = os.getenv('TELEGRAM_WEBAPP_URL', '').rstrip('/')
    if not app_url:
        await message.answer('Укажите TELEGRAM_WEBAPP_URL в .env, чтобы открыть трекер.')
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Открыть трекер раскрасок', web_app=WebAppInfo(url=app_url))]
        ]
    )
    await message.answer('Добро пожаловать в трекер раскрасок!', reply_markup=keyboard)


async def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        raise RuntimeError('TELEGRAM_BOT_TOKEN is required for the bot service.')
    dispatcher = Dispatcher()
    dispatcher.message.register(copy_moderator_reply, ModerationReplyFilter())
    dispatcher.message.register(start, CommandStart())
    async with Bot(token) as bot:
        await dispatcher.start_polling(bot)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
