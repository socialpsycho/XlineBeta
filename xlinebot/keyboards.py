from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, WebAppInfo
from .config import WEBAPP_URL
from .config import ADMIN_ID

def main_reply_menu(user_id: int) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="🚀 Открыть XLINE", web_app=WebAppInfo(url=WEBAPP_URL))
    kb.adjust(1)
    return kb.as_markup(
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Открыть XLINE"
    )

def main_menu(user_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="💼 Кошелёк", callback_data="wallet")
    kb.button(text="👤 Профиль", callback_data="profile")
    
    if user_id == ADMIN_ID:
        kb.button(text="👑 Админка", callback_data="admin_panel")
        kb.adjust(2, 1)
    else:
        kb.adjust(2)
        
    return kb.as_markup()

def sub_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Подписаться на канал", url="https://t.me/xlinewin_news")
    kb.button(text="🔄 Проверить подписку", callback_data="check_sub")
    kb.adjust(1, 1)
    return kb.as_markup()
