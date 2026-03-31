import html as html_module
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .db import (
    mark_quiz_started, get_post, add_user_tag, get_webinar_flow, save_lead,
)
from .content import QUESTIONS, SCORE_MAP, FORM_STEPS
from .quiz import send_question


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

    # ── Вебинар: выбор варианта ответа (как кейс-пост) ──
    if data.startswith("wb_ch_"):
        rest = data[len("wb_ch_") :]
        try:
            slug, idx_s = rest.rsplit("_", 1)
            choice_idx = int(idx_s)
        except (ValueError, IndexError):
            return
        slug = slug.strip().lower()
        if not slug:
            return

        flow = get_webinar_flow(slug)
        if not flow:
            return

        try:
            wb_buttons = json.loads(flow.get("start_buttons_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            wb_buttons = []

        choice_labels = [b.get("text") or "?" for b in wb_buttons if b.get("type") == "choice"]
        chosen = choice_labels[choice_idx] if 0 <= choice_idx < len(choice_labels) else "?"

        confirm_text = flow.get("confirm_text") or "Спасибо!"
        body = (
            f"<b>Ваш выбор:</b> {html_module.escape(chosen)}\n"
            f"─────────────────────\n\n{confirm_text}"
        )
        kb_rows = []
        if flow.get("cta_text") and flow.get("cta_url"):
            kb_rows.append([InlineKeyboardButton(flow["cta_text"], url=flow["cta_url"])])
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=chat_id,
            text=body,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb_rows) if kb_rows else None,
        )
        return

    # ── Запись на вебинар через кнопку ──
    if data.startswith("wb_join_"):
        slug = data.replace("wb_join_", "").strip().lower()
        if not slug:
            return
        add_user_tag(query.from_user.id, slug)

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
