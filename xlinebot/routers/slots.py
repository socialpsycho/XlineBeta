import asyncio
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

from ..db import get_user, place_bet, credit_win, record_loss, is_maintenance
from ..keyboards import bet_menu, play_menu
from ..states import GameStates
from ..games.layouts import spin_slots

router = Router()
games = {}

def calculate_slots_payout(bet: float, result: list[str]) -> tuple[float, str]:
    if result[0] == result[1] == result[2]:
        sym = result[0]
        if sym == "7️⃣": return round(bet * 50, 2), "ДЖЕКПОТ! Три семерки!"
        if sym == "💎": return round(bet * 20, 2), "Три бриллианта!"
        if sym == "🔔": return round(bet * 10, 2), "Три колокола!"
        if sym == "🍋": return round(bet * 5, 2), "Три лимона!"
        if sym == "🍒": return round(bet * 4, 2), "Три вишни!"
    
    if result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        return bet, "Два одинаковых — возврат ставки"
        
    return 0.0, "Повезет в следующий раз"

async def begin(message, uid, bet, edit=False):
    if is_maintenance():
        return await message.answer("🛠 <b>На техобслуживании. Заходите позже.</b>", parse_mode="HTML")

    try:
        place_bet(uid, bet)
    except ValueError as e:
        return await message.answer(str(e))
        
    games[uid] = {"bet": bet, "busy": False}
    
    text = f"🎰 <b>Слоты</b>\nСтавка: {bet:.2f} $\n\nНажми кнопку, чтобы крутить!"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🎰 Крутить!", callback_data="slots_spin")
    kb.button(text="ℹ️ Правила и выплаты", callback_data="slots_rules")
    kb.button(text="🔙 В меню", callback_data="play_menu")
    kb.adjust(1, 1, 1)
    
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data == "game_slots")
async def choose_slots(call: types.CallbackQuery, state: FSMContext):
    if is_maintenance():
        return await call.answer("🛠 На техобслуживании.", show_alert=True)
        
    uid = call.from_user.id
    balance, _, _, _, last_bet, _, _ = get_user(uid)
    await state.set_state(GameStates.waiting_slots_bet)
    await call.message.edit_text(
        f"🎰 <b>Слоты</b>\nБаланс: {balance:.2f} $\n\nВведи сумму ставки или выбери:", 
        parse_mode="HTML", 
        reply_markup=bet_menu("slots", last_bet, "play_menu")
    )
    await call.answer()

@router.message(GameStates.waiting_slots_bet)
async def custom_bet(message: types.Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", "."))
        if bet < 0.10:
            raise ValueError
    except (ValueError, AttributeError):
        return await message.answer("Введи число (например, 0.50 или 1.00). Минимум 0.10 $.")
    await state.clear()
    await begin(message, message.from_user.id, bet)

@router.callback_query(F.data.startswith("slots_bet_"))
async def bet_btn(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        bet = float(call.data.rsplit("_", 1)[1])
    except ValueError:
        return await call.answer("Ошибка ставки.", show_alert=True)
    await begin(call.message, call.from_user.id, bet, edit=True)
    await call.answer()

@router.callback_query(F.data == "slots_spin")
async def spin(call: types.CallbackQuery):
    if is_maintenance():
        return await call.answer("🛠 На техобслуживании.", show_alert=True)
        
    uid = call.from_user.id
    game = games.get(uid)
    
    if not game:
        return await call.answer("Игра не найдена. Начни заново.", show_alert=True)
    if game.get("busy"):
        return await call.answer("Барабаны уже крутятся!", show_alert=True)
        
    game["busy"] = True
    bet = game["bet"]
    
    animation = ["🍒 | 🍋 | 🔔", "💎 | 🍒 | 7️⃣", "🔔 | 💎 | 🍋"]
    
    msg = await call.message.edit_text(
        f"🎰 <b>Слоты</b>\nСтавка: {bet:.2f} $\n\n[ {animation[0]} ]\nКрутим...", 
        parse_mode="HTML"
    )
    await asyncio.sleep(0.3)
    
    for frame in animation[1:]:
        await msg.edit_text(
            f"🎰 <b>Слоты</b>\nСтавка: {bet:.2f} $\n\n[ {frame} ]\nКрутим...", 
            parse_mode="HTML"
        )
        await asyncio.sleep(0.3)

    result = spin_slots()
    payout, desc = calculate_slots_payout(bet, result)
    
    if payout > 0:
        credit_win(uid, "slots", bet, payout, {"result": result})
    else:
        record_loss(uid, "slots", bet, {"result": result})
        
    del games[uid]
    balance = get_user(uid)[0]
    
    result_str = " | ".join(result)
    if payout >= bet * 4:
        status = f"🎉 <b>{desc}</b>\nВыигрыш: <b>+{payout:.2f} $</b>"
    elif payout > 0:
        status = f"🟡 <b>{desc}</b>\nВозврат: <b>+{payout:.2f} $</b>"
    else:
        status = f"❌ <b>{desc}</b>\nПотеряно: <b>-{bet:.2f} $</b>"
        
    text = f"🎰 <b>Слоты</b>\nСтавка: {bet:.2f} $\n\n[ {result_str} ]\n\n{status}\nБаланс: {balance:.2f} $"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Крутить снова", callback_data=f"slots_bet_{bet:.2f}")
    kb.button(text="🔙 В меню", callback_data="play_menu")
    kb.adjust(1, 1)
    
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data == "slots_rules")
async def slots_rules(call: types.CallbackQuery):
    text = (
        "ℹ️ <b>Правила игры в Слоты</b>\n\n"
        "Твоя задача — собрать 3 одинаковых символа на барабанах. "
        "Чем реже символ, тем выше выплата.\n\n"
        "💰 <b>Таблица выплат:</b>\n"
        "7️⃣ 7️⃣ 7️⃣ — <b>x50</b>\n"
        "💎 💎 💎 — <b>x20</b>\n"
        "🔔 🔔 🔔 — <b>x10</b>\n"
        "🍋 🍋 🍋 — <b>x5</b>\n"
        "🍒 🍒 🍒 — <b>x4</b>\n"
        "Любые 2 одинаковых — <b>возврат ставки (x1)</b>\n"
        "Без совпадений — <b>проигрыш</b>\n\n"
        "Шанс на джекпот (семерки) — 1 к 8000. Испытай удачу!"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🎰 Начать игру", callback_data="game_slots")
    kb.button(text="🔙 В меню", callback_data="play_menu")
    kb.adjust(1, 1)
    
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await call.answer()
