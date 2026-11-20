import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Keep existing data when moving the default database from casino.db to play.db.
_database_env = os.getenv("DATABASE_PATH", "").strip()
if _database_env:
    DATABASE_PATH = Path(_database_env)
    if not DATABASE_PATH.is_absolute():
        DATABASE_PATH = BASE_DIR / DATABASE_PATH
else:
    DATABASE_PATH = BASE_DIR / "play.db"

if DATABASE_PATH.name == "casino.db":
    new_database_path = DATABASE_PATH.with_name("play.db")
    if DATABASE_PATH.exists() and not new_database_path.exists():
        DATABASE_PATH.replace(new_database_path)
    DATABASE_PATH = new_database_path

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Telegram ID allowed to access the admin panel.
ADMIN_ID = int(os.getenv("ADMIN_ID", "5198022650"))

# Chat used for operational logs.
LOG_CHAT_ID = int(os.getenv("LOG_CHAT_ID", "-1004442671510"))

# Channel used for subscription checks.
CHANNEL_ID = os.getenv("CHANNEL_ID", "@xlinewin_news")

CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN", "").strip()
SUPPORT_CHAT_ID = int(os.getenv("SUPPORT_CHAT_ID", -1003920002688))

ERRORS_CHAT_ID = int(os.getenv("ERRORS_CHAT_ID", "-1004324243870"))
STATUS_CHAT_ID = int(os.getenv("STATUS_CHAT_ID", "-1004360973540"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Add it to .env or the process environment.")
