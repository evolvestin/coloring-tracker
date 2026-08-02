import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo


async def start(message: Message):
    tunnel_url_file = Path(os.getenv('TUNNEL_URL_FILE', '/app/data/tunnel_url.txt'))
    app_url = (
        tunnel_url_file.read_text(encoding='utf-8').strip()
        if tunnel_url_file.exists()
        else os.getenv('WEBAPP_PUBLIC_URL', '').rstrip('/')
    )
    if not app_url:
        await message.answer('Укажите WEBAPP_PUBLIC_URL в .env, чтобы открыть трекер.')
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Открыть трекер раскрасок', web_app=WebAppInfo(url=app_url))]
        ]
    )
    await message.answer('Добро пожаловать в трекер раскрасок!', reply_markup=keyboard)


async def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('BOT_TOKEN')
    if not token:
        raise RuntimeError('TELEGRAM_BOT_TOKEN is required for the bot service.')
    dispatcher = Dispatcher()
    dispatcher.message.register(start, CommandStart())
    async with Bot(token) as bot:
        await dispatcher.start_polling(bot)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
