import asyncio
import random
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

from ..db import get_user, place_bet, credit_win, record_loss, is_maintenance
from ..keyboards import play_menu
from ..states import GameStates

router = Router()
rocket_games = {}

def generate_crash_point() -> float:
    r = random.random()
    if r < 0.03:
        return 1.00
    return round(0.97 / (1 - r), 2)

@router.callback_query(F.data == "game_rocket")
async def play_rocket(call: types.CallbackQuery, state: FSMContext):
    if is_maintenance():
        return await call.answer("🛠 На техобслуживании.", show_alert=True)

    user_id = call.from_user.id
    balance, _, _, _, last_bet, _, _ = get_user(user_id)
    
    await state.set_state(GameStates.waiting_rocket_bet)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="0.10 $", callback_data="rocket_bet_0.10")
    kb.button(text="0.50 $", callback_data="rocket_bet_0.50")
    kb.button(text="1.00 $", callback_data="rocket_bet_1.00")
    kb.button(text="5.00 $", callback_data="rocket_bet_5.00")
    kb.button(text=f"🔄 Повторить {last_bet:.2f} $", callback_data=f"rocket_bet_{last_bet:.2f}")
    kb.button(text="🔙 Назад", callback_data="play_menu")
    kb.adjust(2, 2, 1, 1)
    
    await call.message.edit_text(
        f"🚀 <b>Ракета</b>\nТвой баланс: {balance:.2f} $\n\nВведи сумму ставки числом или выбери из кнопок:", 
        parse_mode="HTML", 
        reply_markup=kb.as_markup()
    )
    await call.answer()

@router.message(GameStates.waiting_rocket_bet)
async def rocket_custom_bet(message: types.Message, state: FSMContext):
    if is_maintenance():
        return await message.answer("🛠 <b>На техобслуживании.</b>", parse_mode="HTML")

    try:
        bet = float(message.text.replace(",", "."))
        if bet < 0.10:
            raise ValueError
    except (ValueError, AttributeError):
        return await message.answer("Введи число (например, 0.50 или 1.00). Минимум 0.10 $.")
    
    user_id = message.from_user.id
    balance = get_user(user_id)[0]
    if balance < bet: 
        return await message.answer(f"Мало средств! Баланс: {balance:.2f} $")
    
    await state.clear()
    await start_rocket_game_msg(message, user_id, bet)

@router.callback_query(F.data.startswith("rocket_bet_"))
async def rocket_start_btn(call: types.CallbackQuery, state: FSMContext):
    if is_maintenance():
        return await call.answer("🛠 На техобслуживании.", show_alert=True)

    user_id = call.from_user.id
    try:
        bet = float(call.data.split("_")[2])
    except ValueError:
        return await call.answer("Ошибка ставки.", show_alert=True)
        
    balance = get_user(user_id)[0]
    
    if balance < bet: 
        return await call.answer("Мало средств!", show_alert=True)
    
    await state.clear()
    await start_rocket_game_msg(call.message, user_id, bet)

async def start_rocket_game_msg(message_obj, user_id, bet):
    if is_maintenance():
        return await message_obj.answer("🛠 <b>На техобслуживании.</b>", parse_mode="HTML")

    try: 
        place_bet(user_id, bet)
    except ValueError as e: 
        return await message_obj.answer(str(e))
    
    crash_point = generate_crash_point()
    
    rocket_games[user_id] = {
        "bet": bet, 
        "multiplier": 1.0, 
        "crash_point": crash_point,
        "crashed": False, 
        "msg_id": None, 
        "chat_id": message_obj.chat.id
    }
    
    builder = InlineKeyboardBuilder()
    builder.button(text=f"💰 Забрать {bet:.2f} $", callback_data="rocket_cashout")
    
    text = f"🛫 <b>Взлетаем...</b>\nКэф: <b>x1.00</b>\n<code>[🚀▫️▫️▫️▫️▫️▫️▫️▫️▫️]</code>\n⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜"
    
    msg = await message_obj.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    rocket_games[user_id]["msg_id"] = msg.message_id
    asyncio.create_task(rocket_ticker(user_id, message_obj.bot))

async def rocket_ticker(user_id, bot):
    tick = 0
    while True:
        await asyncio.sleep(1.0)
        game = rocket_games.get(user_id)
        if not game or game["crashed"]: 
            break
        
        if game["multiplier"] >= game["crash_point"]:
            game["crashed"] = True
            del rocket_games[user_id]
            record_loss(user_id, "rocket", game["bet"], {"crash_at": game["multiplier"]})
            balance = get_user(user_id)[0]
            
            builder = InlineKeyboardBuilder()
            builder.button(text="🔄 Играть снова", callback_data="rocket_replay")
            builder.button(text="🔙 В меню", callback_data="play_menu")
            builder.adjust(1, 1)
            
            try:
                await bot.edit_message_text(
                    chat_id=game["chat_id"], message_id=game["msg_id"], 
                    text=f"💥 <b>КРАШ НА x{game['multiplier']:.2f}!</b>\nРакета взорвалась.\nПотеряно: {game['bet']:.2f} $\nБаланс: {balance:.2f} $", 
                    parse_mode="HTML", reply_markup=builder.as_markup()
                )
            except Exception: 
                pass
            break

        game["multiplier"] = round(game["multiplier"] + 0.12, 2)
        mult = game["multiplier"]
        tick += 1
        
        if mult < 1.5: status = "🛫 <b>Взлетаем...</b>"
        elif mult < 2.5: status = "✈️ <b>Набираем высоту!</b>"
        elif mult < 4.0: status = "🚀 <b>В стратосфере!</b>"
        else: status = "🔥 <b>КОСМОС! ЗАБИРАЙ!</b>"

        if tick % 2 == 0: kef_text = f"<b>x{mult:.2f}</b>"
        else: kef_text = f"<b><i>x{mult:.2f}</i></b>"

        pos = min(int((mult - 1) * 1.5), 9) 
        line = "▫️" * pos + "🚀" + "▫️" * (9 - pos)
        if mult > 2.0: line = "🔥" + line[1:]

        bars = int(min(mult * 1.5, 10))
        progress = "🟩" * bars + "⬜" * (10 - bars)

        builder = InlineKeyboardBuilder()
        builder.button(text=f"💰 Забрать {game['bet'] * mult:.2f} $", callback_data="rocket_cashout")
        
        text = f"{status}\n\nКэф: {kef_text}\n<code>[{line}]</code>\n{progress}"

        try:
            await bot.edit_message_text(
                chat_id=game["chat_id"], message_id=game["msg_id"],
                text=text, parse_mode="HTML", reply_markup=builder.as_markup()
            )
        except Exception: 
            pass

@router.callback_query(F.data == "rocket_cashout")
async def rocket_cashout(call: types.CallbackQuery):
    if is_maintenance():
        return await call.answer("🛠 На техобслуживании.", show_alert=True)

    user_id = call.from_user.id
    game = rocket_games.get(user_id)
    
    if not game or game["crashed"]:
        return await call.answer("Ракета уже взорвалась или игра не найдена!", show_alert=True)
        
    game["crashed"] = True
    win = round(game["bet"] * game["multiplier"], 2)
    credit_win(user_id, "rocket", game["bet"], win, {"cashed_out_at": game["multiplier"]})
    balance = get_user(user_id)[0]
    del rocket_games[user_id]
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Снова", callback_data="rocket_replay")
    builder.button(text="🔙 Меню", callback_data="play_menu")
    builder.adjust(1, 1)
    
    await call.message.edit_text(
        f"💰 <b>Успел!</b>\nЗабрал: {win:.2f} $ (x{game['multiplier']:.2f})\nБаланс: {balance:.2f} $", 
        parse_mode="HTML", reply_markup=builder.as_markup()
    )
    await call.answer()

@router.callback_query(F.data == "rocket_replay")
async def rocket_replay(call: types.CallbackQuery):
    if is_maintenance():
        return await call.answer("🛠 На техобслуживании.", show_alert=True)

    user_id = call.from_user.id
    balance, _, _, _, last_bet, _, _ = get_user(user_id)
    if balance < last_bet: 
        return await call.answer(f"Мало средств! Нужно {last_bet:.2f} $", show_alert=True)
    await start_rocket_game_msg(call.message, user_id, last_bet)
