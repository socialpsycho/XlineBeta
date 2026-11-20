import asyncio
import logging
import os
import traceback
from datetime import datetime

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent

from xlinebot.config import BOT_TOKEN, LOG_LEVEL, ERRORS_CHAT_ID, STATUS_CHAT_ID
from xlinebot.db import init_db
from xlinebot.miniapp_api import create_app
from xlinebot.routers import common, admin, miniapp


async def main():
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(common.router)
    dp.include_router(admin.router)
    dp.include_router(miniapp.router)

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
        except Exception as exc:
            logging.error("Не удалось отправить лог в ERRORS_CHAT_ID: %s", exc)
        return True

    async def on_startup(bot: Bot):
        try:
            await bot.send_message(
                STATUS_CHAT_ID,
                f"🚀 <b>Бот успешно запущен!</b>\n🕒 Время: {datetime.now().strftime('%H:%M:%S')}",
                parse_mode="HTML",
            )
        except Exception as exc:
            logging.error("Не удалось отправить статус в STATUS_CHAT_ID: %s", exc)

    async def on_shutdown(bot: Bot):
        try:
            await bot.send_message(
                STATUS_CHAT_ID,
                f"🔴 <b>Бот выключается...</b>\n🕒 Время: {datetime.now().strftime('%H:%M:%S')}",
                parse_mode="HTML",
            )
        except Exception as exc:
            logging.error("Не удалось отправить статус в STATUS_CHAT_ID: %s", exc)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Mini App API shares the bot process and persists sessions in SQLite.
    api_app = create_app()
    runner = web.AppRunner(api_app)
    await runner.setup()
    host = os.getenv("MINIAPP_API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("MINIAPP_API_PORT", "80")))
    site = web.TCPSite(runner, host, port)
    await site.start()
    logging.info("XLINE Mini App API listening on %s:%s", host, port)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
