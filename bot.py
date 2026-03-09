import os
import re
import csv
import io
import asyncio
import logging
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# ─────────────────────────── Конфиг ───────────────────────────

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip()}
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.db")

# ─────────────────────────── Вопросы ───────────────────────────

QUESTIONS = [
    {
        "text": (
            "💼 <b>Вопрос 1 — «Задача, на которую уходит полдня»</b>\n\n"
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
            "🤝 <b>Вопрос 2 — «Тебя просят предложить, как внедрить ИИ»</b>\n\n"
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
            "🔄 <b>Вопрос 3 — «Рутина, которая повторяется каждую неделю»</b>\n\n"
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
            "💡 <b>Вопрос 4 — «Идея, которая требует реализации»</b>\n\n"
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
            "📊 <b>Вопрос 5 — «Нужно обосновать решение данными»</b>\n\n"
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
            "🚀 <b>Вопрос 6 — «Рынок меняется быстрее, чем ты успеваешь»</b>\n\n"
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

# ─────────────────────────── Результаты ───────────────────────────

SCORE_MAP = {"A": 1, "B": 2, "C": 3, "D": 4}

RESULTS = [
    {
        "range": (6, 10),
        "title": "Наблюдатель",
        "emoji": "🔍",
        "text": (
            "ИИ уже рядом с тобой.\n"
            "Но пока почти не влияет на твою работу.\n\n"
            "Скорее всего:\n"
            "— многие задачи ты всё ещё делаешь вручную\n"
            "— используешь ИИ редко или эпизодически\n"
            "— не очень понятно, где именно он может помочь\n\n"
            "При этом сейчас происходит интересная вещь.\n"
            "Люди, которые встроили ИИ в рабочие процессы,\n"
            "часто экономят 5–15 часов в неделю.\n"
            "Не потому что они гении.\n"
            "А потому что знают где и как использовать инструменты.\n\n"
            "Хорошая новость:\n"
            "порог входа в ИИ намного ниже, чем кажется."
        ),
    },
    {
        "range": (11, 15),
        "title": "Экспериментатор",
        "emoji": "🧪",
        "text": (
            "ИИ у тебя уже открыт в соседней вкладке.\n"
            "Иногда он помогает.\n"
            "Иногда выдаёт странный результат.\n\n"
            "Скорее всего:\n"
            "— ты пробуешь разные инструменты\n"
            "— но не всегда понимаешь, как правильно ставить задачу\n"
            "— знания пока фрагментарные\n\n"
            "Это самый частый уровень.\n"
            "Люди здесь уже чувствуют потенциал ИИ,\n"
            "но пока не могут сделать его надёжным рабочим инструментом.\n\n"
            "Как только появляется система —\n"
            "эффективность резко растёт."
        ),
    },
    {
        "range": (16, 20),
        "title": "Практик",
        "emoji": "⚡",
        "text": (
            "ИИ уже стал частью твоей работы.\n\n"
            "Ты:\n"
            "— используешь его для анализа\n"
            "— ускоряешь подготовку материалов\n"
            "— автоматизируешь часть задач\n\n"
            "Но чаще всего это личная продуктивность.\n\n"
            "Следующий уровень —\n"
            "когда ИИ начинает работать не только для тебя, "
            "но и внутри процессов:\n"
            "— в продукте\n"
            "— в команде\n"
            "— в операциях\n\n"
            "Там начинается совсем другой эффект."
        ),
    },
    {
        "range": (21, 24),
        "title": "AI-Ready",
        "emoji": "🧠",
        "text": (
            "Ты уже понимаешь, как работать с ИИ системно.\n\n"
            "Скорее всего ты:\n"
            "— быстро тестируешь идеи\n"
            "— используешь несколько инструментов\n"
            "— умеешь получать нужный результат от моделей\n\n"
            "Это уровень, на котором люди начинают:\n"
            "— проектировать AI-решения\n"
            "— автоматизировать процессы\n"
            "— собирать рабочие прототипы\n\n"
            "Именно такие специалисты сейчас становятся\n"
            "одними из самых востребованных на рынке."
        ),
    },
]


def get_result(score: int) -> dict:
    for r in RESULTS:
        lo, hi = r["range"]
        if lo <= score <= hi:
            return r
    return RESULTS[-1]


# ─────────────────────────── База данных ───────────────────────────


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id   INTEGER NOT NULL,
                username      TEXT,
                email         TEXT,
                score         INTEGER,
                archetype     TEXT,
                created_at    TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_user(telegram_id: int, username: str, email: str, score: int, archetype: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO users (telegram_id, username, email, score, archetype, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (telegram_id, username, email, score, archetype, datetime.now().isoformat()),
        )
        conn.commit()


def export_users_csv() -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["telegram_id", "username", "email", "score", "archetype", "created_at"])
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT telegram_id, username, email, score, archetype, created_at FROM users ORDER BY id").fetchall()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


# ─────────────────────────── Email ───────────────────────────


def build_email_html(archetype_emoji: str, archetype_title: str, archetype_text: str, score: int) -> str:
    archetype_html = archetype_text.replace("\n", "<br>")

    tools_html = """
    <tr><td style="padding:20px 30px;">
      <h2 style="color:#1a1a2e;font-size:22px;margin:0 0 20px 0;">10 AI-инструментов</h2>
      <p style="color:#555;font-size:15px;margin:0 0 24px 0;">
        Которые чаще всего используют продакты, аналитики и маркетологи
      </p>

      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;">
          <a href="https://chat.openai.com" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">1. ChatGPT (OpenAI)</a>
          <p style="color:#555;font-size:14px;margin:6px 0 0 0;">Универсальный рабочий инструмент для ежедневных задач: анализ фидбека, генерация гипотез, подготовка PRD и брифов, работа с данными.</p>
        </td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;">
          <a href="https://claude.ai" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">2. Claude</a>
          <p style="color:#555;font-size:14px;margin:6px 0 0 0;">Сильная модель для аналитики и работы с большими документами: разбор исследований, структурирование информации, подготовка аргументов.</p>
        </td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;">
          <a href="https://perplexity.ai" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">3. Perplexity</a>
          <p style="color:#555;font-size:14px;margin:6px 0 0 0;">AI-поисковик нового поколения: быстрый ресёрч рынка и конкурентов, поиск статистики, анализ трендов.</p>
        </td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;">
          <a href="https://gemini.google.com" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">4. Gemini</a>
          <p style="color:#555;font-size:14px;margin:6px 0 0 0;">AI-ассистент от Google: анализ данных в Google Docs и Sheets, аналитические заметки, генерация идей для маркетинга.</p>
        </td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;">
          <a href="https://github.com/features/copilot" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">5. GitHub Copilot</a>
          <p style="color:#555;font-size:14px;margin:6px 0 0 0;">AI-ассистент для кода: быстрая проверка технических гипотез, простые скрипты, понимание кода продукта.</p>
        </td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;">
          <a href="https://replit.com" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">6. Replit AI</a>
          <p style="color:#555;font-size:14px;margin:6px 0 0 0;">Платформа для быстрого создания прототипов: сборка MVP, тестирование AI-идей, создание внутренних инструментов.</p>
        </td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;">
          <a href="https://chat.deepseek.com" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">7. DeepSeek</a>
          <p style="color:#555;font-size:14px;margin:6px 0 0 0;">Модель для аналитики и логических задач: анализ данных, продуктовые гипотезы, структурирование решений.</p>
        </td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;">
          <a href="https://chat.qwen.ai" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">8. Qwen</a>
          <p style="color:#555;font-size:14px;margin:6px 0 0 0;">Модель от Alibaba: обработка больших массивов текста, анализ пользовательских запросов, создание AI-ассистентов.</p>
        </td></tr>
        <tr><td style="padding:14px 0;border-bottom:1px solid #eee;">
          <a href="https://manus.ai" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">9. Manus</a>
          <p style="color:#555;font-size:14px;margin:6px 0 0 0;">AI-агент для сложных многоступенчатых задач: ресёрч, подготовка аналитики, автоматизация, прототипирование без кода.</p>
        </td></tr>
        <tr><td style="padding:14px 0;">
          <a href="https://github.com/open-claude" style="color:#4F46E5;font-weight:bold;font-size:15px;text-decoration:none;">10. OpenClaw</a>
          <p style="color:#555;font-size:14px;margin:6px 0 0 0;">Open-source альтернатива: внутренние AI-ассистенты, работа с корпоративными документами, прототипирование без зависимости от внешних API.</p>
        </td></tr>
      </table>
    </td></tr>
    """

    html = f"""\
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f7;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f7;padding:30px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

  <!-- Header -->
  <tr><td style="background:#1a1a2e;padding:30px 30px;text-align:center;">
    <h1 style="color:#ffffff;font-size:24px;margin:0;font-weight:700;letter-spacing:0.5px;">Gigaschool</h1>
    <p style="color:#a0a0c0;font-size:14px;margin:8px 0 0 0;">Твой AI-профиль</p>
  </td></tr>

  <!-- Archetype -->
  <tr><td style="padding:30px 30px 10px 30px;">
    <div style="background:#f0f0ff;border-radius:10px;padding:24px;text-align:center;">
      <p style="font-size:40px;margin:0 0 8px 0;">{archetype_emoji}</p>
      <h2 style="color:#1a1a2e;font-size:22px;margin:0 0 6px 0;">{archetype_title}</h2>
      <p style="color:#4F46E5;font-size:15px;margin:0;font-weight:600;">{score} из 24 баллов</p>
    </div>
  </td></tr>

  <tr><td style="padding:10px 30px 30px 30px;">
    <p style="color:#333;font-size:15px;line-height:1.7;">{archetype_html}</p>
  </td></tr>

  <!-- Divider -->
  <tr><td style="padding:0 30px;">
    <hr style="border:none;border-top:2px solid #f0f0f0;margin:0;">
  </td></tr>

  <!-- Tools -->
  {tools_html}

  <!-- Footer -->
  <tr><td style="background:#1a1a2e;padding:24px 30px;text-align:center;">
    <p style="color:#a0a0c0;font-size:13px;margin:0;">Gigaschool &copy; {datetime.now().year}</p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""
    return html


def send_email(to_email: str, score: int, result: dict) -> bool:
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        logger.warning("SMTP not configured, skipping email")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Твой AI-профиль: {result['title']} — Gigaschool"
        msg["From"] = f"Gigaschool <{SMTP_EMAIL}>"
        msg["To"] = to_email

        html = build_email_html(result["emoji"], result["title"], result["text"], score)
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.yandex.ru", 465, timeout=15) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())

        logger.info(f"Email sent to {to_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


# ─────────────────────────── Хендлеры бота ───────────────────────────


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    context.user_data["score"] = 0
    context.user_data["question_idx"] = 0

    keyboard = [[InlineKeyboardButton("Начать тест", callback_data="start_quiz")]]
    await update.message.reply_text(
        "Привет!\n\n"
        "Этот тест определит твой <b>AI-профиль</b>.\n\n"
        "6 вопросов — ситуации из реального рабочего дня.\n"
        "Выбери вариант, который ближе всего к тебе.\n"
        "Правильных и неправильных ответов нет.\n\n"
        "Нажми кнопку ниже, чтобы начать",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def send_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    idx = context.user_data.get("question_idx", 0)

    if idx >= len(QUESTIONS):
        await ask_email(chat_id, context)
        return

    q = QUESTIONS[idx]
    options_text = "\n".join(
        f"\n<b>{letter})</b> {text}" for letter, text in q["options"]
    )
    full_text = f"{q['text']}\n{options_text}"

    keyboard = [[
        InlineKeyboardButton("A", callback_data="answer_A"),
        InlineKeyboardButton("B", callback_data="answer_B"),
        InlineKeyboardButton("C", callback_data="answer_C"),
        InlineKeyboardButton("D", callback_data="answer_D"),
    ]]

    await context.bot.send_message(
        chat_id=chat_id,
        text=full_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def ask_email(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_email"] = True

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "<b>Твой результат готов.</b>\n\n"
            "Мы определили твой AI-профиль и подготовили разбор.\n\n"
            "Оставь свою почту, и мы отправим:\n"
            "— разбор твоего архетипа\n"
            "— где именно ты теряешь время в работе\n"
            "— 10 AI-инструментов, некоторые из списка многие ещё даже не пробовали\n\n"
            "Результаты придут в течение минуты\n\n"
            "Напиши свой email"
        ),
        parse_mode="HTML",
    )


async def show_result(chat_id: int, context: ContextTypes.DEFAULT_TYPE, email_sent: bool) -> None:
    score = context.user_data.get("score", 0)
    result = get_result(score)

    email_status = (
        "Письмо с подробным разбором и AI-инструментами отправлено на почту!"
        if email_sent
        else "Не удалось отправить письмо. Проверь адрес и попробуй ещё раз через /start"
    )

    keyboard = [[InlineKeyboardButton("Пройти ещё раз", callback_data="restart_quiz")]]

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"{result['emoji']} <b>Твой AI-профиль: {result['title']}</b>\n\n"
            f"Результат: <b>{score} из 24 баллов</b>\n\n"
            f"─────────────────────\n\n"
            f"{result['text']}\n\n"
            f"─────────────────────\n\n"
            f"📩 {email_status}"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = query.message.chat_id

    if data == "start_quiz":
        context.user_data["score"] = 0
        context.user_data["question_idx"] = 0
        context.user_data["awaiting_email"] = False
        # Убираем кнопку у приветственного сообщения
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await send_question(chat_id, context)
        return

    if data == "restart_quiz":
        context.user_data["score"] = 0
        context.user_data["question_idx"] = 0
        context.user_data["awaiting_email"] = False
        # Убираем кнопку у результата
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

        # Отмечаем выбранный ответ, убираем кнопки
        q = QUESTIONS[idx]
        options_text = "\n".join(
            f"\n{'➡️ ' if l == letter else ''}<b>{l})</b> {t}" for l, t in q["options"]
        )
        try:
            await query.edit_message_text(
                text=f"{q['text']}\n{options_text}\n\n<i>Ваш ответ: {letter}</i>",
                parse_mode="HTML",
            )
        except Exception:
            pass

        await send_question(chat_id, context)
        return


async def email_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get("awaiting_email"):
        return

    email = update.message.text.strip()

    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        await update.message.reply_text(
            "Похоже, это не email-адрес. Попробуй ещё раз.\n"
            "Пример: ivan@mail.ru"
        )
        return

    context.user_data["awaiting_email"] = False
    chat_id = update.message.chat_id

    score = context.user_data.get("score", 0)
    result = get_result(score)

    # Сохраняем в базу
    user = update.effective_user
    username = user.username or ""
    save_user(
        telegram_id=user.id,
        username=username,
        email=email,
        score=score,
        archetype=result["title"],
    )

    # Отправляем письмо (в фоне чтобы не блокировать)
    email_sent = await asyncio.to_thread(send_email, email, score, result)

    # Показываем результат в боте
    await show_result(chat_id, context, email_sent)


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return

    csv_data = export_users_csv()
    buf = io.BytesIO(csv_data.encode("utf-8-sig"))
    buf.name = f"users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    await update.message.reply_document(
        document=buf,
        caption=f"Выгрузка пользователей ({datetime.now().strftime('%d.%m.%Y %H:%M')})",
    )


# ─────────────────────────── Запуск ───────────────────────────


def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("Error: Set BOT_TOKEN in .env file")
        return

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("export", export_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, email_handler))

    print("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    main()
