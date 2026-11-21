from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup
from .config import ADMIN_ID


def main_reply_menu(user_id: int) -> ReplyKeyboardMarkup:
    """Persistent chat menu inspired by the reference layout; no Mini App button."""
    kb = ReplyKeyboardBuilder()
    kb.button(text="⬇️ Пополнить")
    kb.button(text="⬆️ Вывести")
    kb.button(text="🎮 Играть")
    kb.button(text="👤 Профиль")
    kb.button(text="🎁 Бонусы")
    kb.button(text="🤝 Рефералка")
    kb.button(text="🧾 Чеки")
    kb.button(text="⚙️ Настройки")
    kb.button(text="📊 Топ")
    kb.button(text="🎧 Поддержка")
    kb.button(text="💸 $ с чата")
    kb.button(text="📢 Канал")
    kb.button(text="💬 Чат")
    kb.button(text="💳 Баланс")
    kb.button(text="☰ Меню")
    if user_id == ADMIN_ID:
        kb.button(text="👑 Админка")
        kb.adjust(2, 1, 2, 2, 2, 2, 2, 3, 1)
    else:
        kb.adjust(2, 1, 2, 2, 2, 2, 2, 3)
    return kb.as_markup(
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выбери раздел XLINE"
    )


def main_menu(user_id: int):
    """Inline fallback menu for existing callback-based screens."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🎮 Играть", callback_data="menu_games")
    kb.button(text="👤 Профиль", callback_data="profile")
    kb.button(text="💳 Баланс", callback_data="menu_balance")
    if user_id == ADMIN_ID:
        kb.button(text="👑 Админка", callback_data="admin_panel")
    kb.adjust(2, 1)
    return kb.as_markup()


def sub_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Подписаться на канал", url="https://t.me/xlinewin_news")
    kb.button(text="🔄 Проверить подписку", callback_data="check_sub")
    kb.adjust(1, 1)
    return kb.as_markup()
