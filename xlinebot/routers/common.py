from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, LabeledPrice, PreCheckoutQuery, Message, WebAppInfo
import hashlib
import secrets
import time
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
import logging
import asyncio

from ..db import (
    get_user, get_ban_reason, create_ticket, get_active_ticket_by_user,
    register_user, record_star_purchase, get_star_purchases
)
from ..keyboards import main_menu, sub_menu
from ..config import ADMIN_ID, SUPPORT_CHAT_ID, WEBAPP_URL
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
                text += f"\n\n<b>Причина:</b> {reason}"
            await message.answer(text, parse_mode="HTML")
            return

        if status == "frozen":
            reason = get_ban_reason(uid)
            text = "🧊 <b>Твой аккаунт заморожен.</b>"
            if reason:
                text += f"\n\n<b>Причина:</b> {reason}"
            await message.answer(text, parse_mode="HTML")
            return

        try:
            subscribed = await asyncio.wait_for(check_sub(message.bot, uid), timeout=10)
        except Exception:
            logging.exception("XLINE /start: subscription check failed for user %s", uid)
            await message.answer(
                "⚠️ Сейчас не получается проверить подписку. Попробуй отправить /start ещё раз через минуту."
            )
            return

        if not subscribed:
            await message.answer(
                "👋 Привет! Чтобы открыть XLINE, подпишись на наш канал.\n\n"
                "Нажми кнопку ниже, а затем «Проверить подписку».",
                reply_markup=sub_menu()
            )
            return

        # Send the usable launch prompt first. Failure to remove an old reply
        # keyboard must never prevent /start from showing the inline launch button.
        launch_kb = InlineKeyboardBuilder()
        launch_kb.button(text="🔐 Подготовить безопасный запуск", callback_data="xline_launch")
        await message.answer(
            f"👋 Привет, {message.from_user.first_name or 'друг'}!\n\n"
            "Добро пожаловать в XLINE. Нажми кнопку ниже — я подтвержу аккаунт и выдам персональную ссылку для входа.",
            reply_markup=launch_kb.as_markup()
        )
        try:
            await message.answer("Старая клавиатура запуска отключена.", reply_markup=ReplyKeyboardRemove())
        except Exception:
            logging.exception("XLINE could not remove legacy reply keyboard; inline launch remains available")
    except Exception:
        logging.exception("XLINE /start handler failed")
        try:
            await message.answer("⚠️ Не удалось обработать /start из-за временной ошибки. Попробуй ещё раз чуть позже.")
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


@router.callback_query(F.data == "xline_launch")
async def xline_launch_callback(call: types.CallbackQuery):
    # Acknowledge immediately so Telegram does not leave the button spinning
    # while channel membership is checked.
    await call.answer("Проверяю доступ…")
    try:
        uid = call.from_user.id
        status = get_user(uid)[-1]
        if status in ("banned", "frozen"):
            await call.message.answer("⛔ Доступ к аккаунту ограничен.")
            return
        subscribed = await asyncio.wait_for(check_sub(call.bot, uid), timeout=10)
        if not subscribed:
            await call.message.answer(
                "📢 Для запуска XLINE нужна подписка на канал.",
                reply_markup=sub_menu(),
            )
            return
        from ..db import connection
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        now = int(time.time())
        with connection() as db:
            db.execute(
                "INSERT INTO miniapp_launch_tokens(token_hash,user_id,expires_at,used_at) VALUES(?,?,?,NULL)",
                (token_hash, call.from_user.id, now + 180),
            )
        # Add the token as a real query parameter (before any URL fragment).
        # Naive string concatenation after a '#' silently hides it from the page.
        parts = urlsplit(WEBAPP_URL)
        if parts.scheme != "https" or not parts.netloc:
            raise ValueError("WEBAPP_URL must be a public HTTPS URL")
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["launch_token"] = raw_token
        launch_url = urlunsplit((
            parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment
        ))
        kb = InlineKeyboardBuilder()
        kb.button(text="🚀 Открыть XLINE", web_app=WebAppInfo(url=launch_url))
        await call.message.answer(
            "✅ Аккаунт подтверждён. Ссылка действует 3 минуты и используется один раз.",
            reply_markup=kb.as_markup(),
        )
    except Exception:
        logging.exception("XLINE launch-token creation failed")
        await call.message.answer("⚠️ Не удалось подготовить ссылку. Отправь /start и попробуй ещё раз.")

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

@router.callback_query(F.data == "main_menu")
async def main(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Главное меню:", reply_markup=main_menu(call.from_user.id))
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
