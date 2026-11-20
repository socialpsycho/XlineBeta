from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..db import get_user, place_bet, credit_win, record_loss, record_cashout, is_maintenance
from ..keyboards import bet_menu, play_menu
from ..states import GameStates
from ..games.layouts import generate_mines

router = Router()
games = {}

TOTAL_CELLS = 25
HOUSE_EDGE = 0.97

def get_multiplier(opened_count, mines, total_cells=TOTAL_CELLS):
    safe_left = total_cells - mines - opened_count
    total_left = total_cells - opened_count
    if safe_left <= 0 or total_left <= 0:
        return 0.0
    
    prob_survive_all = 1.0
    for i in range(opened_count):
        prob_survive_all *= (total_cells - mines - i) / (total_cells - i)
        
    fair_mult = 1 / prob_survive_all
    return fair_mult * HOUSE_EDGE

def board(game, reveal=False, hit=None):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[])
    row = []
    for i in range(TOTAL_CELLS):
        if i in game["mines"] and reveal: 
            label = "💥" if i == hit else "💣"
        elif i in game["opened"]: 
            label = "💎"
        elif reveal: 
            label = "⬜"
        else: 
            label = "⬜"
            
        row.append(types.InlineKeyboardButton(
            text=label, 
            callback_data=f"mine_open_{i}" if not reveal and i not in game["opened"] else "ignore"
        ))
        
        if len(row) == 5: 
            kb.inline_keyboard.append(row)
            row = []
            
    if row: 
        kb.inline_keyboard.append(row)
        
    if not reveal:
        kb.inline_keyboard.append([
            types.InlineKeyboardButton(text=f"💰 Забрать {game['bet'] * game['multiplier']:.2f} $", callback_data="mine_cashout"), 
            types.InlineKeyboardButton(text="🔙 Сдаться", callback_data="mine_cancel")
        ])
    else:
        kb.inline_keyboard.append([
            types.InlineKeyboardButton(text="🔄 Играть снова", callback_data="mines_replay"), 
            types.InlineKeyboardButton(text="💣 Сменить мины", callback_data="game_mines")
        ])
        kb.inline_keyboard.append([
            types.InlineKeyboardButton(text="🔙 В меню", callback_data="play_menu")
        ])
    return kb

def start_kb(mines_count):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="💎 Играть", callback_data="mine_start_click"),
            types.InlineKeyboardButton(text=f"💣 Мин: {mines_count}", callback_data="ignore")
        ],
        [
            types.InlineKeyboardButton(text="⬅️ Назад", callback_data="play_menu")
        ]
    ])
    return kb

async def begin(message, uid, bet, mines_count, edit=False):
    if is_maintenance():
        return await message.answer("🛠 <b>На техобслуживании. Заходите позже.</b>", parse_mode="HTML")
        
    try: 
        place_bet(uid, bet)
    except ValueError as e:
        return await message.answer(str(e))
        
    games[uid] = {
        "bet": bet, 
        "mines_count": mines_count,
        "mines": generate_mines(mines_count),
        "opened": [], 
        "multiplier": 1.0, 
        "busy": False
    }
    
    text = f"💣 Ставка: {bet:.2f} $\n💥 Мин: {mines_count}\nКэф: x1.00"
    
    if edit: 
        await message.edit_text(text, reply_markup=start_kb(mines_count))
    else: 
        await message.answer(text, reply_markup=start_kb(mines_count))

@router.callback_query(F.data == "mine_start_click")
async def mine_start_click(call: types.CallbackQuery):
    uid = call.from_user.id
    game = games.get(uid)
    if not game:
        return await call.answer("Игра не найдена.", show_alert=True)
    
    await call.message.edit_text(
        f"💣 Ставка: {game['bet']:.2f} $\n💥 Мин: {game['mines_count']}\nКэф: x1.00\n\n<b>Твой ход! Открывай клетки.</b>", 
        parse_mode="HTML",
        reply_markup=board(game)
    )
    await call.answer("Погнали!")

@router.callback_query(F.data == "game_mines")
async def choose(call: types.CallbackQuery, state: FSMContext):
    if is_maintenance():
        return await call.answer("🛠 На техобслуживании.", show_alert=True)
    
    await state.clear()
    
    kb = InlineKeyboardBuilder()
    for i in range(5, 25):
        kb.button(text=f"💣 {i}", callback_data=f"mines_m_{i}")
    
    kb.button(text="🔙 Назад", callback_data="play_menu")
    kb.adjust(4) 
    
    await call.message.edit_text(
        "💥 <b>Выберите количество взрывчатки на поле:</b>", 
        parse_mode="HTML", 
        reply_markup=kb.as_markup()
    )
    await call.answer()

@router.callback_query(F.data.startswith("mines_m_"))
async def choose_mines(call: types.CallbackQuery, state: FSMContext):
    mines_count = int(call.data.rsplit("_", 1)[1])
    await state.update_data(mines_count=mines_count)
    await state.set_state(GameStates.waiting_mines_bet)
    
    _, _, _, _, last, _, _ = get_user(call.from_user.id)
    await call.message.edit_text(
        f"💣 <b>Mines</b>\n💥 Мин: {mines_count}\nБаланс: {get_user(call.from_user.id)[0]:.2f} $\n\nВведи ставку или выбери:", 
        parse_mode="HTML", 
        reply_markup=bet_menu("mines", last, "play_menu")
    )
    await call.answer()

@router.message(GameStates.waiting_mines_bet)
async def custom(message: types.Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", "."))
        if bet < 0.10: # Минимум 10 центов
            raise ValueError
    except (ValueError, AttributeError):
        return await message.answer("Введи число (например, 0.50 или 1.00). Минимум 0.10 $.")
        
    data = await state.get_data()
    mines_count = data.get("mines_count", 5)
    
    await state.clear()
    await begin(message, message.from_user.id, bet, mines_count)

@router.callback_query(F.data.startswith("mines_bet_"))
async def start_btn(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    mines_count = data.get("mines_count", 5)
    await state.clear()
    # Парсим дробное значение из callback_data
    bet = float(call.data.rsplit("_", 1)[1])
    await begin(call.message, call.from_user.id, bet, mines_count, True)
    await call.answer()

@router.callback_query(F.data.startswith("mine_open_"))
async def open_cell(call: types.CallbackQuery):
    if is_maintenance():
        return await call.answer("🛠 На техобслуживании.", show_alert=True)
        
    uid = call.from_user.id
    game = games.get(uid)
    if not game: 
        return await call.answer("Игра уже завершена.", show_alert=True)
    if game.get("busy"):
        return await call.answer("Подожди...", show_alert=True)
        
    game["busy"] = True
    idx = int(call.data.rsplit("_", 1)[1])
    
    if idx in game["opened"]: 
        game["busy"] = False
        return await call.answer()
        
    if idx in game["mines"]:
        record_loss(uid, "mines", game["bet"], {"bombs": game["mines"], "opened": game["opened"], "hit": idx})
        del games[uid]
        balance = get_user(uid)[0]
        await call.message.edit_text(
            f"💥 <b>БУМ!</b>\nПотеряно: {game['bet']:.2f} $\nБаланс: {balance:.2f} $\n\n💣 Все бомбы показаны:", 
            parse_mode="HTML", 
            reply_markup=board(game, True, idx)
        )
        return await call.answer()
        
    game["opened"].append(idx)
    game["multiplier"] = get_multiplier(len(game["opened"]), game["mines_count"])
    
    if len(game["opened"]) == TOTAL_CELLS - game["mines_count"]:
        payout = round(game["bet"] * game["multiplier"], 2)
        details = {"bombs": game["mines"], "opened": game["opened"]}
        credit_win(uid, "mines", game["bet"], payout, details)
        del games[uid]
        await call.message.edit_text(
            f"🏆 <b>Победа!</b>\nВыигрыш: {payout:.2f} $\n\n💣 Бомбы и свободные клетки:", 
            parse_mode="HTML", 
            reply_markup=board(game, True)
        )
        return await call.answer()
        
    game["busy"] = False
    await call.message.edit_text(
        f"💣 Ставка: {game['bet']:.2f} $\n💥 Мин: {game['mines_count']}\nКэф: x{game['multiplier']:.2f}", 
        reply_markup=board(game)
    )
    await call.answer()

@router.callback_query(F.data == "mine_cashout")
async def cashout(call: types.CallbackQuery):
    if is_maintenance():
        return await call.answer("🛠 На техобслуживании.", show_alert=True)
        
    uid = call.from_user.id
    game = games.get(uid)
    if not game or not game["opened"]: 
        return await call.answer("Сначала открой безопасную клетку.", show_alert=True)
    if game.get("busy"):
        return await call.answer("Подожди...", show_alert=True)
        
    game = games.pop(uid)
    payout = round(game["bet"] * game["multiplier"], 2)
    record_cashout(uid, "mines", game["bet"], payout, {"bombs": game["mines"], "opened": game["opened"]})
    
    await call.message.edit_text(
        f"💰 <b>Выигрыш: {payout:.2f} $</b>\n\n💣 Бомбы и свободные клетки:", 
        parse_mode="HTML", 
        reply_markup=board(game, True)
    )
    await call.answer()

@router.callback_query(F.data == "mine_cancel")
async def cancel(call: types.CallbackQuery):
    game = games.pop(call.from_user.id, None)
    if game: 
        record_loss(call.from_user.id, "mines", game["bet"], {"bombs": game["mines"], "opened": game["opened"], "cancelled": True})
    await call.message.edit_text("🎮 Выбери игру:", reply_markup=play_menu())
    await call.answer()

@router.callback_query(F.data == "mines_replay")
async def replay(call: types.CallbackQuery):
    if is_maintenance():
        return await call.answer("🛠 На техобслуживании.", show_alert=True)
        
    _, _, _, _, bet, _, _ = get_user(call.from_user.id)
    await begin(call.message, call.from_user.id, bet, 5, True)
    await call.answer()
