import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .db import get_setting


def parse_webinar_start_buttons(raw: str) -> tuple[list[dict] | None, str]:
    """Стартовые кнопки вебинара (как интерактив у постов).

    Строки:
    - «Текст | https://…» — кнопка-ссылка
    - «+Текст» — явная кнопка записи (wb_join), ровно одна такая строка
    - Одна строка без «|» и без «+» — кнопка записи (как раньше)
    - Две и больше строк без «|» и без «+» — все кнопки выбора ответа (callback)
    При строке «+…» все остальные строки без «|» считаются вариантами ответа.
    Только ссылки — без автодобавления «Записаться».
    «-» — только «✅ Записаться».
    """
    raw = (raw or "").strip()
    if not raw or raw == "-":
        return ([{"type": "optin", "text": "✅ Записаться"}], "")

    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    typed: list[tuple[str, object]] = []

    for line in lines:
        if "|" in line:
            t, u = [x.strip() for x in line.split("|", 1)]
            if u.startswith("http"):
                if not t:
                    return None, "Пустой текст кнопки в строке со ссылкой."
                typed.append(("url", {"type": "url", "text": t, "url": u}))
            else:
                return None, f"После «|» должна быть ссылка http(s). Строка: {line[:50]}..."
        elif line.startswith("+"):
            text = line[1:].strip()
            if not text:
                return None, "После + укажите текст кнопки записи."
            typed.append(("plus", text))
        else:
            typed.append(("plain", line))

    if sum(1 for t, _ in typed if t == "plus") > 1:
        return None, "Только одна строка с префиксом + (кнопка записи)."

    plain_texts = [v for t, v in typed if t == "plain"]
    has_plus = any(t == "plus" for t, _ in typed)

    out: list[dict] = []
    if has_plus:
        for t, v in typed:
            if t == "url":
                out.append(v)  # type: ignore[arg-type]
            elif t == "plus":
                out.append({"type": "optin", "text": v})
            else:
                out.append({"type": "choice", "text": v})
        return (out, "")

    if len(plain_texts) == 0:
        for t, v in typed:
            if t == "url":
                out.append(v)  # type: ignore[arg-type]
        return (out, "")

    if len(plain_texts) == 1:
        for t, v in typed:
            if t == "url":
                out.append(v)  # type: ignore[arg-type]
            elif t == "plain":
                out.append({"type": "optin", "text": v})
        return (out, "")

    for t, v in typed:
        if t == "url":
            out.append(v)  # type: ignore[arg-type]
        elif t == "plain":
            out.append({"type": "choice", "text": v})
    return (out, "")


def webinar_flow_start_keyboard(slug: str, flow: dict) -> InlineKeyboardMarkup:
    """Кнопки под стартовым сообщением вебинара (интерактивный блок)."""
    rows: list[list[InlineKeyboardButton]] = []
    js = flow.get("start_buttons_json")
    choice_i = 0
    if js:
        try:
            buttons = json.loads(js)
            for b in buttons:
                if b.get("type") == "optin":
                    rows.append([InlineKeyboardButton(b.get("text") or "Записаться", callback_data=f"wb_join_{slug}")])
                elif b.get("type") == "choice":
                    label = b.get("text") or "Вариант"
                    rows.append(
                        [InlineKeyboardButton(label, callback_data=f"wb_ch_{slug}_{choice_i}")]
                    )
                    choice_i += 1
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


def start_keyboard() -> InlineKeyboardMarkup:
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
