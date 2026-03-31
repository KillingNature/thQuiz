import os
import logging
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bot")

# ══════════════════════════════ КОНФИГ ══════════════════════════════

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip()}
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot_data.db")
MSK = timezone(timedelta(hours=3))

POST_TYPE_EMOJI = {"post": "\U0001f4dd", "case": "\U0001f9e9", "sale": "\U0001f4b0", "webinar": "\U0001f4e2"}
POST_TYPE_NAME = {"post": "Пост", "case": "Кейс", "sale": "Анонс", "webinar": "Вебинар"}


def now_msk() -> datetime:
    return datetime.now(MSK)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
