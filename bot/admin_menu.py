"""
Inline-меню администратора.

/admin — главное меню с inline-кнопками.
Все существующие текстовые команды продолжают работать.
"""

import io

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .config import is_admin, now_msk, POST_TYPE_EMOJI, POST_TYPE_NAME
from .db import (
    get_all_posts, get_post,
    get_stats, get_bot_users_stats, get_funnel_stats, get_sources_stats,
    get_archetype_distribution,
    save_snapshot, get_last_snapshot,
    get_setting,
    get_all_tags_stats, get_all_webinar_flows,
    export_users_csv, export_leads_csv,
)
from .admin import _clear_admin_state


# ── Клавиатуры ──────────────────────────────────────────────────────────

def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001f4dd Контент", callback_data="adm_content"),
         InlineKeyboardButton("\U0001f4ca Аналитика", callback_data="adm_analytics")],
        [InlineKeyboardButton("\u2699\ufe0f Настройки", callback_data="adm_settings"),
         InlineKeyboardButton("\U0001f465 Аудитория", callback_data="adm_audience")],
    ])


def _content_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Новый пост", callback_data="adm_do_newpost"),
         InlineKeyboardButton("Новый кейс", callback_data="adm_do_newcase")],
        [InlineKeyboardButton("Новая продажа", callback_data="adm_do_newsale"),
         InlineKeyboardButton("Новый вебинар", callback_data="adm_do_newwebinar")],
        [InlineKeyboardButton("Список постов", callback_data="adm_do_posts"),
         InlineKeyboardButton("Воронки вебинаров", callback_data="adm_do_webflows")],
        [InlineKeyboardButton("\u2b05 Назад", callback_data="adm_main")],
    ])


def _analytics_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Статистика", callback_data="adm_do_stats"),
         InlineKeyboardButton("Воронка", callback_data="adm_do_funnel")],
        [InlineKeyboardButton("Источники", callback_data="adm_do_sources")],
        [InlineKeyboardButton("Снимок аудитории", callback_data="adm_do_snapshot"),
         InlineKeyboardButton("Сравнить", callback_data="adm_do_compare")],
        [InlineKeyboardButton("\u2b05 Назад", callback_data="adm_main")],
    ])


def _settings_keyboard() -> InlineKeyboardMarkup:
    quiz_on = get_setting("quiz_enabled", "1") == "1"
    quiz_label = "\u2705 Квиз: ВКЛ" if quiz_on else "\u26d4 Квиз: ВЫКЛ"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Предпросмотр старта", callback_data="adm_do_preview_start")],
        [InlineKeyboardButton("Изменить старт", callback_data="adm_do_set_start"),
         InlineKeyboardButton("Кнопки старта", callback_data="adm_do_set_start_buttons")],
        [InlineKeyboardButton("Сбросить старт", callback_data="adm_do_reset_start"),
         InlineKeyboardButton(quiz_label, callback_data="adm_do_toggle_quiz")],
        [InlineKeyboardButton("\u2b05 Назад", callback_data="adm_main")],
    ])


def _audience_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Теги", callback_data="adm_do_tags"),
         InlineKeyboardButton("Проверить активных", callback_data="adm_do_check_active")],
        [InlineKeyboardButton("Экспорт юзеров", callback_data="adm_do_export"),
         InlineKeyboardButton("Экспорт лидов", callback_data="adm_do_export_leads")],
        [InlineKeyboardButton("\u2b05 Назад", callback_data="adm_main")],
    ])


# ── Команда /admin ──────────────────────────────────────────────────────

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    _clear_admin_state(context)
    await update.message.reply_text(
        "\U0001f527 <b>Панель администратора</b>\n\nВыберите раздел:",
        parse_mode="HTML",
        reply_markup=_main_keyboard(),
    )


# ── Роутер callback-запросов adm_* ─────────────────────────────────────

async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id

    if not is_admin(query.from_user.id):
        return

    # ── Навигация по разделам ──

    if data == "adm_main":
        await query.edit_message_text(
            "\U0001f527 <b>Панель администратора</b>\n\nВыберите раздел:",
            parse_mode="HTML", reply_markup=_main_keyboard(),
        )
        return

    if data == "adm_content":
        await query.edit_message_text(
            "\U0001f4dd <b>Контент</b>\n\nВыберите действие:",
            parse_mode="HTML", reply_markup=_content_keyboard(),
        )
        return

    if data == "adm_analytics":
        await query.edit_message_text(
            "\U0001f4ca <b>Аналитика</b>\n\nВыберите отчёт:",
            parse_mode="HTML", reply_markup=_analytics_keyboard(),
        )
        return

    if data == "adm_settings":
        await query.edit_message_text(
            "\u2699\ufe0f <b>Настройки</b>\n\nВыберите действие:",
            parse_mode="HTML", reply_markup=_settings_keyboard(),
        )
        return

    if data == "adm_audience":
        await query.edit_message_text(
            "\U0001f465 <b>Аудитория</b>\n\nВыберите действие:",
            parse_mode="HTML", reply_markup=_audience_keyboard(),
        )
        return

    # ── Контент: действия ──

    if data == "adm_do_newpost":
        _clear_admin_state(context)
        context.user_data["admin_state"] = "awaiting_post_content"
        context.user_data["admin_draft"] = {"type": "post"}
        await context.bot.send_message(
            chat_id, "\U0001f4dd <b>Создание поста</b>\n\n"
            "Отправьте содержимое поста.\n"
            "Можно использовать <b>жирный</b>, <i>курсив</i>, эмодзи, ссылки.\n"
            "Можно прикрепить фото или видео.\n\n"
            "/cancel \u2014 отменить", parse_mode="HTML",
        )
        return

    if data == "adm_do_newcase":
        _clear_admin_state(context)
        context.user_data["admin_state"] = "awaiting_case_content"
        context.user_data["admin_draft"] = {"type": "case"}
        await context.bot.send_message(
            chat_id, "\U0001f9e9 <b>Создание интерактив-кейса</b>\n\n"
            "<b>Шаг 1 из 3:</b> Отправьте описание ситуации/кейса.\n"
            "Можно с фото или видео, форматированием, эмодзи.\n\n"
            "/cancel \u2014 отменить", parse_mode="HTML",
        )
        return

    if data == "adm_do_newsale":
        _clear_admin_state(context)
        context.user_data["admin_state"] = "awaiting_sale_content"
        context.user_data["admin_draft"] = {"type": "sale"}
        await context.bot.send_message(
            chat_id, "\U0001f4b0 <b>Создание поста с формой</b>\n\n"
            "Отправьте текст анонса/продажи.\n"
            "Можно с фото или видео, форматированием, эмодзи.\n\n"
            "После поста автоматически добавится кнопка\n"
            "\u00abОставить заявку\u00bb \u2014 пользователь заполнит: имя, телефон, email, ник.\n\n"
            "/cancel \u2014 отменить", parse_mode="HTML",
        )
        return

    if data == "adm_do_newwebinar":
        _clear_admin_state(context)
        context.user_data["admin_state"] = "awaiting_webinar_content"
        context.user_data["admin_draft"] = {"type": "webinar"}
        await context.bot.send_message(
            chat_id, "\U0001f4e2 <b>Создание анонса вебинара</b>\n\n"
            "<b>Шаг 1 из 3:</b> Отправьте текст анонса.\n"
            "Можно с фото или видео, форматированием, эмодзи.\n\n"
            "/cancel \u2014 отменить", parse_mode="HTML",
        )
        return

    if data == "adm_do_posts":
        posts = get_all_posts()
        if not posts:
            await context.bot.send_message(chat_id, "Постов пока нет. Создайте первый через меню.")
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
            lines.append(f"<b>#{p['id']}</b> {emoji} {name} | {status} | \U0001f3af {target}\n<i>{preview}</i>\n")
        await context.bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
        return

    if data == "adm_do_webflows":
        flows = get_all_webinar_flows()
        if not flows:
            await context.bot.send_message(
                chat_id,
                "Воронок пока нет.\n"
                "Создайте: /new_webinar_flow <code>webinar_x</code>",
                parse_mode="HTML",
            )
            return
        lines = ["\U0001f3ac <b>Вебинарные воронки:</b>\n"]
        for f in flows:
            lines.append(f"\u2022 <b>{f['slug']}</b> \u2014 {f.get('title') or 'без названия'}\n  <i>{f['created_at'][:16]}</i>")
        await context.bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
        return

    # ── Аналитика: действия ──

    if data == "adm_do_stats":
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
        await context.bot.send_message(
            chat_id,
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
        return

    if data == "adm_do_funnel":
        f = get_funnel_stats()

        def _pct(part: int, whole: int) -> str:
            return f"{round(part / whole * 100)}%" if whole > 0 else "\u2014"

        await context.bot.send_message(
            chat_id,
            f"\U0001f53d <b>Воронка конверсии</b>\n\n"
            f"1. Зашли в бота: <b>{f['started_bot']}</b> (100%)\n"
            f"2. Начали квиз: <b>{f['started_quiz']}</b> ({_pct(f['started_quiz'], f['started_bot'])})\n"
            f"3. Прошли квиз: <b>{f['completed_quiz']}</b> ({_pct(f['completed_quiz'], f['started_bot'])})\n"
            f"4. Оставили email: <b>{f['left_email']}</b> ({_pct(f['left_email'], f['started_bot'])})\n"
            f"5. Оставили заявку: <b>{f['leads']}</b> ({_pct(f['leads'], f['started_bot'])})",
            parse_mode="HTML",
        )
        return

    if data == "adm_do_sources":
        sources = get_sources_stats()
        if not sources:
            await context.bot.send_message(chat_id, "Пока нет данных об источниках.")
            return
        lines = ["\U0001f517 <b>Источники трафика</b>\n"]
        for src, cnt in sources:
            lines.append(f"  {src}: <b>{cnt}</b>")
        lines.append(
            f"\n\U0001f4a1 <i>Для UTM-трекинга используйте ссылки вида:\n"
            f"https://t.me/ИМЯ_БОТА?start=ИСТОЧНИК</i>"
        )
        await context.bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
        return

    if data == "adm_do_snapshot":
        label = now_msk().strftime("%d.%m.%Y %H:%M")
        b = get_bot_users_stats()
        s = get_stats()
        snap_id = save_snapshot(label, b["total"], b["active"], s["users"], s["leads"])
        await context.bot.send_message(
            chat_id,
            f"\U0001f4f8 <b>Снимок #{snap_id} сохранён</b>\n"
            f"Метка: <i>{label}</i>\n\n"
            f"Всего: <b>{b['total']}</b>\n"
            f"Активных: <b>{b['active']}</b>\n"
            f"Прошли квиз: <b>{s['users']}</b>\n"
            f"Заявки: <b>{s['leads']}</b>",
            parse_mode="HTML",
        )
        return

    if data == "adm_do_compare":
        snap = get_last_snapshot()
        if not snap:
            await context.bot.send_message(chat_id, "Нет сохранённых снимков. Сначала сделайте снимок через меню.")
            return
        b = get_bot_users_stats()
        s = get_stats()

        def _diff(current: int, old: int) -> str:
            d = current - old
            return f"+{d}" if d >= 0 else str(d)

        await context.bot.send_message(
            chat_id,
            f"\U0001f4ca <b>Сравнение с последним снимком</b>\n"
            f"Метка: <i>{snap['label']}</i>\n"
            f"Дата снимка: {snap['created_at'][:16]}\n\n"
            f"Всего в боте: {snap['total_users']} \u2192 <b>{b['total']}</b> (<b>{_diff(b['total'], snap['total_users'])}</b>)\n"
            f"Активных: {snap['active_users']} \u2192 <b>{b['active']}</b> (<b>{_diff(b['active'], snap['active_users'])}</b>)\n"
            f"Прошли квиз: {snap['quiz_completed']} \u2192 <b>{s['users']}</b> (<b>{_diff(s['users'], snap['quiz_completed'])}</b>)\n"
            f"Заявки: {snap['leads_count']} \u2192 <b>{s['leads']}</b> (<b>{_diff(s['leads'], snap['leads_count'])}</b>)",
            parse_mode="HTML",
        )
        return

    # ── Настройки: действия ──

    if data == "adm_do_preview_start":
        await _do_preview_start(chat_id, context)
        return

    if data == "adm_do_set_start":
        _clear_admin_state(context)
        context.user_data["admin_state"] = "awaiting_start_content"
        await context.bot.send_message(
            chat_id,
            "\U0001f3e0 <b>Редактирование стартового сообщения</b>\n\n"
            "Отправьте новый текст приветствия.\n"
            "Можно с фото, форматированием, эмодзи.\n\n"
            "Это сообщение увидит каждый пользователь при нажатии /start.\n"
            "Кнопка \u00abНачать тест\u00bb добавится автоматически.\n\n"
            "/cancel \u2014 отменить", parse_mode="HTML",
        )
        return

    if data == "adm_do_set_start_buttons":
        _clear_admin_state(context)
        context.user_data["admin_state"] = "awaiting_start_inline_buttons"
        await context.bot.send_message(
            chat_id,
            "<b>Кнопки-ссылки под \u00abНачать тест\u00bb</b>\n\n"
            "Отправьте <b>одним сообщением</b>, каждая строка:\n"
            "<code>Текст | https://...</code>\n\n"
            "Несколько ссылок \u2014 несколько строк.\n"
            "<code>-</code> \u2014 убрать все доп. кнопки (только \u00abНачать тест\u00bb).\n\n"
            "/cancel \u2014 отменить", parse_mode="HTML",
        )
        return

    if data == "adm_do_reset_start":
        from .db import set_setting
        from .content import DEFAULT_START_MESSAGE
        set_setting("start_message", DEFAULT_START_MESSAGE)
        set_setting("start_photo", "")
        set_setting("start_inline_buttons", "[]")
        set_setting("start_button_text", "")
        set_setting("start_button_url", "")
        await context.bot.send_message(chat_id, "\u2705 Стартовое сообщение сброшено на стандартное.")
        # Обновляем подменю настроек
        await query.edit_message_text(
            "\u2699\ufe0f <b>Настройки</b>\n\nВыберите действие:",
            parse_mode="HTML", reply_markup=_settings_keyboard(),
        )
        return

    if data == "adm_do_toggle_quiz":
        current = get_setting("quiz_enabled", "1")
        new_value = "0" if current == "1" else "1"
        from .db import set_setting
        set_setting("quiz_enabled", new_value)
        if new_value == "1":
            await context.bot.send_message(
                chat_id,
                "\u2705 <b>Квиз включён.</b>\n\n"
                "Пользователи после /start будут проходить тест.", parse_mode="HTML")
        else:
            await context.bot.send_message(
                chat_id,
                "\u26d4 <b>Квиз отключён.</b>\n\n"
                "Пользователи после /start сразу получат подборку AI-инструментов.\n"
                "Кнопка \u00abПройти тест\u00bb останется доступна.", parse_mode="HTML")
        # Обновляем кнопку квиза в подменю
        await query.edit_message_text(
            "\u2699\ufe0f <b>Настройки</b>\n\nВыберите действие:",
            parse_mode="HTML", reply_markup=_settings_keyboard(),
        )
        return

    # ── Аудитория: действия ──

    if data == "adm_do_tags":
        stats = get_all_tags_stats()
        if not stats:
            await context.bot.send_message(chat_id, "Пока нет меток.")
            return
        lines = ["\U0001f3f7 <b>Метки пользователей</b>\n"]
        for tag, cnt in stats:
            lines.append(f"{tag}: <b>{cnt}</b>")
        await context.bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
        return

    if data == "adm_do_check_active":
        await _do_check_active(chat_id, context)
        return

    if data == "adm_do_export":
        data_csv = export_users_csv()
        buf = io.BytesIO(data_csv.encode("utf-8-sig"))
        buf.name = f"users_{now_msk().strftime('%Y%m%d_%H%M%S')}.csv"
        await context.bot.send_document(
            chat_id, document=buf,
            caption=f"Пользователи квиза ({now_msk().strftime('%d.%m.%Y %H:%M')})",
        )
        return

    if data == "adm_do_export_leads":
        data_csv = export_leads_csv()
        buf = io.BytesIO(data_csv.encode("utf-8-sig"))
        buf.name = f"leads_{now_msk().strftime('%Y%m%d_%H%M%S')}.csv"
        await context.bot.send_document(
            chat_id, document=buf,
            caption=f"Заявки ({now_msk().strftime('%d.%m.%Y %H:%M')})",
        )
        return


# ── Вспомогательные ─────────────────────────────────────────────────────

async def _do_check_active(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    import asyncio
    from .db import _connect, mark_user_blocked
    await context.bot.send_message(chat_id, "\U0001f50d Проверяю активных подписчиков\u2026 Это может занять некоторое время.")
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
    await context.bot.send_message(
        chat_id,
        f"\u2705 <b>Проверка завершена</b>\n\n"
        f"Активных: <b>{active}</b>\n"
        f"Заблокировали: <b>{newly_blocked}</b>\n"
        f"Всего проверено: <b>{active + newly_blocked}</b>",
        parse_mode="HTML",
    )


async def _do_preview_start(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .content import DEFAULT_START_MESSAGE
    from .keyboards import start_keyboard
    start_text = get_setting("start_message", DEFAULT_START_MESSAGE)
    start_photo = get_setting("start_photo", "")
    markup = start_keyboard()
    await context.bot.send_message(chat_id, "\U0001f441 <b>Текущее стартовое сообщение:</b>", parse_mode="HTML")
    if start_photo:
        await context.bot.send_photo(
            chat_id=chat_id, photo=start_photo,
            caption=start_text, reply_markup=markup, parse_mode="HTML",
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id, text=start_text,
            reply_markup=markup, parse_mode="HTML",
        )
