import logging
from datetime import datetime, timezone
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, LabeledPrice, PreCheckoutQuery, Message
from aiocryptopay import AioCryptoPay, Networks
from aiogram.exceptions import TelegramBadRequest

from ..db import (
    get_user, add_balance, get_max_win, get_history, get_ban_reason, 
    use_promo, create_withdrawal, create_ticket, get_active_ticket_by_user,
    is_maintenance, get_deposit_history, get_withdraw_history, get_promo_history,
    register_user, is_withdraw_blocked, has_real_deposit
)
from ..keyboards import main_menu, play_menu, sub_menu
from ..config import ADMIN_ID, LOG_CHAT_ID, CRYPTOBOT_TOKEN, SUPPORT_CHAT_ID
from ..states import PromoStates, WalletStates, SupportStates
from ..utils import check_sub

router = Router()
crypto = AioCryptoPay(token=CRYPTOBOT_TOKEN, network=Networks.MAIN_NET)

# --- ПАКЕТЫ ЗВЕЗД ---
STAR_RATE = 0.011

STAR_PACKAGES = {
    100: 1.10,     
    150: 1.65,     
    500: 5.50,     
    1000: 11.00,   
}

def main_reply_menu(user_id: int) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="🎰 Играть")
    kb.button(text="💼 Кошелёк")
    kb.button(text="👤 Профиль")
    
    if user_id == ADMIN_ID:
        kb.button(text="👑 Админка")
        kb.adjust(2, 2)
    else:
        kb.adjust(2, 1)
        
    return kb.as_markup(resize_keyboard=True, input_field_placeholder="Выбери действие...")

@router.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    register_user(uid, message.from_user.username)
    balance, wins, losses, wagered, _, _, status = get_user(uid)
    
    if status == "banned":
        reason = get_ban_reason(uid)
        text = "⛔ <b>Ты забанен в этом боте.</b>"
        if reason: text += f"\n\n<b>Причина:</b> {reason}"
        return await message.answer(text, parse_mode="HTML")
    if status == "frozen":
        reason = get_ban_reason(uid)
        text = "🧊 <b>Твой аккаунт заморожен.</b>"
        if reason: text += f"\n\n<b>Причина:</b> {reason}"
        return await message.answer(text, parse_mode="HTML")

    if not await check_sub(message.bot, uid):
        return await message.answer(
            "👋 Привет! Чтобы начать играть, подпишись на наш канал.\n\n"
            "Нажми кнопку ниже, а затем 'Проверить подписку'.",
            reply_markup=sub_menu()
        )

    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\nДобро пожаловать в Xline.", 
        reply_markup=main_reply_menu(uid)
    )

@router.callback_query(F.data == "check_sub")
async def check_sub_callback(call: types.CallbackQuery):
    if await check_sub(call.bot, call.from_user.id):
        await call.message.edit_text(
            "✅ <b>Подписка подтверждена!</b>\nТеперь тебе доступны все игры.", 
            parse_mode="HTML",
            reply_markup=main_menu(call.from_user.id)
        )
        await call.message.answer("Главное меню активировано.", reply_markup=main_reply_menu(call.from_user.id))
    else:
        await call.answer("❌ Ты всё ещё не подписан на канал!", show_alert=True)

@router.message(F.text == "🎰 Играть")
async def reply_play(message: types.Message, state: FSMContext):
    await state.clear()
    if not await check_sub(message.bot, message.from_user.id):
        return await message.answer("⛔ Для доступа к играм подпишись на канал!", reply_markup=sub_menu())
        
    if is_maintenance():
        return await message.answer("🛠 <b>Казино на техобслуживании.</b>\nСкоро вернемся!", parse_mode="HTML")
        
    await message.answer("🎮 Выбери игру:", reply_markup=play_menu())

@router.message(F.text == "💼 Кошелёк")
async def reply_wallet(message: types.Message):
    balance = get_user(message.from_user.id)[0]
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Пополнить", callback_data="deposit")
    kb.button(text="📤 Вывести", callback_data="withdraw")
    kb.button(text="📜 История", callback_data="wallet_history_menu")
    kb.adjust(1, 1, 1)
    await message.answer(
        f"💼 <b>Кошелёк</b>\n\nБаланс: <b>{balance:.2f} $</b>", 
        parse_mode="HTML", reply_markup=kb.as_markup()
    )

@router.message(F.text == "👤 Профиль")
async def reply_profile(message: types.Message):
    uid = message.from_user.id
    balance, wins, losses, wagered, _, _, _ = get_user(uid)
    total = wins + losses
    rate = wins / total * 100 if total else 0
    max_win = get_max_win(uid)
    
    if wagered < 10: rank = "🥉 Новичок"
    elif wagered < 100: rank = "🥈 Любитель"
    elif wagered < 500: rank = "🥇 Профи"
    elif wagered < 5000: rank = "🏆 Хайроллер"
    else: rank = "💎 Казино-Магнат"

    text = (
        f"👤 <b>Твой профиль</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"🏅 Ранг: <b>{rank}</b>\n"
        f"💰 Баланс: <b>{balance:.2f} $</b>\n"
        f"🏆 Рекордный выигрыш: <b>{max_win:.2f} $</b>\n"
        f"📈 WinRate: <b>{rate:.0f}%</b>\n"
        f"🎮 Игр: <b>{total}</b>\n"
        f"💸 Всего поставлено: <b>{wagered:.2f} $</b>"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="📜 История игр", callback_data="game_history")
    kb.button(text="🎁 Промокод", callback_data="enter_promo")
    kb.button(text="🆘 Поддержка", callback_data="support")
    kb.adjust(2, 1)
    
    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data == "main_menu")
async def main(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Главное меню:", reply_markup=main_menu(call.from_user.id))
    await call.answer()

@router.callback_query(F.data == "play_menu")
async def games(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    if not await check_sub(call.bot, call.from_user.id):
        return await call.answer("⛔ Для доступа к играм подпишись на канал!", show_alert=True)
        
    if is_maintenance():
        return await call.answer("🛠 Казино на техобслуживании.", show_alert=True)
        
    await call.message.edit_text("🎮 Выбери игру:", reply_markup=play_menu())
    await call.answer()

@router.callback_query(F.data == "profile")
async def profile(call: types.CallbackQuery):
    uid = call.from_user.id
    balance, wins, losses, wagered, _, _, _ = get_user(uid)
    total = wins + losses
    rate = wins / total * 100 if total else 0
    max_win = get_max_win(uid)
    
    if wagered < 10: rank = "🥉 Новичок"
    elif wagered < 100: rank = "🥈 Любитель"
    elif wagered < 500: rank = "🥇 Профи"
    elif wagered < 5000: rank = "🏆 Хайроллер"
    else: rank = "💎 Казино-Магнат"

    text = (
        f"👤 <b>Твой профиль</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"🏅 Ранг: <b>{rank}</b>\n"
        f"💰 Баланс: <b>{balance:.2f} $</b>\n"
        f"🏆 Рекордный выигрыш: <b>{max_win:.2f} $</b>\n"
        f"📈 WinRate: <b>{rate:.0f}%</b>\n"
        f"🎮 Игр: <b>{total}</b>\n"
        f"💸 Всего поставлено: <b>{wagered:.2f} $</b>"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="📜 История игр", callback_data="game_history")
    kb.button(text="🎁 Промокод", callback_data="enter_promo")
    kb.button(text="🆘 Поддержка", callback_data="support")
    kb.button(text="🔙 Назад", callback_data="main_menu")
    kb.adjust(2, 2)
    
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data == "game_history")
async def game_history(call: types.CallbackQuery):
    uid = call.from_user.id
    history = get_history(uid, limit=5)
    
    if not history:
        text = "📜 <b>История игр</b>\n\nТы ещё не играл. Самое время начать!"
    else:
        text = "📜 <b>История игр (последние 5)</b>\n\n"
        for game, result, bet, payout in history:
            game_name = {"mines": "💣 Мины", "tower": "🗼 Башня", "rocket": "🚀 Ракета", "slots": "🎰 Слоты", "blackjack": "🃏 Блэкджек"}.get(game, game.capitalize())
            if result == "win": res_text = f"✅ Выигрыш: <b>+{payout:.2f} $</b>"
            elif result == "loss": res_text = f"❌ Проигрыш: <b>-{bet:.2f} $</b>"
            elif result == "cashout": res_text = f"💰 Забрано: <b>+{payout:.2f} $</b>"
            elif result == "promo": res_text = f"🎁 Промокод: <b>+{payout:.2f} $</b>"
            else: res_text = f"🔹 {result.capitalize()}"
            text += f"{game_name} | {res_text}\n"
            
    kb = InlineKeyboardBuilder().button(text="🔙 Назад в профиль", callback_data="profile")
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data == "wallet")
async def wallet(call: types.CallbackQuery):
    balance = get_user(call.from_user.id)[0]
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Пополнить", callback_data="deposit")
    kb.button(text="📤 Вывести", callback_data="withdraw")
    kb.button(text="📜 История", callback_data="wallet_history_menu")
    kb.button(text="🔙 Назад", callback_data="main_menu")
    kb.adjust(1, 1, 1, 1)
    await call.message.edit_text(
        f"💼 <b>Кошелёк</b>\n\nБаланс: <b>{balance:.2f} $</b>", 
        parse_mode="HTML", reply_markup=kb.as_markup()
    )
    await call.answer()

# --- ИСТОРИЯ КОШЕЛЬКА ---
@router.callback_query(F.data == "wallet_history_menu")
async def wallet_history_menu(call: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="⬇️ Пополнения", callback_data="hist_deposits")
    kb.button(text="⬆️ Выводы", callback_data="hist_withdraws")
    kb.button(text="🎁 Промокоды", callback_data="hist_promos")
    kb.button(text="🔙 Назад", callback_data="wallet")
    kb.adjust(2, 1, 1)
    await call.message.edit_text(
        "📜 <b>История кошелька</b>\n\nВыбери раздел:", 
        parse_mode="HTML", reply_markup=kb.as_markup()
    )
    await call.answer()

@router.callback_query(F.data == "hist_deposits")
async def hist_deposits(call: types.CallbackQuery):
    history = get_deposit_history(call.from_user.id, limit=10)
    if not history:
        text = "📜 <b>Пополнения</b>\n\nПополнений пока не было."
    else:
        text = "📜 <b>Последние пополнения</b>\n\n"
        for amount, desc, date_str in history:
            date_short = date_str[5:16].replace('T', ' ')
            desc_clean = "Пополнение" if "Пополнение" in desc else desc
            text += f"➕ <b>+{amount:.2f} $</b> ({desc_clean})\n   <i>{date_short}</i>\n"
    kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="wallet_history_menu")
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data == "hist_withdraws")
async def hist_withdraws(call: types.CallbackQuery):
    history = get_withdraw_history(call.from_user.id, limit=10)
    if not history:
        text = "📜 <b>Выводы</b>\n\nВыводов пока не было."
    else:
        text = "📜 <b>Последние выводы</b>\n\n"
        for amount, method, status, destination, date_str in history:
            date_short = date_str[5:16].replace('T', ' ')
            status_text = "✅ Выплачено" if status == "paid" else ("❌ Отклонено" if status == "rejected" else "⏳ В обработке")
            method_text = "USDT" if method == "crypto" else "Звезды"
            text += f"➖ <b>{amount:.2f} $</b> ({method_text})\n   <i>{status_text} | {date_short}</i>\n"
    kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="wallet_history_menu")
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data == "hist_promos")
async def hist_promos(call: types.CallbackQuery):
    history = get_promo_history(call.from_user.id, limit=10)
    if not history:
        text = "📜 <b>Промокоды</b>\n\nАктивированных промокодов нет."
    else:
        text = "📜 <b>Промокоды</b>\n\n"
        for amount, details_json, date_str in history:
            date_short = date_str[5:16].replace('T', ' ')
            text += f"🎁 <b>+{amount:.2f} $</b> <i>({date_short})</i>\n"
    kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="wallet_history_menu")
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await call.answer()

# --- ПОПОЛНЕНИЕ ---
@router.callback_query(F.data == "deposit")
async def deposit_start(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="⭐ Telegram Stars", callback_data="dep_stars")
    kb.button(text="🪙 CryptoBot", callback_data="dep_crypto")
    kb.button(text="🏦 Купить USDT за RUB", url="https://t.me/laveshka?startapp=buy")
    kb.button(text="🔙 Назад", callback_data="wallet")
    kb.adjust(2, 1, 1)
    
    await call.message.edit_text(
        "💳 <b>Пополнение</b>\n\nВыбери способ оплаты:", 
        parse_mode="HTML", reply_markup=kb.as_markup()
    )
    await call.answer()

# --- СТАРСЫ (ПАКЕТЫ) ---
@router.callback_query(F.data == "dep_stars")
async def dep_stars(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    for stars, dollars in STAR_PACKAGES.items():
        kb.button(text=f"{stars} ⭐", callback_data=f"buy_stars_{stars}")
    kb.button(text="✍️ Ввести свою сумму", callback_data="stars_custom")
    kb.button(text="🔙 Назад", callback_data="deposit")
    kb.adjust(2, 2, 1, 1)
    
    text = (
        "⭐ <b>Пополнение (Telegram Stars)</b>\n\n"
        "Выбери желаемый пакет:"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data == "stars_custom")
async def stars_custom(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(WalletStates.waiting_deposit_amount)
    kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="dep_stars")
    await call.message.edit_text(
        "⭐ <b>Своя сумма</b>\n\nВведи сумму в ⭐ (минимум 100):", 
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await call.answer()

@router.message(WalletStates.waiting_deposit_amount)
async def custom_stars_amount(message: types.Message, state: FSMContext):
    try: await message.delete()
    except: pass
    
    if not message.text or not message.text.isdigit(): 
        return await message.answer("Введи целое число.")
    
    stars_amount = int(message.text)
    if stars_amount < 100: 
        return await message.answer("Минимальная сумма — 100 ⭐.")
    
    await state.clear()
    dollars_amount = round(stars_amount * STAR_RATE, 2)
    
    await message.answer_invoice(
        title="Пополнение баланса", 
        description=f"{stars_amount} Telegram Stars ➔ {dollars_amount:.2f} $ на баланс Xline после подтверждения поддержкой.",
        payload=f"dep_{dollars_amount}", provider_token="", currency="XTR",
        prices=[LabeledPrice(label=f"Пакет {stars_amount} ⭐", amount=stars_amount)],
        reply_markup=InlineKeyboardBuilder().button(text=f"Заплатить {stars_amount} ⭐", pay=True).as_markup()
    )

@router.callback_query(F.data.startswith("buy_stars_"))
async def process_star_package(call: types.CallbackQuery):
    stars_amount = int(call.data.split("_")[2])
    dollars_amount = STAR_PACKAGES.get(stars_amount)
    
    if not dollars_amount:
        return await call.answer("Ошибка пакета.", show_alert=True)
        
    await call.message.answer_invoice(
        title="Пополнение баланса", 
        description=f"{stars_amount} Telegram Stars ➔ {dollars_amount:.2f} $ на баланс Xline после подтверждения поддержкой.",
        payload=f"dep_{dollars_amount}", provider_token="", currency="XTR",
        prices=[LabeledPrice(label=f"Пакет {stars_amount} ⭐", amount=stars_amount)],
        reply_markup=InlineKeyboardBuilder().button(text=f"Заплатить {stars_amount} ⭐", pay=True).as_markup()
    )
    await call.answer()

@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

@router.message(F.successful_payment)
async def success_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    uid = message.from_user.id
    if payload.startswith("dep_"):
        amount_dollars = float(payload.split("_")[1])
        add_balance(uid, amount_dollars, "Пополнение через TG Stars")
        kb = InlineKeyboardBuilder().button(text="🔙 В кошелёк", callback_data="wallet")
        await message.answer(f"✅ <b>Успешно!</b>\nБаланс пополнен на {amount_dollars:.2f} $.", parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data == "dep_crypto")
async def dep_crypto(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(WalletStates.waiting_crypto_amount)
    kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="deposit")
    text = ("🪙 <b>Пополнение (Крипта)</b>\n\n• Минимум: <b>2.00 $</b>\n• Курс: <b>1 $ = 1.36 USDT</b>\n\n— Введите сумму пополнения в $:")
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await call.answer()

@router.message(WalletStates.waiting_crypto_amount)
async def process_crypto_amount(message: types.Message, state: FSMContext):
    try: await message.delete()
    except: pass
        
    try:
        amount_dollars = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("Введи число (например, 2.50).")
        
    if amount_dollars < 2.0: 
        return await message.answer("Минимальная сумма — 2.00 $.")
    await state.clear()
    
    usdt_amount = round(amount_dollars * 1.36, 2)
    try:
        invoice = await crypto.create_invoice(asset="USDT", amount=str(usdt_amount), description=f"Пополнение Xline на {amount_dollars:.2f} $")
        pay_url = invoice.bot_invoice_url
        invoice_id = invoice.invoice_id
        
        kb = InlineKeyboardBuilder()
        kb.button(text="🪙 Оплатить в CryptoBot", url=pay_url)
        kb.button(text="🔄 Проверить оплату", callback_data=f"check_crypto_{invoice_id}_{amount_dollars}")
        kb.button(text="🔙 Назад", callback_data="wallet")
        kb.adjust(1, 1, 1)
        
        await message.answer(f"🧾 <b>Счет создан!</b>\n\nК оплате: <b>{usdt_amount:.2f} USDT</b>\nТы получишь: <b>{amount_dollars:.2f} $</b>\n\nНажми 'Оплатить', переведи крипту и нажми 'Проверить оплату'.", parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception as e:
        print(f"ОШИБКА CRYPTOBOT: {e}")
        await message.answer(f"❌ Ошибка создания счета:\n<code>{e}</code>", parse_mode="HTML")

@router.callback_query(F.data.startswith("check_crypto_"))
async def check_crypto(call: types.CallbackQuery):
    parts = call.data.split("_")
    invoice_id = int(parts[2])
    amount_dollars = float(parts[3])
    try:
        invoices = await crypto.get_invoices(invoice_ids=invoice_id)
        if invoices and invoices[0].status == "paid":
            uid = call.from_user.id
            add_balance(uid, amount_dollars, "Пополнение криптой")
            await call.message.edit_text(
                f"✅ <b>Оплата получена!</b>\nБаланс пополнен на {amount_dollars:.2f} $.", 
                parse_mode="HTML",
                reply_markup=InlineKeyboardBuilder().button(text="🔙 В кошелёк", callback_data="wallet").as_markup()
            )
            await call.answer("Успешно!")
        else:
            await call.answer("Оплата еще не поступила. Подожди пару минут и проверь снова.", show_alert=True)
    except Exception:
        await call.answer("Ошибка проверки. Попробуй позже.", show_alert=True)

# --- ВЫВОД ---
@router.callback_query(F.data == "withdraw")
async def withdraw_start(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    uid = call.from_user.id
    balance = get_user(uid)[0]
    
    if balance < 5.0: 
        return await call.answer("Минимальная сумма для вывода — 5.00 $", show_alert=True)
        
    if is_withdraw_blocked(uid):
        return await call.answer("⛔ Вывод заблокирован. Обратитесь в поддержку.", show_alert=True)
        
    if not has_real_deposit(uid):
        return await call.answer("⛔ Для вывода нужен хотя бы один депозит. Стартовый бонус вывести нельзя.", show_alert=True)

    kb = InlineKeyboardBuilder()
    kb.button(text="⭐ Stars (Скоро)", callback_data="w_type_stars_soon")
    kb.button(text="🪙 CryptoBot Чек", callback_data="w_type_crypto")
    kb.button(text="🔙 Отмена", callback_data="wallet")
    kb.adjust(2, 2)
    
    await call.message.edit_text(
        f"📤 <b>Заявка на вывод</b>\n\nБаланс: <b>{balance:.2f} $</b>\nМинимум для вывода: <b>5.00 $</b>\n\n— Выбери способ вывода:", 
        parse_mode="HTML", reply_markup=kb.as_markup()
    )
    await call.answer()

@router.callback_query(F.data == "w_type_stars_soon")
async def withdraw_stars_soon(call: types.CallbackQuery):
    await call.answer("⭐ Вывод звездами временно недоступен. Скоро добавим!", show_alert=True)

@router.callback_query(F.data == "w_type_crypto")
async def withdraw_crypto(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(method="crypto")
    await state.set_state(WalletStates.waiting_withdraw_amount)
    kb = InlineKeyboardBuilder().button(text="🔙 Отмена", callback_data="wallet")
    await call.message.edit_text(
        f"🪙 <b>Вывод USDT</b>\n\nВведи сумму в $ (минимум 5.00):", 
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await call.answer()

@router.message(WalletStates.waiting_withdraw_amount)
async def process_withdraw_amount(message: types.Message, state: FSMContext):
    try: await message.delete()
    except: pass
        
    try:
        amount_dollars = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("Введи число (например, 10.50).")
        
    uid = message.from_user.id
    if amount_dollars < 5.0: 
        return await message.answer("Минимальная сумма для вывода — 5.00 $.")
    balance = get_user(uid)[0]
    if balance < amount_dollars: 
        return await message.answer(f"Недостаточно средств! Твой баланс: {balance:.2f} $.")
        
    await state.update_data(amount=amount_dollars)
    data = await state.get_data()
    method = data.get("method")
    
    if method == "crypto":
        await state.clear()
        with_id = create_withdrawal(uid, amount_dollars, "crypto", "check")
        log_text = (
            f"📥 <b>НОВАЯ ЗАЯВКА НА ВЫВОД</b>\n\n"
            f"ID заявки: <code>{with_id}</code>\n"
            f"Юзер: <code>{uid}</code> ({message.from_user.first_name})\n"
            f"Сумма: <b>{amount_dollars:.2f} $</b>\n"
            f"Метод: <b>USDT (Чек CryptoBot)</b>"
        )
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Выплачено", callback_data=f"adm_appr_{with_id}")
        kb.button(text="❌ Отклонить", callback_data=f"adm_rej_{with_id}")
        kb.adjust(2)
        try:
            await message.bot.send_message(LOG_CHAT_ID, log_text, parse_mode="HTML", reply_markup=kb.as_markup())
        except: return await message.answer("⚠️ Ошибка отправки заявки.")
        await message.answer(f"✅ <b>Заявка создана!</b>\nСумма: <b>{amount_dollars:.2f} $</b>", parse_mode="HTML", reply_markup=InlineKeyboardBuilder().button(text="👤 В профиль", callback_data="profile").as_markup())

# --- ПРОМОКОДЫ, ПОДДЕРЖКА и т.д. ---
@router.callback_query(F.data == "enter_promo")
async def enter_promo_start(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(PromoStates.waiting_promo)
    kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="profile")
    await call.message.edit_text(
        "🎁 <b>Активация промокода</b>\n\nВведи код в чат, чтобы получить награду:", 
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await call.answer()

@router.message(PromoStates.waiting_promo)
async def enter_promo_process(message: types.Message, state: FSMContext):
    if not message.text: return await message.answer("Введи текстовый код.")
    await state.clear()
    amount = use_promo(message.from_user.id, message.text.strip())
    kb = InlineKeyboardBuilder().button(text="👤 В профиль", callback_data="profile")
    if amount:
        await message.answer(f"✅ <b>Промокод активирован!</b>\nТы получил: +{amount:.2f} $", parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await message.answer("❌ <b>Неверный промокод</b> или его лимит активаций исчерпан.", parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data == "support")
async def support_start_cb(call: types.CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    active_msg_id = get_active_ticket_by_user(uid)
    
    if active_msg_id:
        return await call.answer("⚠️ У вас уже есть открытый тикет! Дождитесь ответа администратора.", show_alert=True)
        
    await state.set_state(SupportStates.waiting_message)
    kb = InlineKeyboardBuilder().button(text="🔙 Отмена", callback_data="profile")
    await call.message.edit_text(
        "🆘 <b>Поддержка</b>\n\nНапиши свой вопрос или описание проблемы. Мы ответим тебе в этом чате.", 
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await call.answer()

@router.message(SupportStates.waiting_message)
async def support_send(message: types.Message, state: FSMContext):
    if not message.text: 
        return await message.answer("Пожалуйста, отправь текстовое сообщение.")
    
    uid = message.from_user.id
    active_msg_id = get_active_ticket_by_user(uid)
    
    if active_msg_id:
        user_text = f"📩 <b>Сообщение от юзера</b> <code>{uid}</code>\n\n{message.text}"
        try:
            await message.bot.send_message(SUPPORT_CHAT_ID, user_text, parse_mode="HTML", reply_to_message_id=active_msg_id)
            await message.answer("✅ Сообщение отправлено в поддержку.")
        except Exception as e:
            print(f"ОШИБКА ПОДДЕРЖКИ: {e}")
            await message.answer("⚠️ Ошибка отправки. Попробуй позже.")
        return

    support_kb = InlineKeyboardBuilder()
    support_kb.button(text="✅ Решено", callback_data=f"ticket_resolved_{uid}")
    support_kb.button(text="🔒 Закрыть (причина)", callback_data=f"close_ticket_{uid}")
    support_kb.adjust(2)

    text = (
        f"📩 <b>Тикет от юзера</b>\n\n"
        f"ID: <code>{uid}</code>\n"
        f"Юзер: @{message.from_user.username or 'нет'} ({message.from_user.first_name})\n\n"
        f"<b>Сообщение:</b>\n{message.text}"
    )
    
    try:
        sent_msg = await message.bot.send_message(SUPPORT_CHAT_ID, text, parse_mode="HTML", reply_markup=support_kb.as_markup())
        create_ticket(uid, sent_msg.message_id)
        await message.answer("✅ <b>Тикет создан!</b> Пиши сюда, сообщения будут лететь в поддержку.", parse_mode="HTML", reply_markup=InlineKeyboardBuilder().button(text="🔙 Выйти из поддержки", callback_data="profile").as_markup())
    except Exception as e:
        print(f"ОШИБКА ПОДДЕРЖКИ: {e}")
        await message.answer("⚠️ Ошибка отправки. Попробуй позже.")
