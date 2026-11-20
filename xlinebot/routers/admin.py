import asyncio
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from ..db import (
    get_user, add_balance, deduct_balance, get_all_users, 
    set_user_status, get_ban_reason, connection, create_promo,
    approve_withdrawal, reject_withdrawal, get_ticket_user, close_ticket_db,
    is_maintenance, set_maintenance, clear_history_and_promos,
    is_withdraw_blocked, set_withdraw_block, delete_user,
    get_all_deposits, get_all_withdrawals
)
from ..config import ADMIN_ID, SUPPORT_CHAT_ID
from ..states import AdminStates

router = Router()

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def admin_back_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 В админку", callback_data="admin_panel")
    return kb.as_markup()

# Вспомогательная функция для безопасного редактирования прямо в admin.py
async def safe_edit(message, text, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        elif "message can't be edited" in str(e) or "message to edit not found" in str(e):
            await message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            raise e

# --- ГЛАВНОЕ МЕНЮ АДМИНКИ ---
@router.message(F.text == "👑 Админка")
async def reply_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("У тебя нет прав.")
    
    text = "👑 <b>Админ-панель Xline</b>\n\nВыбери раздел:"
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика и История", callback_data="admin_stats_menu")
    kb.button(text="👥 Пользователи", callback_data="admin_users_menu")
    kb.button(text="⚙️ Управление ботом", callback_data="admin_manage_menu")
    kb.button(text="🔙 Назад в меню", callback_data="main_menu")
    kb.adjust(1, 1, 1, 1)
    
    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

@router.callback_query(F.data == "admin_panel")
async def admin_panel_btn(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("У тебя нет прав.", show_alert=True)
    
    text = "👑 <b>Админ-панель Xline</b>\n\nВыбери раздел:"
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика и История", callback_data="admin_stats_menu")
    kb.button(text="👥 Пользователи", callback_data="admin_users_menu")
    kb.button(text="⚙️ Управление ботом", callback_data="admin_manage_menu")
    kb.button(text="🔙 Назад в меню", callback_data="main_menu")
    kb.adjust(1, 1, 1, 1)
    
    await safe_edit(call.message, text, reply_markup=kb.as_markup())
    await call.answer()

# --- МЕНЮ СТАТИСТИКИ ---
@router.callback_query(F.data == "admin_stats_menu")
async def admin_stats_menu(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    
    text = "📊 <b>Статистика и История</b>\n\nВыбери что посмотреть:"
    kb = InlineKeyboardBuilder()
    kb.button(text="📈 Общая статистика", callback_data="admin_stats")
    kb.button(text="📥 История пополнений", callback_data="admin_hist_deposits")
    kb.button(text="📤 История выводов", callback_data="admin_hist_withdraws")
    kb.button(text="🕵️ Крупные выигрыши", callback_data="admin_big_wins")
    kb.button(text="🔙 Назад", callback_data="admin_panel")
    kb.adjust(1, 1, 1, 1, 1)
    
    await safe_edit(call.message, text, reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    
    with connection() as db:
        users_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_balance = db.execute("SELECT SUM(balance) FROM users").fetchone()[0] or 0.0
        total_wagered = db.execute("SELECT SUM(wagered) FROM users").fetchone()[0] or 0.0
        total_payouts = db.execute("SELECT SUM(payout) FROM game_history WHERE result IN ('win', 'cashout')").fetchone()[0] or 0.0

    profit = total_wagered - total_payouts
    rtp = (total_payouts / total_wagered * 100) if total_wagered > 0 else 0
    
    text = (
        f"📊 <b>Общая статистика казино</b>\n\n"
        f"👥 Игроков: {users_count}\n"
        f"💰 Баланс всех юзеров: {total_balance:.2f} $\n"
        f"📥 Оборот (всего поставлено): {total_wagered:.2f} $\n"
        f"📤 Выплачено (выигрыши): {total_payouts:.2f} $\n"
        f"💵 <b>Профит бота: {profit:.2f} $</b>\n"
        f"📈 <b>Фактический RTP: {rtp:.2f}%</b>"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🧹 Сброс статы", callback_data="admin_confirm_reset")
    kb.button(text="🔙 Назад", callback_data="admin_stats_menu")
    kb.adjust(1, 1)
    
    await safe_edit(call.message, text, reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data == "admin_hist_deposits")
async def admin_hist_deposits(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    
    deposits = get_all_deposits(limit=15)
    if not deposits:
        text = "📥 <b>История пополнений</b>\n\nПополнений пока нет."
    else:
        text = "📥 <b>Последние пополнения</b>\n\n"
        for uid, amount, desc, date_str in deposits:
            date_short = date_str[5:16].replace('T', ' ')
            text += f"👤 <code>{uid}</code> | <b>+{amount:.2f} $</b> | {desc}\n<i>{date_short}</i>\n\n"
            
    kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="admin_stats_menu")
    await safe_edit(call.message, text, reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data == "admin_hist_withdraws")
async def admin_hist_withdraws(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    
    withdraws = get_all_withdrawals(limit=15)
    if not withdraws:
        text = "📤 <b>История выводов</b>\n\nВыводов пока нет."
    else:
        text = "📤 <b>Последние выводы</b>\n\n"
        for w_id, uid, amount, method, status, date_str in withdraws:
            date_short = date_str[5:16].replace('T', ' ')
            status_text = "✅ Выплачено" if status == "paid" else ("❌ Отклонено" if status == "rejected" else "⏳ В обработке")
            method_text = "USDT" if method == "crypto" else "Звезды"
            text += f"🆔 Заявка <code>{w_id}</code>\n👤 <code>{uid}</code> | <b>{amount:.2f} $</b> ({method_text})\n<i>{status_text} | {date_short}</i>\n\n"
            
    kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="admin_stats_menu")
    await safe_edit(call.message, text, reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data == "admin_big_wins")
async def admin_big_wins(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    
    with connection() as db:
        rows = db.execute("SELECT user_id, game, payout FROM game_history WHERE payout > 10.0 ORDER BY id DESC LIMIT 10").fetchall()
    
    if not rows:
        text = "🕵️ Крупных выигрышей (выше 10.00 $) пока нет."
    else:
        text = "🕵️ <b>Последние крупные выигрыши:</b>\n\n"
        for r in rows:
            text += f"👤 <code>{r[0]}</code> | {r[1].upper()} | {r[2]:.2f} $\n"
            
    kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="admin_stats_menu")
    await safe_edit(call.message, text, reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data == "admin_confirm_reset")
async def admin_reset_confirm(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    
    text = (
        "⚠️ <b>ВНИМАНИЕ!</b>\n\n"
        "Ты собираешься полностью сбросить:\n"
        "• Балансы всех игроков (до 0.10 $)\n"
        "• Всю историю игр\n"
        "• WinRate, оборот, рекорды\n\n"
        "Это действие <b>необратимо</b>. Продолжить?"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🔥 ДА, СБРОСИТЬ ВСЁ", callback_data="admin_do_reset")
    kb.button(text="🔙 Отмена", callback_data="admin_stats")
    kb.adjust(1, 1)
    await safe_edit(call.message, text, reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data == "admin_do_reset")
async def admin_do_reset(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    
    with connection() as db:
        db.execute("UPDATE users SET balance=0.10, wins=0, losses=0, wagered=0")
        db.execute("DELETE FROM game_history")
        db.execute("DELETE FROM sqlite_sequence WHERE name='game_history'")
        
    await safe_edit(call.message, "✅ Полный вайп статистики завершен. Балансы установлены по 0.10 $.", reply_markup=admin_back_kb())
    await call.answer("База сброшена!", show_alert=True)

# --- МЕНЮ ПОЛЬЗОВАТЕЛЕЙ ---
@router.callback_query(F.data == "admin_users_menu")
async def admin_users_menu(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    
    text = "👥 <b>Управление пользователями</b>\n\nВыбери действие:"
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Список юзеров", callback_data="admin_user_list")
    kb.button(text="💸 Выдать баланс", callback_data="admin_give")
    kb.button(text="💳 Забрать баланс", callback_data="admin_take")
    kb.button(text="🛑 Бан/Заморозка", callback_data="admin_status")
    kb.button(text="🔙 Назад", callback_data="admin_panel")
    kb.adjust(1, 1, 1, 1, 1)
    
    await safe_edit(call.message, text, reply_markup=kb.as_markup())
    await call.answer()

def get_users_kb(action: str):
    users = get_all_users()
    kb = InlineKeyboardBuilder()
    for row in users:
        uid, balance, status, username = row
        status_icon = "🟢" if status == "active" else ("🧊" if status == "frozen" else "🔴")
        display_name = f"@{username}" if username else f"ID: {uid}"
        kb.button(text=f"{status_icon} {display_name} | {balance:.2f} $", callback_data=f"admin_{action}_{uid}")
    kb.button(text="🔙 Назад", callback_data="admin_users_menu")
    kb.adjust(1)
    return kb.as_markup()

@router.callback_query(F.data == "admin_user_list")
async def admin_user_list(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    await safe_edit(
        call.message,
        "👤 <b>Выбери юзера для просмотра инфо:</b>", 
        reply_markup=get_users_kb("info")
    )
    await call.answer()

@router.callback_query(F.data.startswith("admin_info_"))
async def admin_show_info(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.split("_")[2])
    
    balance, wins, losses, wagered, last_bet, last_diff, status = get_user(uid)
    reason = get_ban_reason(uid)
    total = wins + losses
    
    with connection() as db:
        row = db.execute("SELECT username FROM users WHERE user_id=?", (uid,)).fetchone()
        username = row[0] if row else ""
    
    status_text = "🟢 Активен" if status == "active" else ("🧊 Заморожен" if status == "frozen" else "🔴 Забанен")
    if reason: status_text += f" ({reason})"
    
    w_blocked = is_withdraw_blocked(uid)
    w_status = "🔴 Заблокирован" if w_blocked else "🟢 Разрешен"
    
    text = (
        f"👤 <b>Инфо о юзере <code>{uid}</code></b>\n"
        f"🔗 Юзернейм: @{username or 'нет'}\n\n"
        f"📊 Статус: <b>{status_text}</b>\n"
        f"💰 Баланс: {balance:.2f} $\n"
        f"📈 WinRate: {wins/total*100 if total else 0:.1f}%\n"
        f"🎮 Игр: {total} (W: {wins}, L: {losses})\n"
        f"💸 Оборот: {wagered:.2f} $\n"
        f"🗼 Сложность башни: {last_diff}\n"
        f"📤 Вывод: <b>{w_status}</b>"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="admin_user_list")
    if w_blocked:
        kb.button(text="✅ Разрешить вывод", callback_data=f"admin_unblock_withdraw_{uid}")
    else:
        kb.button(text="🚫 Заблокировать вывод", callback_data=f"admin_block_withdraw_{uid}")
    kb.button(text="🗑 Удалить юзера", callback_data=f"admin_delete_confirm_{uid}")
    kb.adjust(1, 1, 1)
    
    await safe_edit(call.message, text, reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data.startswith("admin_block_withdraw_"))
async def admin_block_withdraw(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.split("_")[3])
    set_withdraw_block(uid, True)
    await call.answer("Вывод заблокирован для юзера.", show_alert=True)
    call.data = f"admin_info_{uid}"
    await admin_show_info(call)

@router.callback_query(F.data.startswith("admin_unblock_withdraw_"))
async def admin_unblock_withdraw(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.split("_")[3])
    set_withdraw_block(uid, False)
    await call.answer("Вывод разблокирован.", show_alert=True)
    call.data = f"admin_info_{uid}"
    await admin_show_info(call)

@router.callback_query(F.data.startswith("admin_delete_confirm_"))
async def admin_delete_confirm(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.split("_")[3])
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔥 ДА, УДАЛИТЬ", callback_data=f"admin_delete_do_{uid}")
    kb.button(text="🔙 Отмена", callback_data=f"admin_info_{uid}")
    kb.adjust(1, 1)
    
    await safe_edit(call.message, 
        f"⚠️ <b>ВНИМАНИЕ!</b>\n\n"
        f"Ты собираешься <b>полностью удалить</b> юзера <code>{uid}</code>.\n\n"
        f"Вместе с ним удалится:\n"
        f"• Вся история игр\n"
        f"• Все заявки на вывод\n"
        f"• Все тикеты\n"
        f"• Сам аккаунт\n\n"
        f"Это действие <b>НЕОБРАТИМО</b>. Продолжить?",
        reply_markup=kb.as_markup()
    )
    await call.answer()

@router.callback_query(F.data.startswith("admin_delete_do_"))
async def admin_delete_do(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.split("_")[3])
    
    delete_user(uid)
    
    await safe_edit(call.message, 
        f"✅ Юзер <code>{uid}</code> и все его данные полностью удалены из базы.",
        reply_markup=admin_back_kb()
    )
    await call.answer("Юзер удален", show_alert=True)

@router.callback_query(F.data == "admin_give")
async def admin_give_start(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    await safe_edit(
        call.message, 
        "💸 <b>Кому выдать баланс?</b>", 
        reply_markup=get_users_kb("give")
    )
    await call.answer()

@router.callback_query(F.data.startswith("admin_give_"))
async def admin_give_user(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.split("_")[2])
    await state.update_data(target_id=uid)
    await state.set_state(AdminStates.waiting_give_amount)
    
    kb = InlineKeyboardBuilder().button(text="🔙 Отмена", callback_data="admin_users_menu")
    await safe_edit(call.message, f"Введи <b>сумму в $</b>, которую нужно выдать юзеру <code>{uid}</code>:", reply_markup=kb.as_markup())
    await call.answer()

@router.message(AdminStates.waiting_give_amount)
async def admin_give_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("Введи число (например, 5.50).")
        
    data = await state.get_data()
    target_id = data.get("target_id")
    await state.clear()
    
    add_balance(target_id, amount, "Админ-пополнение")
    await message.answer(f"✅ Выдано {amount:.2f} $ юзеру {target_id}", reply_markup=admin_back_kb())

@router.callback_query(F.data == "admin_take")
async def admin_take_start(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    await safe_edit(
        call.message, 
        "💳 <b>У кого забрать баланс?</b>", 
        reply_markup=get_users_kb("take")
    )
    await call.answer()

@router.callback_query(F.data.startswith("admin_take_"))
async def admin_take_user(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.split("_")[2])
    await state.update_data(target_id=uid)
    await state.set_state(AdminStates.waiting_take_amount)
    
    kb = InlineKeyboardBuilder().button(text="🔙 Отмена", callback_data="admin_users_menu")
    await safe_edit(call.message, f"Введи <b>сумму в $</b>, которую нужно забрать у юзера <code>{uid}</code>:", reply_markup=kb.as_markup())
    await call.answer()

@router.message(AdminStates.waiting_take_amount)
async def admin_take_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("Введи число (например, 5.50).")
        
    data = await state.get_data()
    target_id = data.get("target_id")
    await state.clear()
    
    success = deduct_balance(target_id, amount, "Админ-списание")
    if success:
        await message.answer(f"✅ Списано {amount:.2f} $ у юзера {target_id}", reply_markup=admin_back_kb())
    else:
        await message.answer(f"❌ У юзера {target_id} не хватает средств.", reply_markup=admin_back_kb())

@router.callback_query(F.data == "admin_status")
async def admin_status_start(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    await safe_edit(
        call.message, 
        "🛑 <b>Управление статусами</b>\nВыбери юзера:", 
        reply_markup=get_users_kb("status")
    )
    await call.answer()

@router.callback_query(F.data.startswith("admin_status_"))
async def admin_status_user(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.split("_")[2])
    status = get_user(uid)[6]
    reason = get_ban_reason(uid)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Разбанить", callback_data=f"admin_setstatus_{uid}_active")
    kb.button(text="🧊 Заморозить", callback_data=f"admin_setstatus_{uid}_frozen")
    kb.button(text="⛔ Забанить", callback_data=f"admin_setstatus_{uid}_banned")
    kb.button(text="🔙 Назад", callback_data="admin_status")
    kb.adjust(1, 1, 1, 1)
    
    status_text = f"<b>{status}</b>"
    if reason: status_text += f" (Причина: {reason})"
    
    await safe_edit(call.message, 
        f"👤 Юзер <code>{uid}</code>\nТекущий статус: {status_text}\n\nЧто делаем?",
        reply_markup=kb.as_markup()
    )
    await call.answer()

@router.callback_query(F.data.startswith("admin_setstatus_"))
async def admin_set_status(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    parts = call.data.split("_")
    uid = int(parts[2])
    new_status = parts[3]
    
    if new_status in ("banned", "frozen"):
        await state.update_data(target_id=uid, new_status=new_status)
        await state.set_state(AdminStates.waiting_ban_reason)
        kb = InlineKeyboardBuilder().button(text="🔙 Отмена", callback_data="admin_users_menu")
        await safe_edit(call.message, 
            f"Введи <b>причину</b> для статуса <b>{new_status}</b> (или напиши 'нет'):", 
            reply_markup=kb.as_markup()
        )
        await call.answer()
        return
        
    set_user_status(uid, new_status, "")
    await safe_edit(call.message, 
        f"✅ Статус юзера <code>{uid}</code> изменен на <b>{new_status}</b>.",
        reply_markup=admin_back_kb()
    )
    await call.answer()

@router.message(AdminStates.waiting_ban_reason)
async def admin_ban_reason(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = data.get("target_id")
    new_status = data.get("new_status")
    reason = message.text if message.text.lower() != "нет" else ""
    
    await state.clear()
    set_user_status(uid, new_status, reason)
    
    await message.answer(
        f"✅ Статус юзера <code>{uid}</code> изменен на <b>{new_status}</b>.\nПричина: {reason or 'без причины'}",
        parse_mode="HTML", reply_markup=admin_back_kb()
    )

# --- МЕНЮ УПРАВЛЕНИЯ БОТОМ ---
@router.callback_query(F.data == "admin_manage_menu")
async def admin_manage_menu(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    
    text = "⚙️ <b>Управление ботом</b>\n\nВыбери действие:"
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Рассылка", callback_data="admin_broadcast")
    kb.button(text="🎁 Создать промокод", callback_data="admin_promo")
    kb.button(text="🛠 Тех. работы", callback_data="admin_maintenance")
    kb.button(text="🧹 Очистка истории БД", callback_data="admin_clear_history")
    kb.button(text="🔙 Назад", callback_data="admin_panel")
    kb.adjust(1, 1, 1, 1, 1)
    
    await safe_edit(call.message, text, reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(AdminStates.waiting_broadcast)
    kb = InlineKeyboardBuilder().button(text="🔙 Отмена", callback_data="admin_manage_menu")
    await safe_edit(call.message, "📢 Введи текст для рассылки или пришли картинку с подписью (можно с HTML-тегами):", reply_markup=kb.as_markup())
    await call.answer()

@router.message(AdminStates.waiting_broadcast)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()
    
    users = get_all_users()
    status_msg = await message.answer("⏳ Начинаю рассылку...")
    success, failed = 0, 0
    total = len(users)
    
    admin_badge = "🛡 <b>ADMIN</b>\n\n"

    for index, row in enumerate(users, 1):
        uid = row[0]
        try:
            if message.photo:
                caption_text = admin_badge + (message.caption or "")
                await message.bot.send_photo(chat_id=uid, photo=message.photo[-1].file_id, caption=caption_text, parse_mode="HTML")
            else:
                full_text = admin_badge + message.html_text
                await message.bot.send_message(chat_id=uid, text=full_text, parse_mode="HTML")
            success += 1
        except Exception:
            failed += 1
            
        if index % 20 == 0 or index == total:
            try:
                await status_msg.edit_text(f"⏳ Рассылка... {index}/{total}\nУспешно: {success} | Ошибок: {failed}")
            except:
                pass
                
        await asyncio.sleep(0.05)
            
    await status_msg.edit_text(f"✅ Рассылка завершена.\nУспешно: {success}\nОшибок: {failed}", reply_markup=admin_back_kb())

@router.callback_query(F.data == "admin_promo")
async def admin_promo_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(AdminStates.waiting_promo_code)
    kb = InlineKeyboardBuilder().button(text="🔙 Отмена", callback_data="admin_manage_menu")
    await safe_edit(call.message, "🎁 Введи <b>название</b> промокода (например, XLINE100):", reply_markup=kb.as_markup())
    await call.answer()

@router.message(AdminStates.waiting_promo_code)
async def admin_promo_code(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(code=message.text.upper())
    await state.set_state(AdminStates.waiting_promo_amount)
    await message.answer("💰 Введи <b>сумму</b> награды (в $):", parse_mode="HTML")

@router.message(AdminStates.waiting_promo_amount)
async def admin_promo_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("Введи число (например, 5.50).")
    await state.update_data(amount=amount)
    await state.set_state(AdminStates.waiting_promo_uses)
    await message.answer("🔢 Введи <b>количество</b> активаций (лимит):", parse_mode="HTML")

@router.message(AdminStates.waiting_promo_uses)
async def admin_promo_uses(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введи число.")
    data = await state.get_data()
    await state.clear()
    
    create_promo(data["code"], data["amount"], int(message.text))
    await message.answer(f"✅ Промокод <code>{data['code']}</code> создан!\nСумма: {data['amount']:.2f} $\nАктиваций: {message.text}", parse_mode="HTML", reply_markup=admin_back_kb())

@router.callback_query(F.data == "admin_clear_history")
async def admin_clear_history(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    
    text = (
        "⚠️ <b>ВНИМАНИЕ!</b>\n\n"
        "Ты собираешься удалить:\n"
        "• Все заявки на вывод\n"
        "• Всю историю кошелька (пополнения/выводы)\n"
        "• Все промокоды\n\n"
        "Балансы игроков и статистика игр <b>НЕ</b> тронутся.\n\n"
        "Продолжить?"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🔥 ДА, ОЧИСТИТЬ", callback_data="admin_do_clear_history")
    kb.button(text="🔙 Отмена", callback_data="admin_manage_menu")
    kb.adjust(1, 1)
    
    await safe_edit(call.message, text, reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data == "admin_do_clear_history")
async def admin_do_clear_history(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    
    clear_history_and_promos()
    
    await safe_edit(call.message, "✅ <b>Очистка завершена!</b>\n\nВсе заявки, история кошелька и промокоды удалены.", reply_markup=admin_back_kb())
    await call.answer("История и промокоды очищены!", show_alert=True)

# --- ОБРАБОТКА ЗАЯВОК НА ВЫВОД (ИЗ ЛОГ-ЧАТА) ---
@router.callback_query(F.data.startswith("adm_appr_"))
async def approve_withdraw(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): 
        return await call.answer("Нет прав", show_alert=True)
        
    with_id = int(call.data.split("_")[2])
    
    with connection() as db:
        row = db.execute("SELECT user_id, amount, method, destination, status FROM withdrawals WHERE id = ?", (with_id,)).fetchone()
        
    if not row or row["status"] != "pending":
        return await call.answer("Заявка уже обработана", show_alert=True)
        
    user_id = row["user_id"]
    amount = row["amount"]
    method = row["method"]
    destination = row["destination"]
    
    if method == "crypto":
        usdt_amount = round(amount * 0.98, 2)
        await call.bot.send_message(user_id, f"✅ <b>Заявка на вывод одобрена!</b>\n\nСумма: <b>{usdt_amount} USDT</b>\n\nСредства будут отправлены чеком в ближайшее время.", parse_mode="HTML")
        approve_withdrawal(with_id)
        await safe_edit(call.message, call.message.html_text + f"\n\n✅ <b>ВЫПЛАЧЕНО (Ручной чек)</b>\nОтправлено {usdt_amount} USDT", reply_markup=None)
    else:
        approve_withdrawal(with_id)
        await safe_edit(call.message, call.message.html_text + "\n\n✅ <b>ВЫПЛАЧЕНО (Звезды)</b>", reply_markup=None)
        await call.bot.send_message(user_id, f"✅ <b>Выплата произведена!</b>\nЗаявка на {amount:.2f} $ выполнена.", parse_mode="HTML")

    await call.answer("Заявка выполнена")

@router.callback_query(F.data.startswith("adm_rej_"))
async def reject_withdraw(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): 
        return await call.answer("Нет прав", show_alert=True)
        
    with_id = int(call.data.split("_")[2])
    uid = reject_withdrawal(with_id)
    
    if uid:
        await safe_edit(call.message, call.message.html_text + "\n\n❌ <b>ОТКЛОНЕНО</b> (Средства возвращены)", reply_markup=None)
        try:
            await call.bot.send_message(uid, "❌ <b>Заявка на вывод отклонена.</b>\nСредства возвращены на баланс.", parse_mode="HTML")
        except: 
            pass
        await call.answer("Отклонено")
    else:
        await call.answer("Уже обработано", show_alert=True)

# --- ОТВЕТЫ И ЗАКРЫТИЕ ТИКЕТОВ ---
@router.message(F.chat.id == SUPPORT_CHAT_ID, F.reply_to_message)
async def answer_ticket(message: types.Message):
    if not is_admin(message.from_user.id): 
        return
    
    reply_msg_id = message.reply_to_message.message_id
    target_uid = None
    
    if message.reply_to_message.reply_markup:
        for row in message.reply_to_message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("ticket_resolved_"):
                    target_uid = int(btn.callback_data.split("_")[2])
                    break
    
    if not target_uid:
        target_uid = get_ticket_user(reply_msg_id)
        
    if target_uid:
        try:
            await message.bot.send_message(target_uid, f"📬 <b>Ответ поддержки:</b>\n\n{message.text}", parse_mode="HTML")
            await message.reply("✅ Ответ отправлен игроку.")
        except Exception:
            await message.reply("❌ Не удалось отправить (юзер заблокировал бота).")
    else:
        await message.reply("❓ Не найден юзер для этого тикета.")

@router.callback_query(F.data.startswith("ticket_resolved_"))
async def ticket_resolved(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): 
        return await call.answer("Нет прав", show_alert=True)
    
    uid = int(call.data.split("_")[2])
    
    with connection() as db:
        db.execute("UPDATE tickets SET status = 'closed' WHERE user_id = ? AND status = 'open'", (uid,))
    
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        print(f"Не удалось убрать кнопки: {e}")
    
    try:
        await call.bot.send_message(uid, "✅ <b>Твой вопрос решен!</b>\n\nСпасибо за обращение.", parse_mode="HTML")
    except: pass
        
    await call.answer("Тикет закрыт как 'Решено'")
    await call.message.reply("✅ Тикет закрыт (Решено).")

@router.callback_query(F.data.startswith("close_ticket_"))
async def close_ticket_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): 
        return await call.answer("Нет прав", show_alert=True)
    
    uid = int(call.data.split("_")[2])
    
    await state.clear()
    await state.update_data(target_uid=uid, ticket_msg_id=call.message.message_id)
    await state.set_state(AdminStates.waiting_ticket_reason)
    
    try:
        await call.message.reply(f"✍️ Введи <b>причину</b> закрытия тикета для юзера <code>{uid}</code>:")
    except Exception as e:
        print(f"Ошибка при ответе на тикет: {e}")
        
    await call.answer()

@router.message(AdminStates.waiting_ticket_reason)
async def close_ticket_reason(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    
    data = await state.get_data()
    msg_id = data.get("ticket_msg_id")
    target_uid = data.get("target_uid")
    
    if not msg_id or not target_uid:
        await state.clear()
        return await message.answer("❌ Ошибка: данные тикета не найдены.")
    
    reason = message.text
    await state.clear()
    
    with connection() as db:
        db.execute("UPDATE tickets SET status = 'closed' WHERE user_id = ? AND status = 'open'", (target_uid,))
    
    try:
        await message.bot.edit_message_reply_markup(chat_id=SUPPORT_CHAT_ID, message_id=msg_id, reply_markup=None)
    except Exception as e:
        print(f"Не удалось убрать кнопки: {e}")
    
    try:
        await message.bot.send_message(target_uid, f"🔒 <b>Твой тикет закрыт.</b>\n\n<b>Причина:</b> {reason}\n\nСпасибо за обращение!", parse_mode="HTML")
    except: pass
        
    await message.answer(f"✅ Тикет юзера <code>{target_uid}</code> закрыт с причиной.", reply_markup=admin_back_kb())

# --- ТЕХ. РАБОТЫ ---
@router.callback_query(F.data == "admin_maintenance")
async def admin_toggle_maintenance(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    
    current = is_maintenance()
    new_status = not current
    set_maintenance(new_status)
    
    status_text = "🛑 ВКЛЮЧЕНЫ (Игры заблокированы)" if new_status else "🟢 ВЫКЛЮЧЕНЫ (Игры доступны)"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="admin_manage_menu")
    
    await safe_edit(call.message, 
        f"🛠 <b>Режим тех. работ</b>\n\n"
        f"Текущий статус: <b>{status_text}</b>\n\n"
        f"При включении игроки не смогут делать ставки.", 
        reply_markup=kb.as_markup()
    )
    await call.answer(f"Тех. работы: {'ВКЛ' if new_status else 'ВЫКЛ'}")
