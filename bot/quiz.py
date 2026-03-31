import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .config import is_admin
from .db import (
    track_bot_user, add_user_tag, get_webinar_flow,
    get_setting, mark_quiz_started, mark_quiz_completed, save_user,
)
from .content import (
    QUESTIONS, SCORE_MAP, get_result,
    AI_TOOLS_TEXT, DEFAULT_START_MESSAGE,
)
from .keyboards import start_keyboard, webinar_flow_start_keyboard
from .email_service import send_email


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    source = context.args[0] if context.args else ""
    track_bot_user(user.id, user.username or "", user.first_name or "", source)

    context.user_data.clear()
    context.user_data["score"] = 0
    context.user_data["question_idx"] = 0

    # Deep-link webinar flow: /start webinar_x
    if source.startswith("webinar_"):
        slug_lc = source.strip().lower()
        add_user_tag(user.id, slug_lc)
        flow = get_webinar_flow(slug_lc)
        if flow:
            markup = webinar_flow_start_keyboard(slug_lc, flow)
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
            context.user_data["last_webinar_tag"] = slug_lc
            return

    quiz_enabled = get_setting("quiz_enabled", "1") == "1"

    if not quiz_enabled:
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

    markup = start_keyboard()

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


async def show_quiz_result(chat_id: int, context: ContextTypes.DEFAULT_TYPE, email_sent: bool) -> None:
    score = context.user_data.get("score", 0)
    result = get_result(score)
    status = ("Также продублировали вам на почту!"
              if email_sent else "Не удалось отправить письмо. Проверь адрес и попробуй ещё раз через /start")
    keyboard = [[InlineKeyboardButton("Пройти ещё раз", callback_data="restart_quiz")]]

    await context.bot.send_message(
        chat_id=chat_id, parse_mode="HTML",
        text=(f"{result['emoji']} <b>Твой AI-профиль: {result['title']}</b>\n\n"
              f"Результат: <b>{score} из 24 баллов</b>\n\n"
              f"─────────────────────\n\n{result['text']}"),
    )

    await context.bot.send_message(
        chat_id=chat_id, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True,
        text=(f"{AI_TOOLS_TEXT}\n\n"
              f"─────────────────────\n\n\U0001f4e9 {status}"),
    )
