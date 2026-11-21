from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup
from .config import ADMIN_ID


def main_reply_menu(user_id: int) -> ReplyKeyboardMarkup:
    """Only the three persistent shortcuts shown at the bottom in the reference."""
    kb = ReplyKeyboardBuilder()
    kb.button(text="💳 Баланс")
    kb.button(text="🎮 Играть")
    kb.button(text="☰ Меню")
    kb.adjust(3)
    return kb.as_markup(
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выбери действие"
    )


def main_menu(user_id: int):
    """The large two-column section grid attached to the welcome message."""
    kb = InlineKeyboardBuilder()
    buttons = [
        ("⬇️ Пополнить", "section_deposit"),
        ("⬆️ Вывести", "section_withdraw"),
        ("🎮 Играть", "menu_games"),
        ("👤 Профиль", "profile"),
        ("🎁 Бонусы", "section_bonus"),
        ("🤝 Рефералка", "section_referral"),
        ("🧾 Чеки", "section_receipts"),
        ("⚙️ Настройки", "section_settings"),
        ("📊 Топ", "section_top"),
        ("🎧 Поддержка", "support"),
        ("💸 $ с чата", "section_chat_rewards"),
        ("📢 Канал", "section_channel"),
        ("💬 Чат", "section_chat"),
    ]
    for label, callback in buttons:
        kb.button(text=label, callback_data=callback)
    if user_id == ADMIN_ID:
        kb.button(text="👑 Админка", callback_data="admin_panel")
        kb.adjust(2, 1, 2, 2, 2, 2, 2, 1)
    else:
        kb.adjust(2, 1, 2, 2, 2, 2, 2)
    return kb.as_markup()


def sub_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Подписаться на канал", url="https://t.me/xlinewin_news")
    kb.button(text="🔄 Проверить подписку", callback_data="check_sub")
    kb.adjust(1, 1)
    return kb.as_markup()
