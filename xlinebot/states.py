from aiogram.fsm.state import State, StatesGroup

class WalletStates(StatesGroup):
    waiting_deposit_amount = State()
    waiting_crypto_amount = State()
    # --- НОВОЕ ДЛЯ ВЫВОДА ---
    waiting_withdraw_amount = State()   # Ввод суммы (звезд)
    waiting_withdraw_username = State() # Ввод юзернейма (для звезд)
    waiting_withdraw_wallet = State()   # Ввод адреса (для USDT)

class AdminStates(StatesGroup):
    waiting_give_amount = State()
    waiting_take_amount = State()
    waiting_ban_reason = State()
    waiting_broadcast = State()
    waiting_promo_code = State()
    waiting_promo_amount = State()
    waiting_promo_uses = State()
    waiting_ticket_reason = State()

class PromoStates(StatesGroup):
    waiting_promo = State()
    
class SupportStates(StatesGroup):
    waiting_message = State()
