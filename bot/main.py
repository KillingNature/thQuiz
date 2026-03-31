import re
import asyncio

from telegram import Update, BotCommand, BotCommandScopeChat
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from .config import BOT_TOKEN, ADMIN_IDS, is_admin, logger
from .db import init_db, migrate_existing_users, save_user
from .content import get_result
from .email_service import send_email
from .quiz import cmd_start, send_question, show_quiz_result
from .admin import (
    cmd_help, cmd_newpost, cmd_newcase, cmd_newsale, cmd_newwebinar,
    cmd_cancel, cmd_posts, cmd_preview, cmd_schedule, cmd_send_now,
    cmd_delete_post, cmd_export, cmd_export_leads,
    cmd_stats, cmd_snapshot, cmd_compare, cmd_funnel, cmd_sources,
    cmd_check_active,
    cmd_set_start, cmd_preview_start, cmd_reset_start, cmd_toggle_quiz,
    cmd_set_start_button, cmd_set_start_buttons, cmd_set_button,
    cmd_target, cmd_tags, cmd_new_webinar_flow,
    handle_admin_input,
)
from .callbacks import button_handler, handle_form_input
from .broadcast import check_scheduled_posts
from .admin_menu import cmd_admin


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


async def setup_bot_commands(app: Application) -> None:
    """Устанавливает меню команд: общее для всех + расширенное для админов."""
    await app.bot.set_my_commands([
        BotCommand("start", "Начать / перезапустить бота"),
    ])

    admin_commands = [
        BotCommand("start", "Начать / перезапустить бота"),
        BotCommand("admin", "Панель администратора"),
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
    app.add_handler(CommandHandler("admin", cmd_admin))

    # Кнопки
    app.add_handler(CallbackQueryHandler(button_handler))

    # Текст и фото
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO | filters.VIDEO) & ~filters.COMMAND, message_router))

    # Планировщик рассылки — каждые 5 минут
    app.job_queue.run_repeating(check_scheduled_posts, interval=300, first=10)

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
