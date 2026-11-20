from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from ..config import WEBAPP_URL

router = Router()

webapp_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[[
        InlineKeyboardButton(
            text="🚀 Открыть XLINE Mini App",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )
    ]]
)


@router.message(Command("miniapp"))
async def open_miniapp(message: Message):
    await message.answer(
        "🚀 XLINE Mini App\n\n"
        "Управляй профилем, кошельком и цифровыми товарами XLINE.",
        reply_markup=webapp_keyboard,
    )
