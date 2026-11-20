import asyncio
import logging
import traceback
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent
from xlinebot.config import BOT_TOKEN, LOG_LEVEL, ERRORS_CHAT_ID, STATUS_CHAT_ID
from xlinebot.db import init_db
from xlinebot.routers import common, mines, tower, rocket, admin, slots, blackjack

async def main():
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    init_db()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    # Подключаем роутеры
    dp.include_router(common.router)
    dp.include_router(mines.router)
    dp.include_router(tower.router)
    dp.include_router(rocket.router)
    dp.include_router(slots.router)
    dp.include_router(admin.router)
    dp.include_router(blackjack.router)

    # --- ОБРАБОТЧИК ОШИБОК (ЛЕТЯТ В ERRORS_CHAT_ID) ---
    @dp.errors()
    async def global_error_handler(event: ErrorEvent):
        error_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_text = (
            f"🚨 <b>КРИТИЧЕСКАЯ ОШИБКА</b>\n\n"
            f"🕒 Время: {error_time}\n"
            f"❌ Ошибка: <code>{type(event.exception).__name__}</code>\n"
            f"📝 Текст: {str(event.exception)[:1000]}\n\n"
            f"<pre>{traceback.format_exc()[:3000]}</pre>"
        )
        try:
            await bot.send_message(ERRORS_CHAT_ID, error_text, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Не удалось отправить лог в ERRORS_CHAT_ID: {e}")
        return True

    # --- СТАТУС ЗАПУСКА (ЛЕТИТ В STATUS_CHAT_ID) ---
    async def on_startup(bot: Bot):
        try:
            await bot.send_message(
                STATUS_CHAT_ID, 
                f"🚀 <b>Бот успешно запущен!</b>\n🕒 Время: {datetime.now().strftime('%H:%M:%S')}\n\n<i>Если ты не перезапускал его вручную — значит Amvera дала контейнеру пинка (возможно, не хватило памяти).</i>", 
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Не удалось отправить статус в STATUS_CHAT_ID: {e}")

    # --- СТАТУС ПРИ ОСТАНОВКЕ (ВЫКЛЮЧЕНИЕ) ---
    async def on_shutdown(bot: Bot):
        try:
            await bot.send_message(
                STATUS_CHAT_ID, 
                f"🔴 <b>Бот выключается...</b>\n"
                f"🕒 Время: {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"<i>Контейнер остановлен. Если это плановый перезапуск — бот скоро пришлет сообщение о запуске.</i>", 
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Не удалось отправить статус в STATUS_CHAT_ID: {e}")

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
