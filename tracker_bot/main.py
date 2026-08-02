import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo


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
    dispatcher.message.register(start, CommandStart())
    async with Bot(token) as bot:
        await dispatcher.start_polling(bot)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
