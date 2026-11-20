from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, WebAppInfo
from .config import WEBAPP_URL
from .config import ADMIN_ID

def main_reply_menu(user_id: int) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="🚀 Играть", web_app=WebAppInfo(url=WEBAPP_URL))
    kb.adjust(1)
    return kb.as_markup(
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Нажми «🚀 Играть»"
    )

def main_menu(user_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="🎰 Играть", callback_data="play_menu")
    kb.button(text="💼 Кошелёк", callback_data="wallet")
    kb.button(text="👤 Профиль", callback_data="profile")
    
    if user_id == ADMIN_ID:
        kb.button(text="👑 Админка", callback_data="admin_panel")
        kb.adjust(1, 2, 1)
    else:
        kb.adjust(1, 2)
        
    return kb.as_markup()

def play_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="💣 Mines", callback_data="game_mines")
    kb.button(text="🚀 Ракета", callback_data="game_rocket")
    kb.button(text="🗼 Башня", callback_data="game_tower")
    kb.button(text="🎰 Слоты", callback_data="game_slots")
    kb.button(text="🃏 Blackjack", callback_data="game_blackjack")
    kb.button(text="🔙 Назад", callback_data="main_menu")
    kb.adjust(2, 2, 2)
    return kb.as_markup()

def bet_menu(prefix: str, last_bet: float, back: str):
    kb = InlineKeyboardBuilder()
    # Базовые кнопки ставок (в долларах)
    kb.button(text="0.10 $", callback_data=f"{prefix}_bet_0.10")
    kb.button(text="0.50 $", callback_data=f"{prefix}_bet_0.50")
    kb.button(text="1.00 $", callback_data=f"{prefix}_bet_1.00")
    kb.button(text="5.00 $", callback_data=f"{prefix}_bet_5.00")
    
    # Кнопка повтора последней ставки
    kb.button(text=f"🔄 Повторить {last_bet:.2f} $", callback_data=f"{prefix}_bet_{last_bet:.2f}")
    kb.button(text="🔙 Назад", callback_data=back)
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()

def result_menu(replay: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Играть снова", callback_data=replay)
    kb.button(text="🔙 В меню", callback_data="play_menu")
    kb.adjust(1, 1)
    return kb.as_markup()

def sub_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Подписаться на канал", url="https://t.me/xlinewin_news")
    kb.button(text="🔄 Проверить подписку", callback_data="check_sub")
    kb.adjust(1, 1)
    return kb.as_markup()
