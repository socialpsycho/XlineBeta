from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

router = Router()


@router.message(Command("miniapp"))
async def open_miniapp(message: Message):
    # Use the same authenticated one-time launch flow as /start.
    # A raw WebApp URL here would open without a launch token and can fail auth.
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🔐 Подготовить безопасный запуск",
            callback_data="xline_launch",
        )
    ]])
    await message.answer(
        "🔐 Для безопасного входа в XLINE нажми кнопку ниже. "
        "Я подготовлю персональную ссылку, действующую 3 минуты.",
        reply_markup=keyboard,
    )
