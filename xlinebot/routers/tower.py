from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from ..db import get_user, place_bet, credit_win, record_loss, record_cashout, save_tower_diff, is_maintenance
from ..keyboards import bet_menu, play_menu
from ..states import GameStates
from ..games.layouts import generate_tower_layout

router = Router()
games = {}
DIFFICULTY = {"easy": (4, 1, 9), "medium": (3, 1, 9), "hard": (2, 1, 9), "expert": (3, 2, 5), "master": (4, 3, 4)}
HOUSE_EDGE = 0.97

def render(game, reveal=False):
    kb = InlineKeyboardBuilder()
    levels = game["levels"]
    cells = game["cells"]
    
    for level in range(levels - 1, -1, -1):
        if level < len(game["opened"]):
            chosen = game["opened"][level]
            for i in range(cells):
                label = "💎" if i == chosen else ("💣" if reveal and i in game["bombs"][level] else "⬛")
                kb.button(text=label, callback_data="ignore")
        elif reveal:
            for i in range(cells):
                label = "💣" if i in game["bombs"][level] else "⬜"
                kb.button(text=label, callback_data="ignore")
        elif level == len(game["opened"]):
            for i in range(cells):
                kb.button(text="⬜", callback_data=f"tower_open_{level}_{i}")
        else:
            for i in range(cells):
                kb.button(text="🔒", callback_data="ignore")
                
    if reveal:
        kb.button(text="🔄 Играть снова", callback_data="tower_replay")
        kb.button(text="🔙 В меню", callback_data="play_menu")
        kb.adjust(*([cells] * levels), 1, 1)
    else:
        kb.button(text=f"💰 Забрать {game['bet'] * game['multiplier']:.2f} $", callback_data="tower_cashout")
        kb.button(text="🔙 Сдаться", callback_data="tower_cancel")
        kb.adjust(*([cells] * levels), 1, 1)
    return kb.as_markup()

async def begin(message, uid, bet, diff, edit=False):
    if is_maintenance():
        return await message.answer("🛠 <b>На техобслуживании. Заходите позже.</b>", parse_mode="HTML")

    try: 
        place_bet(uid, bet)
    except ValueError as e: 
        return await message.answer(str(e))
        
    cells, bombs, levels = DIFFICULTY[diff]
    prob_win_floor = (cells - bombs) / cells
    base = (1 / prob_win_floor) * HOUSE_EDGE
    
    game = {
        "bet": bet, "diff": diff, "cells": cells, "bombs_count": bombs,
        "levels": levels, "opened": [], "bombs": generate_tower_layout(cells, bombs, levels),
        "base": base, "multiplier": base, "busy": False
    }
    games[uid] = game
    
    text = f"🗼 Ставка: {bet:.2f} $\nКоэффициент: x{base:.2f}\n\nПоднимайся!"
    if edit: 
        await message.edit_text(text, reply_markup=render(game))
    else: 
        await message.answer(text, reply_markup=render(game))

@router.callback_query(F.data == "game_tower")
async def choose(call: types.CallbackQuery):
    if is_maintenance():
        return await call.answer("🛠 На техобслуживании.", show_alert=True)

    kb = InlineKeyboardBuilder()
    for key, label in [("easy", "Лёгкая"), ("medium", "Средняя"), ("hard", "Сложная"), ("expert", "Эксперт"), ("master", "Мастер")]:
        kb.button(text=label, callback_data=f"tower_diff_{key}")
    kb.button(text="🔙 Назад", callback_data="play_menu")
    kb.adjust(3, 2, 1)
    
    await call.message.edit_text(
        "🗼 <b>Tower — выбери сложность</b>\n\n"
        "Лёгкая: 4 клетки, 1 бомба, 9 этажей\n"
        "Средняя: 3 клетки, 1 бомба, 9 этажей\n"
        "Сложная: 2 клетки, 1 бомба, 9 этажей\n"
        "Эксперт: 3 клетки, 2 бомбы, 5 этажей\n"
        "Мастер: 4 клетки, 3 бомбы, 4 этажа",
        parse_mode="HTML", reply_markup=kb.as_markup()
    )
    await call.answer()

@router.callback_query(F.data.startswith("tower_diff_"))
async def diff(call: types.CallbackQuery, state: FSMContext):
    key = call.data.rsplit("_", 1)[1]
    await state.update_data(tower_diff=key)
    await state.set_state(GameStates.waiting_tower_bet)
    
    uid = call.from_user.id
    balance, _, _, _, last, _, _ = get_user(uid)
    
    save_tower_diff(uid, key)
    
    await call.message.edit_text(
        f"Сложность: {key.upper()}\nБаланс: {balance:.2f} $\nВведи ставку:",
        reply_markup=bet_menu("tower", last, "game_tower")
    )
    await call.answer()

@router.message(GameStates.waiting_tower_bet)
async def custom(message: types.Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", "."))
        if bet < 0.10: # Минимум 10 центов
            raise ValueError
    except (ValueError, AttributeError):
        return await message.answer("Введи число (например, 0.50 или 1.00). Минимум 0.10 $.")
        
    data = await state.get_data()
    diff = data.get("tower_diff", "easy")
    await state.clear()
    await begin(message, message.from_user.id, bet, diff)

@router.callback_query(F.data.startswith("tower_bet_"))
async def bet_btn(call: types.CallbackQuery, state: FSMContext):
    try:
        bet = float(call.data.rsplit("_", 1)[1])
    except ValueError:
        return await call.answer("Ошибка ставки.", show_alert=True)
        
    data = await state.get_data()
    diff = data.get("tower_diff", "easy")
    await state.clear()
    await begin(call.message, call.from_user.id, bet, diff, True)
    await call.answer()

@router.callback_query(F.data.startswith("tower_open_"))
async def open_cell(call: types.CallbackQuery):
    if is_maintenance():
        return await call.answer("🛠 На техобслуживании.", show_alert=True)

    uid = call.from_user.id
    game = games.get(uid)
    if not game: 
        return await call.answer("Игра завершена.", show_alert=True)
    if game.get("busy"): 
        return await call.answer("Подожди...", show_alert=True)
        
    game["busy"] = True
    
    parts = call.data.split("_")
    level, idx = int(parts[2]), int(parts[3])
    if level != len(game["opened"]): 
        game["busy"] = False
        return await call.answer("Этот этаж сейчас недоступен.", show_alert=True)
        
    if idx in game["bombs"][level]:
        game["hit"] = {"level": level, "cell": idx}
        record_loss(uid, "tower", game["bet"], {"bombs": game["bombs"], "opened": game["opened"], "hit": game["hit"]})
        del games[uid]
        await call.message.edit_text(
            f"💥 <b>Бомба на этаже {level+1}!</b>\nПотеряно: {game['bet']:.2f} $\n\nКарта башни:",
            parse_mode="HTML", reply_markup=render(game, True)
        )
        return await call.answer()
        
    game["opened"].append(idx)
    game["multiplier"] *= game["base"]
    
    if len(game["opened"]) == game["levels"]:
        payout = round(game["bet"] * game["multiplier"], 2)
        credit_win(uid, "tower", game["bet"], payout, {"bombs": game["bombs"], "opened": game["opened"]})
        del games[uid]
        await call.message.edit_text(
            f"🏆 <b>Ты дошёл до вершины!</b>\nВыигрыш: {payout:.2f} $\n\nКарта башни:",
            parse_mode="HTML", reply_markup=render(game, True)
        )
        return await call.answer()
        
    game["busy"] = False
    await call.message.edit_text(
        f"🗼 Этаж: {level+1}/{game['levels']}\nСтавка: {game['bet']:.2f} $\nКэф: x{game['multiplier']:.2f}",
        reply_markup=render(game)
    )
    await call.answer()

@router.callback_query(F.data == "tower_cashout")
async def cashout(call: types.CallbackQuery):
    if is_maintenance():
        return await call.answer("🛠 На техобслуживании.", show_alert=True)

    uid = call.from_user.id
    game = games.get(uid)
    if not game or not game["opened"]: 
        return await call.answer("Пройди хотя бы один этаж.", show_alert=True)
    if game.get("busy"): 
        return await call.answer("Подожди...", show_alert=True)
        
    game = games.pop(uid) 
    
    payout = round(game["bet"] * game["multiplier"], 2)
    record_cashout(uid, "tower", game["bet"], payout, {"bombs": game["bombs"], "opened": game["opened"]})
    
    await call.message.edit_text(
        f"💰 <b>Забрано: {payout:.2f} $</b>\n\nКарта башни:",
        parse_mode="HTML", reply_markup=render(game, True)
    )
    await call.answer()

@router.callback_query(F.data == "tower_cancel")
async def cancel(call: types.CallbackQuery):
    game = games.pop(call.from_user.id, None)
    if game: 
        record_loss(call.from_user.id, "tower", game["bet"], {"bombs": game["bombs"], "opened": game["opened"], "cancelled": True})
    await call.message.edit_text("🎮 Выбери игру:", reply_markup=play_menu())
    await call.answer()

@router.callback_query(F.data == "tower_replay")
async def replay(call: types.CallbackQuery):
    if is_maintenance():
        return await call.answer("🛠 На техобслуживании.", show_alert=True)

    uid = call.from_user.id
    balance, _, _, _, bet, last_diff, _ = get_user(uid)
    
    if balance < bet: 
        return await call.answer(f"Мало средств! Нужно {bet:.2f} $", show_alert=True)
        
    await begin(call.message, uid, bet, last_diff or "easy", True)
    await call.answer()
