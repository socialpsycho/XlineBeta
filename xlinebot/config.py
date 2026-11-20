import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "casino.db"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Твой Telegram ID для доступа к админке
ADMIN_ID = int(os.getenv("ADMIN_ID", "5198022650")) 

# ID лог-чата для заявок на вывод
LOG_CHAT_ID = int(os.getenv("LOG_CHAT_ID", "-1004442671510"))

# ID канала для проверки подписки
CHANNEL_ID = os.getenv("CHANNEL_ID", "@xlinewin_news")

# Токен для CryptoBot
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN", "").strip()

# ID тикет чата для ответа на тикеты
SUPPORT_CHAT_ID = int(os.getenv("SUPPORT_CHAT_ID", -1003920002688))

# --- НОВЫЕ ПЕРЕМЕННЫЕ ДЛЯ ЛОГОВ ---
# Куда падают ошибки
ERRORS_CHAT_ID = int(os.getenv("ERRORS_CHAT_ID", "-1004324243870"))
# Куда падают статусы (запуск/перезагрузка)
STATUS_CHAT_ID = int(os.getenv("STATUS_CHAT_ID", "-1004360973540"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Add it to .env or the process environment.")
