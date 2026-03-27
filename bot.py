import os
import re
import csv
import io
import json
import uuid
import asyncio
import logging
import sqlite3
import smtplib
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, formataddr, make_msgid
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, BotCommandScopeChat
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ══════════════════════════════ КОНФИГ ══════════════════════════════

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip()}
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.db")
MSK = timezone(timedelta(hours=3))

POST_TYPE_EMOJI = {"post": "\U0001f4dd", "case": "\U0001f9e9", "sale": "\U0001f4b0", "webinar": "\U0001f4e2"}
POST_TYPE_NAME = {"post": "Пост", "case": "Кейс", "sale": "Анонс", "webinar": "Вебинар"}


def now_msk() -> datetime:
    return datetime.now(MSK)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ══════════════════════════════ ВОПРОСЫ КВИЗА ══════════════════════════════

QUESTIONS = [
    {
        "text": (
            "\U0001f4bc <b>Вопрос 1 — «Задача, на которую уходит полдня»</b>\n\n"
            "Тебе нужно подготовить материал:\n"
            "анализ конкурентов, бриф, сводный отчёт, описание фичи — неважно что именно.\n"
            "Обычно это занимает 3–4 часа.\n\n"
            "Как ты это делаешь?"
        ),
        "options": [
            ("A", "Сажусь и делаю вручную — гуглю, читаю, структурирую сам"),
            ("B", "Прошу ChatGPT помочь, но результат сырой — всё равно переделываю почти полностью"),
            ("C", "Использую ИИ как черновик, знаю как его доработать — трачу в 2 раза меньше времени"),
            ("D", "У меня готовый промпт под эту задачу — получаю нужный результат с первого запроса за 20 минут"),
        ],
    },
    {
        "text": (
            "\U0001f91d <b>Вопрос 2 — «Тебя просят предложить, как внедрить ИИ»</b>\n\n"
            "Руководитель, клиент или коллега говорит:\n"
            "«Все вокруг внедряют ИИ. Что мы можем сделать у себя?»\n\n"
            "Что происходит дальше?"
        ),
        "options": [
            ("A", "Теряюсь — не знаю, что конкретно предложить"),
            ("B", "Говорю про ChatGPT и нейросети, но без конкретики"),
            ("C", "Могу назвать несколько инструментов, но не уверен, подойдут ли они именно для этих задач"),
            ("D", "Провожу быстрый разбор процессов, нахожу точки автоматизации и предлагаю конкретный план с инструментами"),
        ],
    },
    {
        "text": (
            "\U0001f504 <b>Вопрос 3 — «Рутина, которая повторяется каждую неделю»</b>\n\n"
            "У каждого есть задачи, которые делаются снова и снова:\n"
            "еженедельный отчёт, сводка, ответы на типовые вопросы, обработка данных из таблицы.\n\n"
            "Как ты с ними работаешь?"
        ),
        "options": [
            ("A", "Делаю вручную каждый раз — это норма"),
            ("B", "Использую шаблоны, но время всё равно уходит"),
            ("C", "Иногда подключаю ИИ, но непоследовательно — зависит от настроения"),
            ("D", "Процесс автоматизирован: ИИ делает черновик или всю работу, я только проверяю"),
        ],
    },
    {
        "text": (
            "\U0001f4a1 <b>Вопрос 4 — «Идея, которая требует реализации»</b>\n\n"
            "У тебя есть идея:\n"
            "чат-бот, автоматизация процесса, AI-функция в продукте, внутренний помощник для команды.\n"
            "Раньше это означало: найти разработчика, объяснить задачу, ждать, получить не то.\n\n"
            "Что происходит с идеей сейчас?"
        ),
        "options": [
            ("A", "Остаётся идеей — нет ресурсов и непонятно как реализовать"),
            ("B", "Пишу ТЗ и жду, когда у разработчика появится время"),
            ("C", "Пробую no-code инструменты, но застреваю на настройке"),
            ("D", "Могу собрать рабочий прототип сам за 1–2 дня — без разработчиков"),
        ],
    },
    {
        "text": (
            "\U0001f4ca <b>Вопрос 5 — «Нужно обосновать решение данными»</b>\n\n"
            "Тебе нужно принять или защитить решение:\n"
            "какую фичу делать, стоит ли автоматизировать процесс, что приоритизировать.\n"
            "Есть данные — отзывы, метрики, таблицы, обратная связь от пользователей.\n\n"
            "Как работаешь с этим?"
        ),
        "options": [
            ("A", "Читаю всё вручную, формирую мнение интуитивно"),
            ("B", "Прошу ИИ помочь с текстом, но анализ делаю сам"),
            ("C", "Использую ИИ для первичной обработки, но не всегда знаю, как правильно сформулировать задачу"),
            ("D", "Загружаю данные в ИИ с чётким запросом — получаю структурированный анализ, паттерны и гипотезы за 30 минут"),
        ],
    },
    {
        "text": (
            "\U0001f680 <b>Вопрос 6 — «Рынок меняется быстрее, чем ты успеваешь»</b>\n\n"
            "Ты замечаешь:\n"
            "— коллеги делают за час то, на что у тебя уходит день\n"
            "— на рынке растёт спрос на специалистов с AI-компетенцией\n"
            "— компании ищут тех, кто умеет не просто использовать ИИ, "
            "но и внедрять его в продукты\n\n"
            "Что ты делаешь с этим?"
        ),
        "options": [
            ("A", "Слежу за трендом, но конкретных шагов пока нет"),
            ("B", "Читаю статьи и смотрю видео — стараюсь быть в курсе"),
            ("C", "Пробую разные инструменты, но системы нет — знания разрозненные"),
            ("D", "Целенаправленно строю AI-компетенцию: знаю, что именно нужно освоить и последовательно это делаю"),
        ],
    },
]

SCORE_MAP = {"A": 1, "B": 2, "C": 3, "D": 4}

RESULTS = [
    {
        "range": (6, 10), "title": "Наблюдатель", "emoji": "\U0001f50d",
        "text": (
            "ИИ уже рядом с тобой.\nНо пока почти не влияет на твою работу.\n\n"
            "Скорее всего:\n— многие задачи ты всё ещё делаешь вручную\n"
            "— используешь ИИ редко или эпизодически\n— не очень понятно, где именно он может помочь\n\n"
            "При этом сейчас происходит интересная вещь.\n"
            "Люди, которые встроили ИИ в рабочие процессы,\nчасто экономят 5–15 часов в неделю.\n"
            "Не потому что они гении.\nА потому что знают где и как использовать инструменты.\n\n"
            "Хорошая новость:\nпорог входа в ИИ намного ниже, чем кажется."
        ),
    },
    {
        "range": (11, 15), "title": "Экспериментатор", "emoji": "\U0001f9ea",
        "text": (
            "ИИ у тебя уже открыт в соседней вкладке.\nИногда он помогает.\nИногда выдаёт странный результат.\n\n"
            "Скорее всего:\n— ты пробуешь разные инструменты\n"
            "— но не всегда понимаешь, как правильно ставить задачу\n— знания пока фрагментарные\n\n"
            "Это самый частый уровень.\nЛюди здесь уже чувствуют потенциал ИИ,\n"
            "но пока не могут сделать его надёжным рабочим инструментом.\n\n"
            "Как только появляется система —\nэффективность резко растёт."
        ),
    },
    {
        "range": (16, 20), "title": "Практик", "emoji": "\u26a1",
        "text": (
            "ИИ уже стал частью твоей работы.\n\nТы:\n— используешь его для анализа\n"
            "— ускоряешь подготовку материалов\n— автоматизируешь часть задач\n\n"
            "Но чаще всего это личная продуктивность.\n\nСледующий уровень —\n"
            "когда ИИ начинает работать не только для тебя, но и внутри процессов:\n"
            "— в продукте\n— в команде\n— в операциях\n\nТам начинается совсем другой эффект."
        ),
    },
    {
        "range": (21, 24), "title": "AI-Ready", "emoji": "\U0001f9e0",
        "text": (
            "Ты уже понимаешь, как работать с ИИ системно.\n\nСкорее всего ты:\n"
            "— быстро тестируешь идеи\n— используешь несколько инструментов\n"
            "— умеешь получать нужный результат от моделей\n\n"
            "Это уровень, на котором люди начинают:\n— проектировать AI-решения\n"
            "— автоматизировать процессы\n— собирать рабочие прототипы\n\n"
            "Именно такие специалисты сейчас становятся\nодними из самых востребованных на рынке."
        ),
    },
]


def get_result(score: int) -> dict:
    for r in RESULTS:
        if r["range"][0] <= score <= r["range"][1]:
            return r
    return RESULTS[-1]


# ══════════════════════════════ БАЗА ДАННЫХ ══════════════════════════════


def _connect():
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id   INTEGER NOT NULL,
                username      TEXT,
                email         TEXT,
                score         INTEGER,
                archetype     TEXT,
                created_at    TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS posts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                type            TEXT NOT NULL,
                text_html       TEXT,
                photo_id        TEXT,
                case_options    TEXT,
                case_answer_html TEXT,
                webinar_link    TEXT,
                scheduled_date  TEXT,
                scheduled_time  TEXT,
                is_sent         INTEGER DEFAULT 0,
                created_at      TEXT,
                created_by      INTEGER
            );
            CREATE TABLE IF NOT EXISTS leads (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id   INTEGER NOT NULL,
                username      TEXT,
                name          TEXT,
                phone         TEXT,
                email         TEXT,
                tg_nick       TEXT,
                source        TEXT,
                created_at    TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sent_broadcasts (
                post_id       INTEGER,
                telegram_id   INTEGER,
                sent_at       TEXT,
                PRIMARY KEY (post_id, telegram_id)
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS bot_users (
                telegram_id   INTEGER PRIMARY KEY,
                username      TEXT,
                first_name    TEXT,
                source        TEXT DEFAULT '',
                created_at    TEXT NOT NULL,
                is_blocked    INTEGER DEFAULT 0,
                blocked_at    TEXT
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                label           TEXT,
                total_users     INTEGER,
                active_users    INTEGER,
                quiz_completed  INTEGER,
                leads_count     INTEGER,
                created_at      TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_tags (
                telegram_id   INTEGER NOT NULL,
                tag           TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                PRIMARY KEY (telegram_id, tag)
            );
            CREATE TABLE IF NOT EXISTS webinar_flows (
                slug            TEXT PRIMARY KEY,
                title           TEXT,
                start_text      TEXT,
                start_photo     TEXT,
                confirm_text    TEXT,
                cta_text        TEXT,
                cta_url         TEXT,
                start_buttons_json TEXT,
                created_at      TEXT NOT NULL
            );
        """)
        for col in ("quiz_started INTEGER DEFAULT 0", "quiz_completed INTEGER DEFAULT 0"):
            try:
                conn.execute(f"ALTER TABLE bot_users ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass
        for col in ("button_text TEXT", "button_url TEXT", "include_tag TEXT", "webinar_slug TEXT"):
            try:
                conn.execute(f"ALTER TABLE posts ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass
        try:
            conn.execute("ALTER TABLE webinar_flows ADD COLUMN start_buttons_json TEXT")
        except sqlite3.OperationalError:
            pass


# --- users ---

def save_user(telegram_id: int, username: str, email: str, score: int, archetype: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO users (telegram_id, username, email, score, archetype, created_at) VALUES (?,?,?,?,?,?)",
            (telegram_id, username, email, score, archetype, now_msk().isoformat()),
        )


def get_all_subscriber_ids() -> list[int]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT telegram_id FROM bot_users WHERE is_blocked=0 "
            "UNION SELECT DISTINCT telegram_id FROM users"
        ).fetchall()
    return [r[0] for r in rows]


def export_users_csv() -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["telegram_id", "username", "email", "score", "archetype", "created_at"])
    with _connect() as conn:
        for row in conn.execute("SELECT telegram_id,username,email,score,archetype,created_at FROM users ORDER BY id"):
            w.writerow(row)
    return buf.getvalue()


# --- posts ---

def create_post(ptype: str, text_html: str = None, photo_id: str = None,
                case_options: list = None, case_answer_html: str = None,
                webinar_link: str = None, created_by: int = 0,
                button_text: str = None, button_url: str = None,
                include_tag: str = None, webinar_slug: str = None) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO posts (type,text_html,photo_id,case_options,case_answer_html,webinar_link,created_at,created_by,"
            "button_text,button_url,include_tag,webinar_slug) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (ptype, text_html, photo_id,
             json.dumps(case_options) if case_options else None,
             case_answer_html, webinar_link, now_msk().isoformat(), created_by,
             button_text, button_url, include_tag, webinar_slug),
        )
        return cur.lastrowid


def get_post(post_id: int) -> dict | None:
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    if d.get("case_options"):
        d["case_options"] = json.loads(d["case_options"])
    return d


def get_all_posts() -> list[dict]:
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM posts ORDER BY scheduled_date, scheduled_time, id").fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get("case_options"):
            d["case_options"] = json.loads(d["case_options"])
        result.append(d)
    return result


def update_post_schedule(post_id: int, date: str, time: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("UPDATE posts SET scheduled_date=?, scheduled_time=?, is_sent=0 WHERE id=?",
                           (date, time, post_id))
        return cur.rowcount > 0


def update_post_target(post_id: int, include_tag: str | None) -> bool:
    with _connect() as conn:
        cur = conn.execute("UPDATE posts SET include_tag=? WHERE id=?", (include_tag, post_id))
        return cur.rowcount > 0


def update_post_button(post_id: int, button_text: str, button_url: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("UPDATE posts SET button_text=?, button_url=? WHERE id=?",
                           (button_text, button_url, post_id))
        return cur.rowcount > 0


def delete_post_db(post_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM posts WHERE id=?", (post_id,))
        conn.execute("DELETE FROM sent_broadcasts WHERE post_id=?", (post_id,))
        return cur.rowcount > 0


def get_due_posts() -> list[dict]:
    n = now_msk()
    today = n.strftime("%Y-%m-%d")
    now_time = n.strftime("%H:%M")
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM posts WHERE is_sent=0 AND scheduled_date IS NOT NULL "
            "AND (scheduled_date < ? OR (scheduled_date = ? AND scheduled_time <= ?))",
            (today, today, now_time),
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get("case_options"):
            d["case_options"] = json.loads(d["case_options"])
        result.append(d)
    return result


def mark_post_sent(post_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE posts SET is_sent=1 WHERE id=?", (post_id,))


def is_broadcast_sent(post_id: int, telegram_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM sent_broadcasts WHERE post_id=? AND telegram_id=?",
                           (post_id, telegram_id)).fetchone()
    return row is not None


def mark_broadcast_sent(post_id: int, telegram_id: int) -> None:
    with _connect() as conn:
        conn.execute("INSERT OR IGNORE INTO sent_broadcasts (post_id, telegram_id, sent_at) VALUES (?,?,?)",
                     (post_id, telegram_id, now_msk().isoformat()))


# --- leads ---

def save_lead(telegram_id: int, username: str, name: str, phone: str,
              email: str, tg_nick: str, source: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO leads (telegram_id,username,name,phone,email,tg_nick,source,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (telegram_id, username, name, phone, email, tg_nick, source, now_msk().isoformat()),
        )


def export_leads_csv() -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["telegram_id", "username", "name", "phone", "email", "tg_nick", "source", "created_at"])
    with _connect() as conn:
        for row in conn.execute("SELECT telegram_id,username,name,phone,email,tg_nick,source,created_at FROM leads ORDER BY id"):
            w.writerow(row)
    return buf.getvalue()


def get_stats() -> dict:
    with _connect() as conn:
        users_count = conn.execute("SELECT COUNT(DISTINCT telegram_id) FROM users").fetchone()[0]
        leads_count = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        posts_total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        posts_sent = conn.execute("SELECT COUNT(*) FROM posts WHERE is_sent=1").fetchone()[0]
        posts_scheduled = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE is_sent=0 AND scheduled_date IS NOT NULL").fetchone()[0]
    return {
        "users": users_count, "leads": leads_count,
        "posts_total": posts_total, "posts_sent": posts_sent, "posts_scheduled": posts_scheduled,
    }


# --- bot_users ---

def track_bot_user(telegram_id: int, username: str, first_name: str, source: str = "") -> bool:
    """Track user who pressed /start. Returns True if new user."""
    with _connect() as conn:
        existing = conn.execute(
            "SELECT telegram_id FROM bot_users WHERE telegram_id=?", (telegram_id,)
        ).fetchone()
        if existing:
            if source:
                conn.execute(
                    "UPDATE bot_users SET username=?, first_name=?, source=?, is_blocked=0, blocked_at=NULL WHERE telegram_id=?",
                    (username, first_name, source, telegram_id),
                )
            else:
                conn.execute(
                    "UPDATE bot_users SET username=?, first_name=?, is_blocked=0, blocked_at=NULL WHERE telegram_id=?",
                    (username, first_name, telegram_id),
                )
            return False
        conn.execute(
            "INSERT INTO bot_users (telegram_id, username, first_name, source, created_at) VALUES (?,?,?,?,?)",
            (telegram_id, username, first_name, source, now_msk().isoformat()),
        )
        return True


def mark_user_blocked(telegram_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE bot_users SET is_blocked=1, blocked_at=? WHERE telegram_id=?",
            (now_msk().isoformat(), telegram_id),
        )


def mark_quiz_started(telegram_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE bot_users SET quiz_started=1 WHERE telegram_id=?", (telegram_id,))


def mark_quiz_completed(telegram_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE bot_users SET quiz_completed=1 WHERE telegram_id=?", (telegram_id,))


def get_bot_users_stats() -> dict:
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM bot_users").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM bot_users WHERE is_blocked=0").fetchone()[0]
        blocked = conn.execute("SELECT COUNT(*) FROM bot_users WHERE is_blocked=1").fetchone()[0]
        today = now_msk().strftime("%Y-%m-%d")
        new_today = conn.execute(
            "SELECT COUNT(*) FROM bot_users WHERE created_at >= ?", (today,)
        ).fetchone()[0]
        week_ago = (now_msk() - timedelta(days=7)).strftime("%Y-%m-%d")
        new_week = conn.execute(
            "SELECT COUNT(*) FROM bot_users WHERE created_at >= ?", (week_ago,)
        ).fetchone()[0]
    return {
        "total": total, "active": active, "blocked": blocked,
        "new_today": new_today, "new_week": new_week,
    }


def get_funnel_stats() -> dict:
    with _connect() as conn:
        started_bot = conn.execute("SELECT COUNT(*) FROM bot_users").fetchone()[0]
        started_quiz = conn.execute("SELECT COUNT(*) FROM bot_users WHERE quiz_started=1").fetchone()[0]
        completed_quiz = conn.execute("SELECT COUNT(*) FROM bot_users WHERE quiz_completed=1").fetchone()[0]
        left_email = conn.execute(
            "SELECT COUNT(DISTINCT telegram_id) FROM users WHERE email IS NOT NULL AND email != ''"
        ).fetchone()[0]
        leads = conn.execute("SELECT COUNT(DISTINCT telegram_id) FROM leads").fetchone()[0]
    return {
        "started_bot": started_bot, "started_quiz": started_quiz,
        "completed_quiz": completed_quiz, "left_email": left_email, "leads": leads,
    }


def get_sources_stats() -> list[tuple[str, int]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT COALESCE(NULLIF(source,''), '\u043e\u0440\u0433\u0430\u043d\u0438\u043a\u0430') as src, COUNT(*) as cnt "
            "FROM bot_users GROUP BY src ORDER BY cnt DESC"
        ).fetchall()
    return rows


def get_archetype_distribution() -> list[tuple[str, int]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT archetype, COUNT(*) as cnt FROM users "
            "WHERE archetype IS NOT NULL GROUP BY archetype ORDER BY cnt DESC"
        ).fetchall()
    return rows


# --- snapshots ---

def save_snapshot(label: str, total: int, active: int, quiz: int, leads: int) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO snapshots (label, total_users, active_users, quiz_completed, leads_count, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (label, total, active, quiz, leads, now_msk().isoformat()),
        )
        return cur.lastrowid


def get_last_snapshot() -> dict | None:
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def migrate_existing_users() -> int:
    """One-time migration: copy users from quiz results into bot_users."""
    with _connect() as conn:
        migrated = 0
        rows = conn.execute("SELECT DISTINCT telegram_id, username, created_at FROM users").fetchall()
        for tid, uname, created in rows:
            existing = conn.execute("SELECT 1 FROM bot_users WHERE telegram_id=?", (tid,)).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO bot_users (telegram_id, username, first_name, source, created_at, quiz_started, quiz_completed) "
                    "VALUES (?,?,?,?,?,1,1)",
                    (tid, uname or "", "", "migrated_from_quiz", created),
                )
                migrated += 1
            else:
                conn.execute(
                    "UPDATE bot_users SET quiz_started=1, quiz_completed=1 WHERE telegram_id=?",
                    (tid,),
                )
        return migrated


# --- tags ---

def add_user_tag(telegram_id: int, tag: str) -> None:
    tag = (tag or "").strip().lower()
    if not tag:
        return
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO user_tags (telegram_id, tag, created_at) VALUES (?,?,?)",
            (telegram_id, tag, now_msk().isoformat()),
        )


def remove_user_tag(telegram_id: int, tag: str) -> None:
    tag = (tag or "").strip().lower()
    if not tag:
        return
    with _connect() as conn:
        conn.execute("DELETE FROM user_tags WHERE telegram_id=? AND tag=?", (telegram_id, tag))


def get_tag_user_ids(tag: str) -> list[int]:
    tag = (tag or "").strip().lower()
    if not tag:
        return []
    with _connect() as conn:
        rows = conn.execute(
            "SELECT telegram_id FROM user_tags WHERE tag=?", (tag,)
        ).fetchall()
    return [r[0] for r in rows]


def get_all_tags_stats() -> list[tuple[str, int]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT tag, COUNT(*) as cnt FROM user_tags GROUP BY tag ORDER BY cnt DESC, tag"
        ).fetchall()
    return rows


# --- webinar flow ---

def set_webinar_flow(slug: str, title: str, start_text: str, start_photo: str,
                     confirm_text: str, cta_text: str, cta_url: str,
                     start_buttons_json: str | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO webinar_flows (slug,title,start_text,start_photo,confirm_text,cta_text,cta_url,start_buttons_json,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (slug, title, start_text, start_photo, confirm_text, cta_text, cta_url, start_buttons_json, now_msk().isoformat()),
        )


def parse_webinar_start_buttons(raw: str) -> tuple[list[dict] | None, str]:
    """Parse multiline start buttons. Each line: 'Текст | https://url' or a line without | for opt-in button text.
    Returns (buttons, error). buttons ordered top-to-bottom."""
    raw = (raw or "").strip()
    if not raw or raw == "-":
        return ([{"type": "optin", "text": "✅ Записаться"}], "")
    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    out: list[dict] = []
    optin_count = 0
    for line in lines:
        if "|" in line:
            t, u = [x.strip() for x in line.split("|", 1)]
            if u.startswith("http"):
                if not t:
                    return None, "Пустой текст кнопки в строке со ссылкой."
                out.append({"type": "url", "text": t, "url": u})
            else:
                return None, f"После «|» должна быть ссылка http(s). Строка: {line[:50]}..."
        else:
            optin_count += 1
            if optin_count > 1:
                return None, "Только одна кнопка записи (строка без ссылки)."
            out.append({"type": "optin", "text": line})
    if optin_count == 0:
        out.insert(0, {"type": "optin", "text": "✅ Записаться"})
    return (out, "")


def webinar_flow_start_keyboard(slug: str, flow: dict) -> InlineKeyboardMarkup:
    """Кнопки под стартовым сообщением вебинара (интерактивный блок)."""
    rows: list[list[InlineKeyboardButton]] = []
    js = flow.get("start_buttons_json")
    if js:
        try:
            buttons = json.loads(js)
            for b in buttons:
                if b.get("type") == "optin":
                    rows.append([InlineKeyboardButton(b.get("text") or "Записаться", callback_data=f"wb_join_{slug}")])
                elif b.get("type") == "url" and b.get("url"):
                    rows.append([InlineKeyboardButton(b["text"], url=b["url"])])
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
    if not rows:
        rows.append([InlineKeyboardButton("✅ Записаться", callback_data=f"wb_join_{slug}")])
        if flow.get("cta_text") and flow.get("cta_url"):
            rows.append([InlineKeyboardButton(flow["cta_text"], url=flow["cta_url"])])
    return InlineKeyboardMarkup(rows)


def parse_url_buttons_lines(raw: str) -> tuple[str | None, str]:
    """Для обычного /start: только кнопки-ссылки, формат построчно Текст | URL. Пусто или — очистить."""
    raw = (raw or "").strip()
    if not raw or raw == "-":
        return ("[]", "")
    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    lst = []
    for line in lines:
        if "|" not in line:
            return (None, f"Каждая строка: Текст | URL. Ошибка: {line[:40]}...")
        t, u = [x.strip() for x in line.split("|", 1)]
        if not t or not u.startswith("http"):
            return (None, "Нужен формат: Текст | https://...")
        lst.append({"text": t, "url": u})
    return (json.dumps(lst, ensure_ascii=False), "")


def get_webinar_flow(slug: str) -> dict | None:
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM webinar_flows WHERE slug=?", (slug,)).fetchone()
    return dict(row) if row else None


# --- settings ---

DEFAULT_START_MESSAGE = (
    "Привет!\n\nЭтот тест определит твой <b>AI-профиль</b>.\n\n"
    "6 вопросов — ситуации из реального рабочего дня.\n"
    "Выбери вариант, который ближе всего к тебе.\n"
    "Правильных и неправильных ответов нет.\n\n"
    "Нажми кнопку ниже, чтобы начать"
)


def get_setting(key: str, default: str = "") -> str:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))


def _start_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("Начать тест", callback_data="start_quiz")]]
    extra = get_setting("start_inline_buttons", "").strip()
    if extra:
        try:
            for b in json.loads(extra):
                if b.get("text") and b.get("url", "").startswith("http"):
                    rows.append([InlineKeyboardButton(b["text"], url=b["url"])])
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
    if len(rows) == 1:
        btn_text = get_setting("start_button_text", "").strip()
        btn_url = get_setting("start_button_url", "").strip()
        if btn_text and btn_url:
            rows.append([InlineKeyboardButton(btn_text, url=btn_url)])
    return InlineKeyboardMarkup(rows)


# ══════════════════════════════ EMAIL ══════════════════════════════


def build_email_html(archetype_emoji: str, archetype_title: str, archetype_text: str, score: int) -> str:
    archetype_html = archetype_text.replace("\n", "<br>")
    tools_html = """
    <tr><td style="padding:20px 30px;">
      <h2 style="color:#1a1a2e;font-size:22px;margin:0 0 20px 0;">10 AI-инструментов</h2>
      <p style="color:#555;font-size:15px;margin:0 0 24px 0;">Которые чаще всего используют продакты, аналитики и маркетологи</p>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://chat.openai.com" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">1. ChatGPT (OpenAI)</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">Универсальный рабочий инструмент: анализ фидбека, генерация гипотез, подготовка PRD и брифов, работа с данными.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://claude.ai" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">2. Claude</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">Аналитика и работа с большими документами: исследования, структурирование информации, подготовка аргументов.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://perplexity.ai" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">3. Perplexity</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">AI-поисковик: быстрый ресёрч рынка, поиск статистики, анализ трендов.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://gemini.google.com" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">4. Gemini</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">AI-ассистент Google: анализ данных в Docs и Sheets, аналитические заметки, идеи для маркетинга.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://github.com/features/copilot" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">5. GitHub Copilot</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">AI для кода: проверка технических гипотез, скрипты, понимание кода продукта.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://replit.com" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">6. Replit AI</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">Быстрое создание прототипов: MVP, тестирование AI-идей, внутренние инструменты.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://chat.deepseek.com" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">7. DeepSeek</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">Аналитика и логические задачи: анализ данных, продуктовые гипотезы, структурирование решений.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://chat.qwen.ai" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">8. Qwen</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">Обработка больших массивов текста, анализ пользовательских запросов, AI-ассистенты.</p></td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><a href="https://manus.ai" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">9. Manus</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">AI-агент для сложных многоступенчатых задач: ресёрч, аналитика, прототипирование без кода.</p><p style="color:#999;font-size:12px;margin:4px 0 0 0;font-style:italic;">* Компания Meta признана экстремистской и запрещена в РФ</p></td></tr>
        <tr><td style="padding:14px 0;"><a href="https://github.com/open-claude" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">10. OpenClaw</a><p style="color:#555;font-size:14px;margin:6px 0 0 0;">Open-source: внутренние AI-ассистенты, корпоративные документы, прототипирование без внешних API.</p></td></tr>
      </table>
    </td></tr>"""
    return f"""\
<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f7;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f7;padding:30px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
  <tr><td style="background:#1a1a2e;padding:30px;text-align:center;">
    <h1 style="color:#fff;font-size:24px;margin:0;font-weight:700;">Gigaschool</h1>
    <p style="color:#a0a0c0;font-size:14px;margin:8px 0 0 0;">Твой AI-профиль</p>
  </td></tr>
  <tr><td style="padding:30px 30px 10px 30px;">
    <div style="background:#f0f0ff;border-radius:10px;padding:24px;text-align:center;">
      <p style="font-size:40px;margin:0 0 8px 0;">{archetype_emoji}</p>
      <h2 style="color:#1a1a2e;font-size:22px;margin:0 0 6px 0;">{archetype_title}</h2>
      <p style="color:#4F46E5;font-size:15px;margin:0;font-weight:600;">{score} из 24 баллов</p>
    </div>
  </td></tr>
  <tr><td style="padding:10px 30px 30px 30px;"><p style="color:#333;font-size:15px;line-height:1.7;">{archetype_html}</p></td></tr>
  <tr><td style="padding:0 30px;"><hr style="border:none;border-top:2px solid #f0f0f0;margin:0;"></td></tr>
  {tools_html}
  <tr><td style="background:#1a1a2e;padding:24px 30px;text-align:center;">
    <p style="color:#a0a0c0;font-size:13px;margin:0;">Gigaschool &copy; {datetime.now().year}</p>
  </td></tr>
</table></td></tr></table></body></html>"""


def send_email(to_email: str, score: int, result: dict) -> bool:
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        logger.warning("SMTP not configured, skipping email")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Твой AI-профиль: {result['title']} — Gigaschool"
        msg["From"] = formataddr(("Gigaschool", SMTP_EMAIL))
        msg["To"] = to_email
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=SMTP_EMAIL.split("@")[-1])
        msg["Return-Path"] = SMTP_EMAIL
        msg["Reply-To"] = SMTP_EMAIL
        msg["X-Mailer"] = "Gigaschool Quiz Bot"
        msg["MIME-Version"] = "1.0"
        msg.attach(MIMEText(build_email_html(result["emoji"], result["title"], result["text"], score), "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.yandex.ru", 465, timeout=15) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        logger.info(f"Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


# ══════════════════════════════ КВИЗ ══════════════════════════════


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    source = context.args[0] if context.args else ""
    track_bot_user(user.id, user.username or "", user.first_name or "", source)

    context.user_data.clear()
    context.user_data["score"] = 0
    context.user_data["question_idx"] = 0

    # Deep-link webinar flow: /start webinar_x
    if source.startswith("webinar_"):
        flow = get_webinar_flow(source)
        if flow:
            tag = f"{source}_optin"
            markup = webinar_flow_start_keyboard(source, flow)
            text = flow.get("start_text") or "Ближайший вебинар. Нажмите кнопку, чтобы записаться."
            if flow.get("start_photo"):
                await update.message.reply_photo(
                    photo=flow["start_photo"],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            else:
                await update.message.reply_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            # Keep tag name in user_data for possible follow-up UX.
            context.user_data["last_webinar_tag"] = tag
            return

    quiz_enabled = get_setting("quiz_enabled", "1") == "1"

    if not quiz_enabled:
        # Квиз отключён — сразу показываем полезную информацию
        await update.message.reply_text(
            "\U0001f44b <b>Привет!</b>\n\n"
            "Мы подготовили для тебя подборку полезных AI-инструментов:",
            parse_mode="HTML",
        )
        keyboard = [[InlineKeyboardButton("Пройти тест", callback_data="start_quiz")]]
        await context.bot.send_message(
            chat_id=update.message.chat_id, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True,
            text=f"{AI_TOOLS_TEXT}\n\n"
                 f"─────────────────────\n\n"
                 f"<i>Хочешь узнать свой AI-профиль? Нажми кнопку ниже</i>",
        )
        return

    start_text = get_setting("start_message", DEFAULT_START_MESSAGE)
    start_photo = get_setting("start_photo", "")

    markup = _start_keyboard()

    if start_photo:
        await update.message.reply_photo(
            photo=start_photo, caption=start_text,
            reply_markup=markup, parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            start_text, reply_markup=markup, parse_mode="HTML",
        )


async def send_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    idx = context.user_data.get("question_idx", 0)
    if idx >= len(QUESTIONS):
        mark_quiz_completed(chat_id)
        await ask_email(chat_id, context)
        return
    q = QUESTIONS[idx]
    opts = "\n".join(f"\n<b>{l})</b> {t}" for l, t in q["options"])
    keyboard = [[
        InlineKeyboardButton("A", callback_data="answer_A"),
        InlineKeyboardButton("B", callback_data="answer_B"),
        InlineKeyboardButton("C", callback_data="answer_C"),
        InlineKeyboardButton("D", callback_data="answer_D"),
    ]]
    await context.bot.send_message(chat_id=chat_id, text=f"{q['text']}\n{opts}",
                                   reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def ask_email(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_email"] = True
    await context.bot.send_message(
        chat_id=chat_id, parse_mode="HTML",
        text=("<b>Твой результат готов.</b>\n\n"
              "Мы определили твой AI-профиль и подготовили разбор.\n\n"
              "Оставь свою почту — продублируем результаты и подборку "
              "AI-инструментов на email, чтобы не потерялись.\n\n"
              "Напиши свой email"),
    )


AI_TOOLS_TEXT = (
    "\U0001f9f0 <b>10 AI-инструментов</b>\n"
    "<i>Которые чаще всего используют продакты, аналитики и маркетологи</i>\n\n"
    "1. <a href='https://chat.openai.com'>ChatGPT (OpenAI)</a> — анализ фидбека, генерация гипотез, подготовка PRD и брифов\n\n"
    "2. <a href='https://claude.ai'>Claude</a> — аналитика и работа с большими документами, структурирование информации\n\n"
    "3. <a href='https://perplexity.ai'>Perplexity</a> — AI-поисковик: быстрый ресёрч рынка, поиск статистики, тренды\n\n"
    "4. <a href='https://gemini.google.com'>Gemini</a> — анализ данных в Google Docs и Sheets, идеи для маркетинга\n\n"
    "5. <a href='https://github.com/features/copilot'>GitHub Copilot</a> — проверка технических гипотез, скрипты, понимание кода\n\n"
    "6. <a href='https://replit.com'>Replit AI</a> — быстрое создание прототипов, MVP, внутренние инструменты\n\n"
    "7. <a href='https://chat.deepseek.com'>DeepSeek</a> — аналитика и логические задачи, продуктовые гипотезы\n\n"
    "8. <a href='https://chat.qwen.ai'>Qwen</a> — обработка больших массивов текста, AI-ассистенты\n\n"
    "9. <a href='https://manus.ai'>Manus</a> — AI-агент для сложных многоступенчатых задач, прототипирование без кода (компания Meta признана экстремистской и запрещена в РФ)\n\n"
    "10. <a href='https://github.com/open-claude'>OpenClaw</a> — open-source: внутренние AI-ассистенты, корпоративные документы"
)


async def show_quiz_result(chat_id: int, context: ContextTypes.DEFAULT_TYPE, email_sent: bool) -> None:
    score = context.user_data.get("score", 0)
    result = get_result(score)
    status = ("Также продублировали вам на почту!"
              if email_sent else "Не удалось отправить письмо. Проверь адрес и попробуй ещё раз через /start")
    keyboard = [[InlineKeyboardButton("Пройти ещё раз", callback_data="restart_quiz")]]

    # Сообщение 1: AI-профиль
    await context.bot.send_message(
        chat_id=chat_id, parse_mode="HTML",
        text=(f"{result['emoji']} <b>Твой AI-профиль: {result['title']}</b>\n\n"
              f"Результат: <b>{score} из 24 баллов</b>\n\n"
              f"─────────────────────\n\n{result['text']}"),
    )

    # Сообщение 2: 10 AI-инструментов + статус письма + кнопка
    await context.bot.send_message(
        chat_id=chat_id, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True,
        text=(f"{AI_TOOLS_TEXT}\n\n"
              f"─────────────────────\n\n\U0001f4e9 {status}"),
    )


# ══════════════════════════════ АДМИН КОМАНДЫ ══════════════════════════════


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "<b>\U0001f527 Команды администратора</b>\n\n"
        "<b>1) Старт и квиз:</b>\n"
        "/set_start — Изменить приветствие (текст/фото)\n"
        "/set_start_button <code>Текст | URL</code> — Одна кнопка-ссылка в старте\n"
        "/set_start_buttons — Несколько кнопок-ссылок (интерактивный старт)\n"
        "/preview_start — Посмотреть текущее приветствие\n"
        "/reset_start — Сбросить на стандартное\n"
        "/toggle_quiz — Включить/выключить квиз\n\n"
        "<b>2) Создание контента:</b>\n"
        "/newpost — Обычный пост (текст и/или фото)\n"
        "/newcase — Интерактив-кейс (ситуация + варианты + разбор эксперта)\n"
        "/newsale — Пост с формой сбора контактов (имя, телефон, email, ник)\n"
        "/newwebinar — Анонс вебинара (текст + slug + ссылка)\n"
        "/cancel — Отменить текущее создание\n\n"
        "<b>3) Вебинарный flow и сегменты:</b>\n"
        "/new_webinar_flow <code>webinar_x</code> — Старт по deep-link <code>?start=webinar_x</code>\n"
        "/tags — Показать метки и размеры сегментов\n"
        "/target <code>ID TAG|all</code> — Ограничить рассылку поста по метке\n\n"
        "<b>4) Управление постами и рассылкой:</b>\n"
        "/posts — Список всех постов\n"
        "/preview <code>ID</code> — Предпросмотр поста (как его увидят подписчики)\n"
        "/schedule <code>ID ГГГГ-ММ-ДД ЧЧ:ММ</code> — Запланировать отправку (МСК)\n"
        "/send_now <code>ID</code> — Отправить всем прямо сейчас\n"
        "/set_button <code>ID Текст | URL</code> — Добавить кнопку-ссылку в пост\n"
        "/delete_post <code>ID</code> — Удалить пост\n\n"
        "<b>5) Аналитика и выгрузки:</b>\n"
        "/stats — Расширенная статистика бота\n"
        "/funnel — Воронка конверсии\n"
        "/sources — Источники трафика (UTM)\n"
        "/snapshot <code>метка</code> — Снимок аудитории (для сравнения до/после рекламы)\n"
        "/compare — Сравнить с последним снимком\n"
        "/check_active — Проверить кто заблокировал бота\n"
        "/export — Выгрузить пользователей квиза (CSV)\n"
        "/export_leads — Выгрузить заявки из форм (CSV)\n",
        parse_mode="HTML",
    )


def _clear_admin_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in ["admin_state", "admin_draft"]:
        context.user_data.pop(key, None)


async def cmd_newpost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    _clear_admin_state(context)
    context.user_data["admin_state"] = "awaiting_post_content"
    context.user_data["admin_draft"] = {"type": "post"}
    await update.message.reply_text(
        "\U0001f4dd <b>Создание поста</b>\n\n"
        "Отправьте содержимое поста.\n"
        "Можно использовать <b>жирный</b>, <i>курсив</i>, эмодзи, ссылки.\n"
        "Можно прикрепить фото.\n\n"
        "Пост будет выглядеть точно так, как вы его напишете.\n"
        "/cancel — отменить", parse_mode="HTML",
    )


async def cmd_newcase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    _clear_admin_state(context)
    context.user_data["admin_state"] = "awaiting_case_content"
    context.user_data["admin_draft"] = {"type": "case"}
    await update.message.reply_text(
        "\U0001f9e9 <b>Создание интерактив-кейса</b>\n\n"
        "<b>Шаг 1 из 3:</b> Отправьте описание ситуации/кейса.\n"
        "Можно с фото, форматированием, эмодзи.\n\n"
        "/cancel — отменить", parse_mode="HTML",
    )


async def cmd_newsale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    _clear_admin_state(context)
    context.user_data["admin_state"] = "awaiting_sale_content"
    context.user_data["admin_draft"] = {"type": "sale"}
    await update.message.reply_text(
        "\U0001f4b0 <b>Создание поста с формой</b>\n\n"
        "Отправьте текст анонса/продажи.\n"
        "Можно с фото, форматированием, эмодзи.\n\n"
        "После поста автоматически добавится кнопка\n"
        "«Оставить заявку» — пользователь заполнит: имя, телефон, email, ник.\n\n"
        "/cancel — отменить", parse_mode="HTML",
    )


async def cmd_newwebinar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    _clear_admin_state(context)
    context.user_data["admin_state"] = "awaiting_webinar_content"
    context.user_data["admin_draft"] = {"type": "webinar"}
    await update.message.reply_text(
        "\U0001f4e2 <b>Создание анонса вебинара</b>\n\n"
        "<b>Шаг 1 из 3:</b> Отправьте текст анонса.\n"
        "Можно с фото, форматированием, эмодзи.\n\n"
        "/cancel — отменить", parse_mode="HTML",
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    _clear_admin_state(context)
    await update.message.reply_text("Действие отменено.")


async def cmd_posts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    posts = get_all_posts()
    if not posts:
        await update.message.reply_text("Постов пока нет. Создайте первый: /newpost")
        return
    lines = ["\U0001f4cb <b>Все посты:</b>\n"]
    for p in posts:
        emoji = POST_TYPE_EMOJI.get(p["type"], "")
        name = POST_TYPE_NAME.get(p["type"], p["type"])
        if p["is_sent"]:
            status = "\u2705 Отправлен"
        elif p["scheduled_date"]:
            status = f"\u23f3 {p['scheduled_date']} {p['scheduled_time'] or ''}"
        else:
            status = "\u23f8 Не запланирован"
        target = p.get("include_tag") or "all"
        preview = (p.get("text_html") or "")[:40].replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
        if len(p.get("text_html") or "") > 40:
            preview += "..."
        lines.append(f"<b>#{p['id']}</b> {emoji} {name} | {status} | 🎯 {target}\n<i>{preview}</i>\n")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def _send_post_preview(chat_id: int, post: dict, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет пост одному пользователю (для preview и broadcast)."""
    buttons = []

    if post["type"] == "case" and post.get("case_options"):
        for i, opt in enumerate(post["case_options"]):
            buttons.append([InlineKeyboardButton(opt, callback_data=f"case_{post['id']}_{i}")])

    elif post["type"] == "sale":
        buttons.append([InlineKeyboardButton("\U0001f4dd Оставить заявку", callback_data=f"form_{post['id']}")])

    elif post["type"] == "webinar" and post.get("webinar_slug"):
        buttons.append([InlineKeyboardButton("✅ Записаться", callback_data=f"wb_join_{post['webinar_slug']}")])
        if post.get("webinar_link"):
            buttons.append([InlineKeyboardButton("\U0001f517 Регистрация", url=post["webinar_link"])])
    elif post["type"] == "webinar" and post.get("webinar_link"):
        buttons.append([InlineKeyboardButton("\U0001f517 Зарегистрироваться", url=post["webinar_link"])])

    if post.get("button_text") and post.get("button_url"):
        buttons.append([InlineKeyboardButton(post["button_text"], url=post["button_url"])])

    keyboard = InlineKeyboardMarkup(buttons) if buttons else None

    if post.get("photo_id"):
        await context.bot.send_photo(
            chat_id=chat_id, photo=post["photo_id"],
            caption=post.get("text_html"), parse_mode="HTML",
            reply_markup=keyboard,
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id, text=post.get("text_html") or "(пустой пост)",
            parse_mode="HTML", reply_markup=keyboard,
        )


async def cmd_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Использование: /preview <code>ID</code>", parse_mode="HTML")
        return
    try:
        post_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом.")
        return
    post = get_post(post_id)
    if not post:
        await update.message.reply_text(f"Пост #{post_id} не найден.")
        return
    await update.message.reply_text(f"\U0001f441 <b>Предпросмотр поста #{post_id}:</b>", parse_mode="HTML")
    await _send_post_preview(update.effective_chat.id, post, context)


async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 3:
        await update.message.reply_text(
            "Использование: /schedule <code>ID ГГГГ-ММ-ДД ЧЧ:ММ</code>\n"
            "Пример: <code>/schedule 5 2026-03-17 10:00</code>\n"
            "Время — московское (МСК).", parse_mode="HTML")
        return
    try:
        post_id = int(context.args[0])
        date_str = context.args[1]
        time_str = context.args[2]
        datetime.strptime(date_str, "%Y-%m-%d")
        datetime.strptime(time_str, "%H:%M")
    except (ValueError, IndexError):
        await update.message.reply_text("Неверный формат. Пример: /schedule 5 2026-03-17 10:00")
        return
    if not update_post_schedule(post_id, date_str, time_str):
        await update.message.reply_text(f"Пост #{post_id} не найден.")
        return
    await update.message.reply_text(
        f"\u2705 Пост <b>#{post_id}</b> запланирован на <b>{date_str} {time_str}</b> (МСК).",
        parse_mode="HTML")


async def cmd_send_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Использование: /send_now <code>ID</code>", parse_mode="HTML")
        return
    try:
        post_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом.")
        return
    post = get_post(post_id)
    if not post:
        await update.message.reply_text(f"Пост #{post_id} не найден.")
        return
    await update.message.reply_text(f"\U0001f4e4 Отправляю пост #{post_id} всем подписчикам...")
    sent, failed = await broadcast_post(post, context)
    mark_post_sent(post_id)
    await update.message.reply_text(f"\u2705 Готово! Отправлено: {sent}, ошибок: {failed}.")


async def cmd_delete_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Использование: /delete_post <code>ID</code>", parse_mode="HTML")
        return
    try:
        post_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом.")
        return
    if delete_post_db(post_id):
        await update.message.reply_text(f"\U0001f5d1 Пост #{post_id} удалён.")
    else:
        await update.message.reply_text(f"Пост #{post_id} не найден.")


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    data = export_users_csv()
    buf = io.BytesIO(data.encode("utf-8-sig"))
    buf.name = f"users_{now_msk().strftime('%Y%m%d_%H%M%S')}.csv"
    await update.message.reply_document(document=buf,
                                        caption=f"Пользователи квиза ({now_msk().strftime('%d.%m.%Y %H:%M')})")


async def cmd_export_leads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    data = export_leads_csv()
    buf = io.BytesIO(data.encode("utf-8-sig"))
    buf.name = f"leads_{now_msk().strftime('%Y%m%d_%H%M%S')}.csv"
    await update.message.reply_document(document=buf,
                                        caption=f"Заявки ({now_msk().strftime('%d.%m.%Y %H:%M')})")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    s = get_stats()
    b = get_bot_users_stats()
    archetypes = get_archetype_distribution()

    arch_text = ""
    if archetypes:
        total_quiz = sum(cnt for _, cnt in archetypes)
        arch_lines = "\n".join(
            f"  {name}: <b>{cnt}</b> ({round(cnt / total_quiz * 100)}%)"
            for name, cnt in archetypes
        )
        arch_text = f"\n\n\U0001f4ca <b>Архетипы:</b>\n{arch_lines}"

    retention = round(b["active"] / b["total"] * 100) if b["total"] > 0 else 0

    await update.message.reply_text(
        f"\U0001f4c8 <b>Статистика бота</b>\n\n"
        f"<b>Аудитория:</b>\n"
        f"  Всего зашли: <b>{b['total']}</b>\n"
        f"  Активных: <b>{b['active']}</b>\n"
        f"  Заблокировали: <b>{b['blocked']}</b>\n"
        f"  Retention: <b>{retention}%</b>\n\n"
        f"<b>Прирост:</b>\n"
        f"  За сегодня: <b>+{b['new_today']}</b>\n"
        f"  За 7 дней: <b>+{b['new_week']}</b>\n\n"
        f"<b>Конверсии:</b>\n"
        f"  Прошли квиз + email: <b>{s['users']}</b>\n"
        f"  Заявки: <b>{s['leads']}</b>\n\n"
        f"<b>Контент:</b>\n"
        f"  Постов всего: <b>{s['posts_total']}</b>\n"
        f"  Отправлено: <b>{s['posts_sent']}</b>\n"
        f"  Запланировано: <b>{s['posts_scheduled']}</b>"
        f"{arch_text}",
        parse_mode="HTML",
    )


async def cmd_snapshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    label = " ".join(context.args) if context.args else now_msk().strftime("%d.%m.%Y %H:%M")
    b = get_bot_users_stats()
    s = get_stats()
    snap_id = save_snapshot(label, b["total"], b["active"], s["users"], s["leads"])
    await update.message.reply_text(
        f"\U0001f4f8 <b>Снимок #{snap_id} сохранён</b>\n"
        f"Метка: <i>{label}</i>\n\n"
        f"Всего: <b>{b['total']}</b>\n"
        f"Активных: <b>{b['active']}</b>\n"
        f"Прошли квиз: <b>{s['users']}</b>\n"
        f"Заявки: <b>{s['leads']}</b>\n\n"
        f"Используйте /compare для сравнения.",
        parse_mode="HTML",
    )


async def cmd_compare(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    snap = get_last_snapshot()
    if not snap:
        await update.message.reply_text("Нет сохранённых снимков. Сначала сделайте /snapshot")
        return
    b = get_bot_users_stats()
    s = get_stats()

    def _diff(current: int, old: int) -> str:
        d = current - old
        return f"+{d}" if d >= 0 else str(d)

    await update.message.reply_text(
        f"\U0001f4ca <b>Сравнение с последним снимком</b>\n"
        f"Метка: <i>{snap['label']}</i>\n"
        f"Дата снимка: {snap['created_at'][:16]}\n\n"
        f"Всего в боте: {snap['total_users']} \u2192 <b>{b['total']}</b> (<b>{_diff(b['total'], snap['total_users'])}</b>)\n"
        f"Активных: {snap['active_users']} \u2192 <b>{b['active']}</b> (<b>{_diff(b['active'], snap['active_users'])}</b>)\n"
        f"Прошли квиз: {snap['quiz_completed']} \u2192 <b>{s['users']}</b> (<b>{_diff(s['users'], snap['quiz_completed'])}</b>)\n"
        f"Заявки: {snap['leads_count']} \u2192 <b>{s['leads']}</b> (<b>{_diff(s['leads'], snap['leads_count'])}</b>)",
        parse_mode="HTML",
    )


async def cmd_funnel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    f = get_funnel_stats()

    def _pct(part: int, whole: int) -> str:
        return f"{round(part / whole * 100)}%" if whole > 0 else "\u2014"

    await update.message.reply_text(
        f"\U0001f53d <b>Воронка конверсии</b>\n\n"
        f"1. Зашли в бота: <b>{f['started_bot']}</b> (100%)\n"
        f"2. Начали квиз: <b>{f['started_quiz']}</b> ({_pct(f['started_quiz'], f['started_bot'])})\n"
        f"3. Прошли квиз: <b>{f['completed_quiz']}</b> ({_pct(f['completed_quiz'], f['started_bot'])})\n"
        f"4. Оставили email: <b>{f['left_email']}</b> ({_pct(f['left_email'], f['started_bot'])})\n"
        f"5. Оставили заявку: <b>{f['leads']}</b> ({_pct(f['leads'], f['started_bot'])})",
        parse_mode="HTML",
    )


async def cmd_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    sources = get_sources_stats()
    if not sources:
        await update.message.reply_text("Пока нет данных об источниках.")
        return
    lines = ["\U0001f517 <b>Источники трафика</b>\n"]
    for src, cnt in sources:
        lines.append(f"  {src}: <b>{cnt}</b>")
    lines.append(
        f"\n\U0001f4a1 <i>Для UTM-трекинга используйте ссылки вида:\n"
        f"https://t.me/ИМЯ_БОТА?start=ИСТОЧНИК</i>"
    )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_check_active(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("\U0001f50d Проверяю активных подписчиков\u2026 Это может занять некоторое время.")

    with _connect() as conn:
        rows = conn.execute("SELECT telegram_id FROM bot_users WHERE is_blocked=0").fetchall()

    active = 0
    newly_blocked = 0
    for (tid,) in rows:
        try:
            await context.bot.send_chat_action(chat_id=tid, action="typing")
            active += 1
        except Exception as e:
            err = str(e).lower()
            if "forbidden" in err or "blocked" in err or "deactivated" in err or "not found" in err:
                mark_user_blocked(tid)
                newly_blocked += 1
            else:
                active += 1
        await asyncio.sleep(0.05)

    await update.message.reply_text(
        f"\u2705 <b>Проверка завершена</b>\n\n"
        f"Активных: <b>{active}</b>\n"
        f"Заблокировали: <b>{newly_blocked}</b>\n"
        f"Всего проверено: <b>{active + newly_blocked}</b>",
        parse_mode="HTML",
    )


async def cmd_set_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    _clear_admin_state(context)
    context.user_data["admin_state"] = "awaiting_start_content"
    await update.message.reply_text(
        "\U0001f3e0 <b>Редактирование стартового сообщения</b>\n\n"
        "Отправьте новый текст приветствия.\n"
        "Можно с фото, форматированием, эмодзи.\n\n"
        "Это сообщение увидит каждый пользователь при нажатии /start.\n"
        "Кнопка «Начать тест» добавится автоматически.\n"
        "Доп. кнопки: /set_start_button (одна) или /set_start_buttons (несколько).\n\n"
        "/cancel — отменить", parse_mode="HTML",
    )


async def cmd_preview_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    start_text = get_setting("start_message", DEFAULT_START_MESSAGE)
    start_photo = get_setting("start_photo", "")
    markup = _start_keyboard()

    await update.message.reply_text("\U0001f441 <b>Текущее стартовое сообщение:</b>", parse_mode="HTML")
    if start_photo:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id, photo=start_photo,
            caption=start_text, reply_markup=markup, parse_mode="HTML",
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=start_text,
            reply_markup=markup, parse_mode="HTML",
        )


async def cmd_reset_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    set_setting("start_message", DEFAULT_START_MESSAGE)
    set_setting("start_photo", "")
    set_setting("start_inline_buttons", "[]")
    set_setting("start_button_text", "")
    set_setting("start_button_url", "")
    await update.message.reply_text(
        "\u2705 Стартовое сообщение сброшено на стандартное.\n/preview_start — посмотреть")


async def cmd_toggle_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    current = get_setting("quiz_enabled", "1")
    new_value = "0" if current == "1" else "1"
    set_setting("quiz_enabled", new_value)
    if new_value == "1":
        await update.message.reply_text(
            "\u2705 <b>Квиз включён.</b>\n\n"
            "Пользователи после /start будут проходить тест.", parse_mode="HTML")
    else:
        await update.message.reply_text(
            "\u26d4 <b>Квиз отключён.</b>\n\n"
            "Пользователи после /start сразу получат подборку AI-инструментов.\n"
            "Кнопка «Пройти тест» останется доступна.", parse_mode="HTML")


async def cmd_set_start_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    raw = " ".join(context.args).strip()
    if not raw or "|" not in raw:
        await update.message.reply_text(
            "Использование: /set_start_button <code>Текст | URL</code>\n"
            "Пример: /set_start_button Скачать гайд | https://disk.yandex.ru/...",
            parse_mode="HTML",
        )
        return
    text, url = [x.strip() for x in raw.split("|", 1)]
    if not text or not url.startswith("http"):
        await update.message.reply_text("Укажите корректные текст и URL (http/https).")
        return
    set_setting("start_button_text", text)
    set_setting("start_button_url", url)
    await update.message.reply_text("✅ Кнопка-ссылка для стартового сообщения сохранена.")


async def cmd_set_start_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    _clear_admin_state(context)
    context.user_data["admin_state"] = "awaiting_start_inline_buttons"
    await update.message.reply_text(
        "<b>Кнопки-ссылки под «Начать тест»</b>\n\n"
        "Отправьте <b>одним сообщением</b>, каждая строка:\n"
        "<code>Текст | https://...</code>\n\n"
        "Несколько ссылок — несколько строк.\n"
        "<code>-</code> — убрать все доп. кнопки (только «Начать тест»).\n\n"
        "/cancel — отменить",
        parse_mode="HTML",
    )


async def cmd_set_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /set_button <code>ID Текст | URL</code>",
            parse_mode="HTML",
        )
        return
    try:
        post_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом.")
        return
    payload = " ".join(context.args[1:]).strip()
    if "|" not in payload:
        await update.message.reply_text("Формат: /set_button ID Текст | URL")
        return
    btn_text, btn_url = [x.strip() for x in payload.split("|", 1)]
    if not btn_text or not btn_url.startswith("http"):
        await update.message.reply_text("Укажите корректные текст и URL (http/https).")
        return
    if not update_post_button(post_id, btn_text, btn_url):
        await update.message.reply_text(f"Пост #{post_id} не найден.")
        return
    await update.message.reply_text(f"✅ Кнопка-ссылка сохранена для поста #{post_id}.")


async def cmd_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /target <code>ID TAG|all</code>\n"
            "Пример: /target 12 webinar_27_optin",
            parse_mode="HTML",
        )
        return
    try:
        post_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом.")
        return
    tag = context.args[1].strip().lower()
    include_tag = None if tag == "all" else tag
    if not update_post_target(post_id, include_tag):
        await update.message.reply_text(f"Пост #{post_id} не найден.")
        return
    if include_tag:
        await update.message.reply_text(f"✅ Для поста #{post_id} установлен сегмент: <b>{include_tag}</b>", parse_mode="HTML")
    else:
        await update.message.reply_text(f"✅ Для поста #{post_id} снято ограничение по сегменту (all).")


async def cmd_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    stats = get_all_tags_stats()
    if not stats:
        await update.message.reply_text("Пока нет меток.")
        return
    lines = ["🏷 <b>Метки пользователей</b>\n"]
    for tag, cnt in stats:
        lines.append(f"{tag}: <b>{cnt}</b>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_new_webinar_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text(
            "Использование: /new_webinar_flow <code>webinar_x</code>\n"
            "Пример: /new_webinar_flow webinar_27",
            parse_mode="HTML",
        )
        return
    slug = context.args[0].strip().lower()
    if not slug.startswith("webinar_"):
        await update.message.reply_text("Slug должен начинаться с webinar_. Пример: webinar_27")
        return
    _clear_admin_state(context)
    context.user_data["admin_state"] = "awaiting_webinar_flow_start"
    context.user_data["admin_draft"] = {"slug": slug}
    await update.message.reply_text(
        f"🎬 <b>Настройка webinar flow: {slug}</b>\n\n"
        "<b>Шаг 1/4:</b> стартовое сообщение (текст или фото с подписью).\n"
        "Дальше настроим интерактивные кнопки, как у постов.",
        parse_mode="HTML",
    )


# ══════════════════════════════ АДМИН ВВОД ══════════════════════════════


def _extract_content(message) -> tuple[str | None, str | None]:
    """Извлекает text_html и photo_id из сообщения."""
    photo_id = None
    text_html = None
    if message.photo:
        photo_id = message.photo[-1].file_id
        text_html = message.caption_html
    elif message.text:
        text_html = message.text_html
    return text_html, photo_id


async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("admin_state")
    draft = context.user_data.get("admin_draft", {})
    msg = update.message
    text_html, photo_id = _extract_content(msg)

    # ── Стартовое сообщение ──
    if state == "awaiting_start_content":
        set_setting("start_message", text_html or "")
        set_setting("start_photo", photo_id or "")
        _clear_admin_state(context)
        await msg.reply_text(
            "\u2705 Стартовое сообщение обновлено!\n\n"
            "/preview_start — посмотреть как выглядит\n"
            "/reset_start — сбросить на стандартное", parse_mode="HTML")
        return

    # ── Несколько кнопок-ссылок под стартом ──
    if state == "awaiting_start_inline_buttons":
        if not msg.text:
            await msg.reply_text("Пришлите текстом строки в формате Текст | URL.")
            return
        js, err = parse_url_buttons_lines(msg.text.strip())
        if err or js is None:
            await msg.reply_text(err or "Ошибка.")
            return
        set_setting("start_inline_buttons", js)
        _clear_admin_state(context)
        await msg.reply_text("✅ Интерактивные кнопки под старт сохранены.\n/preview_start — проверить.")
        return

    # ── Webinar flow: шаг 1 — стартовое сообщение ──
    if state == "awaiting_webinar_flow_start":
        draft["start_text"] = text_html or ""
        draft["start_photo"] = photo_id or ""
        context.user_data["admin_state"] = "awaiting_webinar_flow_confirm"
        await msg.reply_text(
            "✅ Стартовое сообщение сохранено.\n\n"
            "<b>Шаг 2/4:</b> сообщение после нажатия «Записаться» (подтверждение).",
            parse_mode="HTML",
        )
        return

    # ── Webinar flow: шаг 2 — подтверждение ──
    if state == "awaiting_webinar_flow_confirm":
        draft["confirm_text"] = text_html or "✅ Вы успешно записаны на вебинар."
        context.user_data["admin_state"] = "awaiting_webinar_flow_start_buttons"
        await msg.reply_text(
            "<b>Шаг 3/4: интерактивные кнопки</b> под стартовым сообщением.\n"
            "Каждая строка — одна кнопка (порядок = как сверху вниз):\n\n"
            "<b>Ссылка:</b> <code>Текст | https://...</code>\n"
            "<b>Запись на вебинар:</b> строка <b>без</b> « | » — например "
            "<code>Записаться на вебинар</code>\n\n"
            "Можно несколько ссылок + одна строка записи. Если строки записи нет — "
            "будет кнопка <code>✅ Записаться</code>.\n\n"
            "Только ссылки — одна строка на кнопку. Или <code>-</code> = только «✅ Записаться».",
            parse_mode="HTML",
        )
        return

    # ── Webinar flow: шаг 3 — кнопки старта ──
    if state == "awaiting_webinar_flow_start_buttons":
        if not msg.text or msg.photo:
            await msg.reply_text(
                "Пришлите текстом список кнопок (см. инструкцию выше).\nФото здесь не поддерживается.")
            return
        raw = msg.text.strip()
        buttons, err = parse_webinar_start_buttons(raw)
        if err or buttons is None:
            await msg.reply_text(err or "Ошибка разбора кнопок.")
            return
        draft["start_buttons"] = buttons
        context.user_data["admin_state"] = "awaiting_webinar_flow_confirm_cta"
        await msg.reply_text(
            "<b>Шаг 4/4:</b> опциональная кнопка-ссылка <b>под текстом подтверждения</b> "
            "(после записи).\n"
            "<code>Текст | URL</code> или <code>-</code>, если не нужна.",
            parse_mode="HTML",
        )
        return

    # ── Webinar flow: шаг 4 — CTA после подтверждения ──
    if state == "awaiting_webinar_flow_confirm_cta":
        raw = (msg.text or "").strip()
        cta_text = ""
        cta_url = ""
        if raw != "-":
            if "|" not in raw:
                await msg.reply_text("Формат: Текст | URL (или '-')")
                return
            cta_text, cta_url = [x.strip() for x in raw.split("|", 1)]
            if not cta_text or not cta_url.startswith("http"):
                await msg.reply_text("Некорректные данные кнопки. URL должен начинаться с http.")
                return

        slug = draft.get("slug", "")
        btns = draft.get("start_buttons") or [{"type": "optin", "text": "✅ Записаться"}]
        set_webinar_flow(
            slug=slug,
            title=slug,
            start_text=draft.get("start_text", ""),
            start_photo=draft.get("start_photo", ""),
            confirm_text=draft.get("confirm_text", "✅ Вы успешно записаны на вебинар."),
            cta_text=cta_text,
            cta_url=cta_url,
            start_buttons_json=json.dumps(btns, ensure_ascii=False),
        )
        _clear_admin_state(context)
        await msg.reply_text(
            f"✅ Webinar flow <b>{slug}</b> сохранён.\n\n"
            f"Deep-link для рекламы:\n<code>https://t.me/ИМЯ_БОТА?start={slug}</code>",
            parse_mode="HTML",
        )
        return

    # ── Обычный пост: получаем контент → сохраняем ──
    if state == "awaiting_post_content":
        pid = create_post("post", text_html=text_html, photo_id=photo_id,
                          created_by=update.effective_user.id)
        _clear_admin_state(context)
        await msg.reply_text(
            f"\u2705 Пост <b>#{pid}</b> создан!\n\n"
            f"Что дальше:\n"
            f"/preview {pid} — посмотреть\n"
            f"/schedule {pid} 2026-03-17 10:00 — запланировать (МСК)\n"
            f"/send_now {pid} — отправить сейчас", parse_mode="HTML")
        return

    # ── Кейс: шаг 1 — контент ──
    if state == "awaiting_case_content":
        draft["text_html"] = text_html
        draft["photo_id"] = photo_id
        context.user_data["admin_state"] = "awaiting_case_options"
        await msg.reply_text(
            "\u2705 Описание кейса сохранено!\n\n"
            "<b>Шаг 2 из 3:</b> Отправьте варианты ответов.\n"
            "Каждый вариант — <b>с новой строки</b>.\n\n"
            "Пример:\n<i>Добавить AI-чат в продукт\n"
            "Автоматизировать обработку заявок\n"
            "Внедрить рекомендательную систему</i>", parse_mode="HTML")
        return

    # ── Кейс: шаг 2 — варианты ──
    if state == "awaiting_case_options":
        raw = msg.text or ""
        options = [line.strip() for line in raw.split("\n") if line.strip()]
        if len(options) < 2:
            await msg.reply_text("Нужно минимум 2 варианта (каждый с новой строки). Попробуйте ещё раз.")
            return
        draft["case_options"] = options
        context.user_data["admin_state"] = "awaiting_case_answer"
        await msg.reply_text(
            f"\u2705 Варианты сохранены ({len(options)} шт.)!\n\n"
            "<b>Шаг 3 из 3:</b> Отправьте разбор от эксперта.\n"
            "Этот текст пользователь увидит после выбора ответа.",
            parse_mode="HTML")
        return

    # ── Кейс: шаг 3 — ответ эксперта ──
    if state == "awaiting_case_answer":
        draft["case_answer_html"] = text_html
        pid = create_post("case", text_html=draft.get("text_html"), photo_id=draft.get("photo_id"),
                          case_options=draft.get("case_options"), case_answer_html=text_html,
                          created_by=update.effective_user.id)
        _clear_admin_state(context)
        await msg.reply_text(
            f"\u2705 Кейс <b>#{pid}</b> создан!\n\n"
            f"/preview {pid} — посмотреть\n"
            f"/schedule {pid} 2026-03-17 10:00 — запланировать\n"
            f"/send_now {pid} — отправить сейчас", parse_mode="HTML")
        return

    # ── Продажный пост: контент → сохраняем ──
    if state == "awaiting_sale_content":
        pid = create_post("sale", text_html=text_html, photo_id=photo_id,
                          created_by=update.effective_user.id)
        _clear_admin_state(context)
        await msg.reply_text(
            f"\u2705 Пост с формой <b>#{pid}</b> создан!\n"
            f"К нему автоматически добавится кнопка «Оставить заявку».\n\n"
            f"/preview {pid} — посмотреть\n"
            f"/schedule {pid} 2026-03-17 10:00 — запланировать\n"
            f"/send_now {pid} — отправить сейчас", parse_mode="HTML")
        return

    # ── Вебинар: шаг 1 — контент ──
    if state == "awaiting_webinar_content":
        draft["text_html"] = text_html
        draft["photo_id"] = photo_id
        context.user_data["admin_state"] = "awaiting_webinar_slug"
        await msg.reply_text(
            "\u2705 Текст анонса сохранён!\n\n"
            "<b>Шаг 2 из 3:</b> Отправьте slug вебинара (например <code>webinar_27</code>).\n"
            "Если не нужно ставить метки/подписку, отправьте <code>-</code>.",
            parse_mode="HTML")
        return

    # ── Вебинар: шаг 2 — slug ──
    if state == "awaiting_webinar_slug":
        slug = (msg.text or "").strip().lower()
        if slug != "-" and not slug.startswith("webinar_"):
            await msg.reply_text("Slug должен начинаться с webinar_ или '-'")
            return
        draft["webinar_slug"] = "" if slug == "-" else slug
        context.user_data["admin_state"] = "awaiting_webinar_link"
        await msg.reply_text(
            "<b>Шаг 3 из 3:</b> Отправьте ссылку на регистрацию.\n"
            "Пример: https://gigaschool.ru/webinar", parse_mode="HTML")
        return

    # ── Вебинар: шаг 3 — ссылка ──
    if state == "awaiting_webinar_link":
        link = (msg.text or "").strip()
        if not link.startswith("http"):
            await msg.reply_text("Это не похоже на ссылку. Отправьте URL, начинающийся с http")
            return
        pid = create_post("webinar", text_html=draft.get("text_html"), photo_id=draft.get("photo_id"),
                          webinar_link=link, created_by=update.effective_user.id,
                          webinar_slug=draft.get("webinar_slug", ""))
        _clear_admin_state(context)
        await msg.reply_text(
            f"\u2705 Анонс вебинара <b>#{pid}</b> создан!\n\n"
            f"/preview {pid} — посмотреть\n"
            f"/schedule {pid} 2026-03-17 10:00 — запланировать\n"
            f"/send_now {pid} — отправить сейчас", parse_mode="HTML")
        return


# ══════════════════════════════ РАССЫЛКА ══════════════════════════════


async def broadcast_post(post: dict, context: ContextTypes.DEFAULT_TYPE) -> tuple[int, int]:
    include_tag = (post.get("include_tag") or "").strip().lower()
    subscribers = get_tag_user_ids(include_tag) if include_tag else get_all_subscriber_ids()
    sent = 0
    failed = 0
    for tid in subscribers:
        if is_broadcast_sent(post["id"], tid):
            continue
        try:
            await _send_post_preview(tid, post, context)
            mark_broadcast_sent(post["id"], tid)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"Failed to send post #{post['id']} to {tid}: {e}")
            err = str(e).lower()
            if "forbidden" in err or "blocked" in err or "deactivated" in err or "not found" in err:
                mark_user_blocked(tid)
            failed += 1
    return sent, failed


async def check_scheduled_posts(context: ContextTypes.DEFAULT_TYPE) -> None:
    due = get_due_posts()
    for post in due:
        logger.info(f"Broadcasting scheduled post #{post['id']}")
        sent, failed = await broadcast_post(post, context)
        mark_post_sent(post["id"])
        logger.info(f"Post #{post['id']} broadcast done: sent={sent}, failed={failed}")


# ══════════════════════════════ ПОЛЬЗОВАТЕЛЬСКИЕ ИНТЕРАКЦИИ ══════════════════════════════


FORM_STEPS = [
    ("name", "Как вас зовут?"),
    ("phone", "Номер телефона:"),
    ("email_lead", "Email:"),
    ("tg_nick", "Ник в Telegram (например @username):"),
]


async def handle_form_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    step = context.user_data.get("form_step", 0)
    form = context.user_data.get("form_data", {})
    text = update.message.text.strip()

    field = FORM_STEPS[step][0]
    form[field] = text
    context.user_data["form_data"] = form
    step += 1
    context.user_data["form_step"] = step

    if step < len(FORM_STEPS):
        await update.message.reply_text(FORM_STEPS[step][1])
    else:
        # Форма заполнена
        user = update.effective_user
        save_lead(
            telegram_id=user.id,
            username=user.username or "",
            name=form.get("name", ""),
            phone=form.get("phone", ""),
            email=form.get("email_lead", ""),
            tg_nick=form.get("tg_nick", ""),
            source=context.user_data.get("form_source", "unknown"),
        )
        context.user_data.pop("form_state", None)
        context.user_data.pop("form_step", None)
        context.user_data.pop("form_data", None)
        context.user_data.pop("form_source", None)
        await update.message.reply_text(
            "\u2705 Спасибо! Ваша заявка принята.\nМы свяжемся с вами в ближайшее время.")


# ══════════════════════════════ CALLBACK РОУТЕР ══════════════════════════════


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id

    # ── Квиз ──
    if data in ("start_quiz", "restart_quiz"):
        context.user_data["score"] = 0
        context.user_data["question_idx"] = 0
        context.user_data["awaiting_email"] = False
        context.user_data.pop("form_state", None)
        mark_quiz_started(query.from_user.id)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await send_question(chat_id, context)
        return

    if data.startswith("answer_"):
        letter = data.replace("answer_", "")
        points = SCORE_MAP.get(letter, 0)
        context.user_data["score"] = context.user_data.get("score", 0) + points
        idx = context.user_data.get("question_idx", 0)
        context.user_data["question_idx"] = idx + 1
        q = QUESTIONS[idx]
        opts = "\n".join(
            f"\n{'\u27a1\ufe0f ' if l == letter else ''}<b>{l})</b> {t}" for l, t in q["options"]
        )
        try:
            await query.edit_message_text(
                text=f"{q['text']}\n{opts}\n\n<i>Ваш ответ: {letter}</i>", parse_mode="HTML")
        except Exception:
            pass
        await send_question(chat_id, context)
        return

    # ── Кейс — ответ пользователя ──
    if data.startswith("case_"):
        parts = data.split("_")
        if len(parts) >= 3:
            post_id = int(parts[1])
            option_idx = int(parts[2])
            post = get_post(post_id)
            if post and post.get("case_options"):
                chosen = post["case_options"][option_idx] if option_idx < len(post["case_options"]) else "?"
                answer = post.get("case_answer_html") or "Разбор скоро будет добавлен."
                try:
                    await query.edit_message_reply_markup(reply_markup=None)
                except Exception:
                    pass
                await context.bot.send_message(
                    chat_id=chat_id, parse_mode="HTML",
                    text=f"<b>Ваш ответ:</b> {chosen}\n\n─────────────────────\n\n{answer}")
        return

    # ── Форма заявки ──
    if data.startswith("form_"):
        post_id = data.replace("form_", "")
        context.user_data["form_state"] = True
        context.user_data["form_step"] = 0
        context.user_data["form_data"] = {}
        context.user_data["form_source"] = f"sale_post_{post_id}"
        await context.bot.send_message(chat_id=chat_id, text=FORM_STEPS[0][1])
        return

    # ── Запись на вебинар через кнопку ──
    if data.startswith("wb_join_"):
        slug = data.replace("wb_join_", "").strip().lower()
        if not slug:
            return
        tag = f"{slug}_optin"
        add_user_tag(query.from_user.id, tag)

        flow = get_webinar_flow(slug)
        confirm_text = "✅ Вы успешно записаны на вебинар. Мы пришлем напоминание перед началом."
        buttons = []
        if flow:
            confirm_text = flow.get("confirm_text") or confirm_text
            if flow.get("cta_text") and flow.get("cta_url"):
                buttons.append([InlineKeyboardButton(flow["cta_text"], url=flow["cta_url"])])
        await context.bot.send_message(
            chat_id=chat_id,
            text=confirm_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
        )
        return


# ══════════════════════════════ РОУТЕР СООБЩЕНИЙ ══════════════════════════════


async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # 1. Админ создаёт контент
    if is_admin(user_id) and context.user_data.get("admin_state"):
        await handle_admin_input(update, context)
        return

    # 2. Пользователь заполняет форму заявки
    if context.user_data.get("form_state"):
        await handle_form_input(update, context)
        return

    # 3. Пользователь вводит email после квиза
    if context.user_data.get("awaiting_email"):
        email = (update.message.text or "").strip()
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
            await update.message.reply_text("Похоже, это не email. Попробуй ещё раз.\nПример: ivan@mail.ru")
            return
        context.user_data["awaiting_email"] = False
        chat_id = update.message.chat_id
        score = context.user_data.get("score", 0)
        result = get_result(score)
        user = update.effective_user
        save_user(user.id, user.username or "", email, score, result["title"])
        email_sent = await asyncio.to_thread(send_email, email, score, result)
        await show_quiz_result(chat_id, context, email_sent)
        return


# ══════════════════════════════ ЗАПУСК ══════════════════════════════


async def setup_bot_commands(app: Application) -> None:
    """Устанавливает меню команд: общее для всех + расширенное для админов."""
    # Команды для обычных пользователей
    await app.bot.set_my_commands([
        BotCommand("start", "Начать / перезапустить бота"),
    ])

    # Расширенное меню для каждого админа
    admin_commands = [
        BotCommand("start", "Начать / перезапустить бота"),
        BotCommand("help", "Все команды администратора"),
        BotCommand("set_start", "Изменить стартовое сообщение"),
        BotCommand("set_start_button", "Одна кнопка-ссылка в старте"),
        BotCommand("set_start_buttons", "Несколько кнопок в старте"),
        BotCommand("preview_start", "Предпросмотр стартового сообщения"),
        BotCommand("reset_start", "Сбросить стартовое сообщение"),
        BotCommand("toggle_quiz", "Включить/выключить квиз"),
        BotCommand("newpost", "Создать обычный пост"),
        BotCommand("newcase", "Создать интерактив-кейс"),
        BotCommand("newsale", "Создать пост с формой"),
        BotCommand("newwebinar", "Создать анонс вебинара"),
        BotCommand("cancel", "Отменить текущее действие"),
        BotCommand("posts", "Список всех постов"),
        BotCommand("preview", "Предпросмотр поста (ID)"),
        BotCommand("schedule", "Запланировать пост (ID дата время)"),
        BotCommand("send_now", "Отправить пост сейчас (ID)"),
        BotCommand("set_button", "Кнопка-ссылка для поста"),
        BotCommand("target", "Сегмент поста по метке"),
        BotCommand("new_webinar_flow", "Flow вебинара для deep-link"),
        BotCommand("tags", "Статистика меток"),
        BotCommand("delete_post", "Удалить пост (ID)"),
        BotCommand("stats", "Статистика бота"),
        BotCommand("funnel", "Воронка конверсии"),
        BotCommand("sources", "Источники трафика"),
        BotCommand("snapshot", "Снимок аудитории"),
        BotCommand("compare", "Сравнить со снимком"),
        BotCommand("check_active", "Проверить активных"),
        BotCommand("export", "Выгрузить пользователей CSV"),
        BotCommand("export_leads", "Выгрузить заявки CSV"),
    ]
    for admin_id in ADMIN_IDS:
        try:
            await app.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:
            logger.warning(f"Could not set admin menu for {admin_id}: {e}")

    logger.info("Bot commands menu set")


def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("Error: Set BOT_TOKEN in .env file")
        return

    init_db()
    migrated = migrate_existing_users()
    if migrated:
        logger.info(f"Migrated {migrated} existing users to bot_users table")

    app = Application.builder().token(BOT_TOKEN).post_init(setup_bot_commands).build()

    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("set_start", cmd_set_start))
    app.add_handler(CommandHandler("set_start_button", cmd_set_start_button))
    app.add_handler(CommandHandler("set_start_buttons", cmd_set_start_buttons))
    app.add_handler(CommandHandler("preview_start", cmd_preview_start))
    app.add_handler(CommandHandler("reset_start", cmd_reset_start))
    app.add_handler(CommandHandler("toggle_quiz", cmd_toggle_quiz))
    app.add_handler(CommandHandler("newpost", cmd_newpost))
    app.add_handler(CommandHandler("newcase", cmd_newcase))
    app.add_handler(CommandHandler("newsale", cmd_newsale))
    app.add_handler(CommandHandler("newwebinar", cmd_newwebinar))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("posts", cmd_posts))
    app.add_handler(CommandHandler("preview", cmd_preview))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("send_now", cmd_send_now))
    app.add_handler(CommandHandler("set_button", cmd_set_button))
    app.add_handler(CommandHandler("target", cmd_target))
    app.add_handler(CommandHandler("new_webinar_flow", cmd_new_webinar_flow))
    app.add_handler(CommandHandler("tags", cmd_tags))
    app.add_handler(CommandHandler("delete_post", cmd_delete_post))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("export_leads", cmd_export_leads))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("snapshot", cmd_snapshot))
    app.add_handler(CommandHandler("compare", cmd_compare))
    app.add_handler(CommandHandler("funnel", cmd_funnel))
    app.add_handler(CommandHandler("sources", cmd_sources))
    app.add_handler(CommandHandler("check_active", cmd_check_active))

    # Кнопки
    app.add_handler(CallbackQueryHandler(button_handler))

    # Текст и фото
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, message_router))

    # Планировщик рассылки — каждые 5 минут
    app.job_queue.run_repeating(check_scheduled_posts, interval=300, first=10)

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    main()
