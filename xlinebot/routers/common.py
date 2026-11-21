from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, LabeledPrice, PreCheckoutQuery, Message
import logging
import asyncio

from ..db import (
    get_user, get_ban_reason, create_ticket, get_active_ticket_by_user,
    register_user, record_star_purchase, get_star_purchases
)
from ..keyboards import main_menu, main_reply_menu, sub_menu
from ..config import ADMIN_ID, SUPPORT_CHAT_ID
from ..states import SupportStates
from ..utils import check_sub

router = Router()
def main_reply_menu(user_id: int) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="🚀 Открыть XLINE", web_app=WebAppInfo(url=WEBAPP_URL))
    kb.adjust(1)
    return kb.as_markup(
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Открыть XLINE"
    )

@router.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    try:
        await state.clear()
        uid = message.from_user.id
        register_user(uid, message.from_user.username)
        status = get_user(uid)[-1]

        if status == "banned":
            reason = get_ban_reason(uid)
            text = "⛔ <b>Ты забанен в этом боте.</b>"
            if reason:
                text += f"\\n\\n<b>Причина:</b> {reason}"
            await message.answer(text, parse_mode="HTML")
            return
        if status == "frozen":
            reason = get_ban_reason(uid)
            text = "🧊 <b>Твой аккаунт заморожен.</b>"
            if reason:
                text += f"\\n\\n<b>Причина:</b> {reason}"
            await message.answer(text, parse_mode="HTML")
            return

        try:
            subscribed = await asyncio.wait_for(check_sub(message.bot, uid), timeout=10)
        except Exception:
            logging.exception("XLINE /start: subscription check failed for user %s", uid)
            await message.answer("⚠️ Сейчас не получается проверить подписку. Попробуй /start ещё раз через минуту.")
            return
        if not subscribed:
            await message.answer(
                "👋 Добро пожаловать в XLINE!\\n\\nПодпишись на канал, чтобы открыть все разделы.",
                reply_markup=sub_menu()
            )
            return

        await message.answer(
            "♠️ <b>Добро пожаловать в XLINE!</b>\\n\\n"
            "Выбери раздел ниже. Игры и баланс работают в демонстрационном режиме — "
            "виртуальные баллы не являются деньгами.",
            parse_mode="HTML",
            reply_markup=main_reply_menu(uid)
        )
    except Exception:
        logging.exception("XLINE /start handler failed")
        try:
            await message.answer("⚠️ Не удалось открыть меню. Попробуй отправить /start ещё раз.")
        except Exception:
            logging.exception("XLINE /start fallback reply failed")

@router.callback_query(F.data == "check_sub")
async def check_sub_callback(call: types.CallbackQuery):
    await call.answer()
    try:
        subscribed = await asyncio.wait_for(check_sub(call.bot, call.from_user.id), timeout=10)
        if not subscribed:
            await call.message.answer("❌ Ты всё ещё не подписан на канал!")
            return
        await call.message.edit_text(
            "✅ <b>Подписка подтверждена!</b>\nОткрой XLINE кнопкой под следующим сообщением.",
            parse_mode="HTML"
        )
        launch_kb = InlineKeyboardBuilder()
        launch_kb.button(text="🔐 Подготовить безопасный запуск", callback_data="xline_launch")
        await call.message.answer(
            "🚀 XLINE готов. Нажми кнопку, чтобы подтвердить аккаунт.",
            reply_markup=launch_kb.as_markup()
        )
        try:
            await call.message.answer("Старая клавиатура запуска отключена.", reply_markup=ReplyKeyboardRemove())
        except Exception:
            logging.exception("XLINE could not remove legacy reply keyboard after subscription check")
    except Exception:
        logging.exception("XLINE subscription callback failed")
        await call.message.answer("⚠️ Не удалось проверить подписку. Попробуй ещё раз через /start.")


@router.message(F.text == "💼 Кошелёк")
async def reply_wallet(message: types.Message):
    await message.answer(
        "🛍 <b>Магазин XLINE</b>\n\n"
        "Здесь можно приобрести цифровые товары за Telegram Stars. "
        "Денежного баланса и вывода средств нет.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardBuilder().button(
            text="🛍 Открыть каталог", callback_data="store"
        ).as_markup()
    )


# --- ОСНОВНЫЕ РАЗДЕЛЫ ЧАТ-БОТА (без Mini App) ---
@router.message(F.text == "☰ Меню")
async def text_main_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "♠️ <b>Главное меню XLINE</b>\\nВыбери нужный раздел:",
        parse_mode="HTML",
        reply_markup=main_reply_menu(message.from_user.id)
    )

@router.message(F.text == "🎮 Играть")
async def text_games_menu(message: types.Message):
    kb = InlineKeyboardBuilder()
    for label, code in [
        ("🎲 Кубик", "chatgame_dice"), ("⚽ Футбол", "chatgame_football"),
        ("🏀 Баскетбол", "chatgame_basketball"), ("🎯 Дартс", "chatgame_darts"),
        ("🎳 Боулинг", "chatgame_bowling"), ("🎰 Слоты", "chatgame_slots"),
        ("💫 Комбо ставки", "chatgame_combo"), ("🎮 Авторские", "chatgame_custom"),
        ("💎 Exclusive", "chatgame_exclusive")
    ]:
        kb.button(text=label, callback_data=code)
    kb.button(text="🔙 Главное меню", callback_data="main_menu")
    kb.adjust(3, 3, 3, 1)
    await message.answer(
        "🎮 <b>Игры XLINE</b>\\n\\nВыбери игру. Сейчас подключается чат-игровой режим; "
        "денежных ставок и выплат нет.",
        parse_mode="HTML", reply_markup=kb.as_markup()
    )

@router.callback_query(F.data.startswith("chatgame_"))
async def chat_game_placeholder(call: types.CallbackQuery):
    await call.answer("Этот режим ещё настраивается. Пока доступен только демонстрационный баланс.", show_alert=True)

@router.message(F.text == "👤 Профиль")
async def text_profile(message: types.Message):
    data = get_user(message.from_user.id)
    balance, wins, losses, wagered = data[:4]
    await message.answer(
        "👤 <b>Профиль XLINE</b>\\n\\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\\n"
        f"💳 Баланс: <b>{balance:.2f} demo</b>\\n"
        f"🏆 Победы: <b>{wins}</b>\\n"
        f"❌ Поражения: <b>{losses}</b>\\n"
        f"🎯 Отыгрыш: <b>{wagered:.2f}</b>",
        parse_mode="HTML", reply_markup=main_reply_menu(message.from_user.id)
    )

@router.message(F.text == "💳 Баланс")
async def text_balance(message: types.Message):
    balance = get_user(message.from_user.id)[0]
    await message.answer(
        f"💳 <b>Баланс XLINE</b>\\n\\nДоступно: <b>{balance:.2f} demo</b>\\n"
        "Это виртуальные баллы для тестирования, не реальные деньги.",
        parse_mode="HTML", reply_markup=main_reply_menu(message.from_user.id)
    )

@router.message(F.text.in_({"⬇️ Пополнить", "⬆️ Вывести", "🎁 Бонусы", "🤝 Рефералка", "🧾 Чеки", "⚙️ Настройки", "📊 Топ", "💸 $ с чата", "📢 Канал", "💬 Чат"}))
async def text_section_placeholder(message: types.Message):
    labels = {
        "⬇️ Пополнить": "Пополнение", "⬆️ Вывести": "Вывод",
        "🎁 Бонусы": "Бонусы", "🤝 Рефералка": "Реферальная программа",
        "🧾 Чеки": "Чеки", "⚙️ Настройки": "Настройки",
        "📊 Топ": "Рейтинг игроков", "💸 $ с чата": "Награды чата",
        "📢 Канал": "Канал XLINE", "💬 Чат": "Чат XLINE"
    }
    explanations = {
        "⬇️ Пополнить": "Пополнение реальными деньгами отключено. Баланс сейчас демонстрационный.",
        "⬆️ Вывести": "Вывод средств отключён. Виртуальные баллы нельзя вывести или обменять.",
        "🎁 Бонусы": "Раздел бонусов готовится.",
        "🤝 Рефералка": "Реферальная система готовится.",
        "🧾 Чеки": "История чеков появится после подключения безопасной системы покупок.",
        "⚙️ Настройки": "Настройки профиля готовятся.",
        "📊 Топ": "Рейтинг игроков появится после запуска чат-игр.",
        "💸 $ с чата": "Награды за чат пока отключены.",
        "📢 Канал": "Новости XLINE: @xlinewin_news",
        "💬 Чат": "Ссылка на чат будет добавлена после настройки сообщества."
    }
    await message.answer(
        f"📌 <b>{labels[message.text]}</b>\\n\\n{explanations[message.text]}",
        parse_mode="HTML", reply_markup=main_reply_menu(message.from_user.id)
    )

@router.message(F.text == "🎧 Поддержка")
async def text_support_start(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    active_msg_id = get_active_ticket_by_user(uid)
    if active_msg_id:
        await message.answer("⚠️ У тебя уже есть открытый тикет. Дождись ответа поддержки.")
        return
    await state.set_state(SupportStates.waiting_message)
    await message.answer("🆘 Напиши одним сообщением свой вопрос для поддержки.")

@router.callback_query(F.data == "main_menu")
async def main(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer(
        "♠️ <b>Главное меню XLINE</b>\\nВыбери нужный раздел:",
        parse_mode="HTML",
        reply_markup=main_reply_menu(call.from_user.id)
    )
    await call.answer()

@router.callback_query(F.data == "profile")
async def profile(call: types.CallbackQuery):
    uid = call.from_user.id
    text = (
        "👤 <b>Профиль XLINE</b>\n\n"
        f"🆔 Telegram ID: <code>{uid}</code>\n"
        f"👋 Имя: {call.from_user.first_name or 'Пользователь'}\n\n"
        "Здесь будут отображаться данные аккаунта, покупки и настройки."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🆘 Поддержка", callback_data="support")
    kb.button(text="🔙 Назад", callback_data="main_menu")
    kb.adjust(2, 1)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await call.answer()

@router.callback_query(F.data == "wallet")
@router.callback_query(F.data == "store")
async def store_menu(call: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="🎨 Тема профиля · 50 ⭐", callback_data="buy_product_theme")
    kb.button(text="🖼 Набор аватаров · 75 ⭐", callback_data="buy_product_avatars")
    kb.button(text="💎 Premium-контент · 150 ⭐", callback_data="buy_product_premium")
    kb.button(text="📜 Мои покупки", callback_data="my_purchases")
    kb.button(text="🔙 Назад", callback_data="main_menu")
    kb.adjust(1)
    await call.message.edit_text(
        "🛍 <b>Магазин XLINE</b>\n\n"
        "Оплата цифровых товаров Telegram Stars.\n"
        "Stars не зачисляются на внутренний баланс и не обмениваются на деньги.",
        parse_mode="HTML", reply_markup=kb.as_markup()
    )
    await call.answer()

PRODUCTS = {
    "theme": {"title": "Тема профиля XLINE", "description": "Цифровая тема оформления профиля", "stars": 50},
    "avatars": {"title": "Набор аватаров XLINE", "description": "Цифровой набор аватаров для профиля", "stars": 75},
    "premium": {"title": "Premium-контент XLINE", "description": "Цифровой доступ к дополнительному контенту", "stars": 150},
}

async def send_product_invoice(bot, chat_id: int, user_id: int, product_id: str):
    # Checkout stays closed until real digital goods and automatic delivery are ready.
    return False


@router.callback_query(F.data.startswith("buy_product_"))
async def buy_product(call: types.CallbackQuery):
    product_id = call.data.removeprefix("buy_product_")
    if not await send_product_invoice(call.bot, call.from_user.id, call.from_user.id, product_id):
        return await call.answer("Товар не найден.", show_alert=True)
    await call.answer("Счёт отправлен в личный чат.")


@router.message(F.web_app_data)
async def miniapp_product_request(message: Message):
    import json
    try:
        data = json.loads(message.web_app_data.data)
    except (TypeError, ValueError):
        return await message.answer("Не удалось прочитать запрос Mini App.")
    if data.get("action") != "buy_product":
        return await message.answer("Неизвестное действие Mini App.")
    product_id = str(data.get("product", ""))
    if not await send_product_invoice(message.bot, message.chat.id, message.from_user.id, product_id):
        return await message.answer("Товар не найден. Обнови каталог XLINE.")


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    try:
        prefix, uid, product_id = query.invoice_payload.split(":")
        product = PRODUCTS.get(product_id)
        valid = (
            prefix == "xline_product"
            and int(uid) == query.from_user.id
            and product is not None
            and query.currency == "XTR"
            and query.total_amount == product["stars"]
        )
    except (ValueError, AttributeError):
        valid = False
    valid = False  # Checkout stays closed until product delivery is implemented.
    await query.answer(ok=valid, error_message="Оплата временно отключена: каталог ещё настраивается.")

@router.message(F.successful_payment)
async def success_payment(message: Message):
    payment = message.successful_payment
    try:
        prefix, uid, product_id = payment.invoice_payload.split(":")
        product = PRODUCTS.get(product_id)
        valid = (
            prefix == "xline_product"
            and int(uid) == message.from_user.id
            and product is not None
            and payment.currency == "XTR"
            and payment.total_amount == product["stars"]
        )
    except (ValueError, AttributeError):
        valid = False
        product = None
    if not valid or product is None:
        await message.answer("Платёж получен, но данные счёта не прошли проверку. Обратись в поддержку и сохрани квитанцию.")
        return
    saved = record_star_purchase(
        user_id=message.from_user.id,
        product_id=product_id,
        product_title=product["title"],
        stars=payment.total_amount,
        telegram_charge_id=payment.telegram_payment_charge_id,
    )
    if saved:
        await message.answer(
            f"✅ <b>Покупка подтверждена!</b>\n\n"
            f"Товар: {product['title']}\nОплачено: {payment.total_amount} ⭐\n"
            "Покупка сохранена в истории XLINE.",
            parse_mode="HTML"
        )
    else:
        await message.answer("Эта покупка уже учтена. Повторное зачисление не выполнялось.")

@router.callback_query(F.data == "my_purchases")
async def my_purchases(call: types.CallbackQuery):
    history = get_star_purchases(call.from_user.id)
    if not history:
        text = "📜 <b>Мои покупки</b>\n\nПокупок пока нет."
    else:
        text = "📜 <b>Последние покупки</b>\n\n"
        for title, stars, created_at in history:
            stamp = created_at[:16].replace("T", " ")
            text += f"• {title} — {stars} ⭐\n  <i>{stamp} UTC</i>\n"
    kb = InlineKeyboardBuilder().button(text="🔙 В магазин", callback_data="store")
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await call.answer()

# Promocodes that credit a monetary balance are disabled.

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
