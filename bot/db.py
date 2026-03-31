import csv
import io
import json
import sqlite3
from datetime import timedelta

from .config import DB_PATH, now_msk


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
                video_id        TEXT,
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
            conn.execute("ALTER TABLE posts ADD COLUMN video_id TEXT")
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

def create_post(ptype: str, text_html: str = None, photo_id: str = None, video_id: str = None,
                case_options: list = None, case_answer_html: str = None,
                webinar_link: str = None, created_by: int = 0,
                button_text: str = None, button_url: str = None,
                include_tag: str = None, webinar_slug: str = None) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO posts (type,text_html,photo_id,video_id,case_options,case_answer_html,webinar_link,created_at,created_by,"
            "button_text,button_url,include_tag,webinar_slug) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ptype, text_html, photo_id, video_id,
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


def get_webinar_flow(slug: str) -> dict | None:
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM webinar_flows WHERE slug=?", (slug,)).fetchone()
    return dict(row) if row else None


def get_all_webinar_flows() -> list[dict]:
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT slug, title, created_at FROM webinar_flows ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


# --- settings ---

def get_setting(key: str, default: str = "") -> str:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
