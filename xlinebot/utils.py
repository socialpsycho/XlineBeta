from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from .config import CHANNEL_ID

async def check_sub(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status not in ("left", "kicked")
    except TelegramBadRequest:
        # Если бот не админ в канале, пропускаем (чтобы бот не падал)
        return True
