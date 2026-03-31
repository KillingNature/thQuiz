import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .config import logger
from .db import (
    get_all_subscriber_ids, get_tag_user_ids,
    is_broadcast_sent, mark_broadcast_sent, mark_user_blocked,
    get_due_posts, mark_post_sent,
)


async def send_post_preview(chat_id: int, post: dict, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    if post.get("video_id"):
        await context.bot.send_video(
            chat_id=chat_id,
            video=post["video_id"],
            caption=post.get("text_html"),
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    elif post.get("photo_id"):
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


async def broadcast_post(post: dict, context: ContextTypes.DEFAULT_TYPE) -> tuple[int, int]:
    include_tag = (post.get("include_tag") or "").strip().lower()
    subscribers = get_tag_user_ids(include_tag) if include_tag else get_all_subscriber_ids()
    sent = 0
    failed = 0
    for tid in subscribers:
        if is_broadcast_sent(post["id"], tid):
            continue
        try:
            await send_post_preview(tid, post, context)
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
