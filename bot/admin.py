import io
import json
import asyncio
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .config import is_admin, now_msk, POST_TYPE_EMOJI, POST_TYPE_NAME, logger
from .db import (
    get_all_posts, get_post, create_post,
    update_post_schedule, update_post_target, update_post_button, delete_post_db,
    mark_post_sent,
    export_users_csv, export_leads_csv,
    get_stats, get_bot_users_stats, get_funnel_stats, get_sources_stats,
    get_archetype_distribution,
    save_snapshot, get_last_snapshot,
    mark_user_blocked,
    get_setting, set_setting,
    set_webinar_flow, get_all_tags_stats,
    _connect,
)
from .content import DEFAULT_START_MESSAGE
from .keyboards import (
    start_keyboard, parse_url_buttons_lines, parse_webinar_start_buttons,
)
from .broadcast import send_post_preview, broadcast_post


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "<b>\U0001f527 Справка администратора</b>\n\n"
        "Основной интерфейс: /admin \u2014 интерактивное меню с кнопками.\n\n"
        "<b>\U0001f4dd Контент</b>\n"
        "Создавайте 4 типа постов: обычный, интерактив-кейс (ситуация + варианты + разбор), "
        "пост с формой заявки и анонс вебинара. Посты можно планировать по дате, "
        "ограничивать по сегменту аудитории, добавлять кнопки-ссылки.\n\n"
        "<b>\U0001f3ac Вебинарные воронки</b>\n"
        "Deep-link <code>?start=webinar_x</code> \u2014 пользователь попадает "
        "в мини-воронку: стартовое сообщение \u2192 кнопки/варианты ответа \u2192 "
        "подтверждение \u2192 CTA. Создание: /new_webinar_flow <code>webinar_x</code>\n\n"
        "<b>\U0001f4ca Аналитика</b>\n"
        "Статистика аудитории, воронка конверсии (бот \u2192 квиз \u2192 email \u2192 заявка), "
        "источники трафика (UTM), снимки аудитории для сравнения до/после.\n\n"
        "<b>\u2699\ufe0f Настройки</b>\n"
        "Стартовое сообщение (текст/фото), кнопки в приветствии, вкл/выкл квиза.\n\n"
        "<b>\U0001f465 Аудитория</b>\n"
        "Метки-сегменты, проверка активных, экспорт пользователей и заявок в CSV.\n\n"
        "<b>\U0001f4a1 Команды-шорткаты</b>\n"
        "Некоторые действия требуют ID поста:\n"
        "/preview <code>ID</code> \u2014 предпросмотр\n"
        "/schedule <code>ID ГГГГ-ММ-ДД ЧЧ:ММ</code> \u2014 запланировать (МСК)\n"
        "/send_now <code>ID</code> \u2014 отправить сейчас\n"
        "/set_button <code>ID Текст | URL</code> \u2014 кнопка-ссылка\n"
        "/target <code>ID TAG|all</code> \u2014 сегмент рассылки\n"
        "/delete_post <code>ID</code> \u2014 удалить\n"
        "/cancel \u2014 отменить текущее действие",
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
        "Можно прикрепить фото или видео.\n\n"
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
        "Можно с фото или видео, форматированием, эмодзи.\n\n"
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
        "Можно с фото или видео, форматированием, эмодзи.\n\n"
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
        "Можно с фото или видео, форматированием, эмодзи.\n\n"
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
    await send_post_preview(update.effective_chat.id, post, context)


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
    markup = start_keyboard()

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
            "Пример: /target 12 webinar_27",
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
        "<b>Шаг 2</b> — сразу кнопки под ним: ответы на вопрос, ссылки; запись с лендинга "
        "можно не дублировать — используйте несколько строк с вариантами ответа.",
        parse_mode="HTML",
    )


# ══════════════════════════════ АДМИН ВВОД ══════════════════════════════


def _extract_content(message) -> tuple[str | None, str | None, str | None]:
    """Извлекает text_html и медиа (фото/видео) file_id из сообщения."""
    photo_id = None
    video_id = None
    text_html = None
    if message.photo:
        photo_id = message.photo[-1].file_id
        text_html = message.caption_html
    elif message.video:
        video_id = message.video.file_id
        text_html = message.caption_html
    elif message.text:
        text_html = message.text_html
    return text_html, photo_id, video_id


async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("admin_state")
    draft = context.user_data.get("admin_draft", {})
    msg = update.message
    text_html, photo_id, video_id = _extract_content(msg)

    # ── Стартовое сообщение ──
    if state == "awaiting_start_content":
        if video_id:
            await msg.reply_text("Для стартового сообщения видео пока не поддерживается. Пришлите текст или фото.")
            return
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
        if video_id:
            await msg.reply_text("В стартовом сообщении webinar flow видео пока не поддерживается. Пришлите текст или фото.")
            return
        draft["start_text"] = text_html or ""
        draft["start_photo"] = photo_id or ""
        context.user_data["admin_state"] = "awaiting_webinar_flow_start_buttons"
        await msg.reply_text(
            "✅ Стартовое сообщение сохранено.\n\n"
            "<b>Шаг 2/4: интерактивные кнопки</b> под этим сообщением "
            "(как варианты у кейс-поста).\n\n"
            "Каждая строка — одна кнопка (сверху вниз):\n"
            "• <b>Ссылка:</b> <code>Текст | https://...</code>\n"
            "• <b>Варианты ответа</b> — текст строкой; <b>несколько строк</b> = кнопки выбора "
            "(люди уже с лендинга — без лишней «Записаться»).\n"
            "• <b>Явная запись в боте</b> — одна строка с <code>+</code>, например "
            "<code>+Записаться на эфир</code> (можно вместе с вариантами ответа).\n"
            "• <b>Одна</b> строка без <code>|</code> и без <code>+</code> = одна кнопка записи (старый режим).\n\n"
            "<code>-</code> — только «✅ Записаться».",
            parse_mode="HTML",
        )
        return

    # ── Webinar flow: шаг 2 — кнопки старта ──
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
        context.user_data["admin_state"] = "awaiting_webinar_flow_confirm"
        await msg.reply_text(
            "<b>Шаг 3/4:</b> сообщение после выбора варианта (или после кнопки записи, если она есть).\n"
            "Текстом или фото с подписью.",
            parse_mode="HTML",
        )
        return

    # ── Webinar flow: шаг 3 — текст после выбора / записи ──
    if state == "awaiting_webinar_flow_confirm":
        draft["confirm_text"] = text_html or "Спасибо!"
        context.user_data["admin_state"] = "awaiting_webinar_flow_confirm_cta"
        await msg.reply_text(
            "<b>Шаг 4/4:</b> опциональная кнопка-ссылка <b>под этим сообщением</b>.\n"
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
        btns = draft.get("start_buttons")
        if not btns:
            btns = [{"type": "optin", "text": "✅ Записаться"}]
        set_webinar_flow(
            slug=slug,
            title=slug,
            start_text=draft.get("start_text", ""),
            start_photo=draft.get("start_photo", ""),
            confirm_text=draft.get("confirm_text", "Спасибо!"),
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
        pid = create_post("post", text_html=text_html, photo_id=photo_id, video_id=video_id,
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
        draft["video_id"] = video_id
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
        pid = create_post("case", text_html=draft.get("text_html"), photo_id=draft.get("photo_id"), video_id=draft.get("video_id"),
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
        pid = create_post("sale", text_html=text_html, photo_id=photo_id, video_id=video_id,
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
        draft["video_id"] = video_id
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
                          video_id=draft.get("video_id"),
                          webinar_link=link, created_by=update.effective_user.id,
                          webinar_slug=draft.get("webinar_slug", ""))
        _clear_admin_state(context)
        await msg.reply_text(
            f"\u2705 Анонс вебинара <b>#{pid}</b> создан!\n\n"
            f"/preview {pid} — посмотреть\n"
            f"/schedule {pid} 2026-03-17 10:00 — запланировать\n"
            f"/send_now {pid} — отправить сейчас", parse_mode="HTML")
        return
