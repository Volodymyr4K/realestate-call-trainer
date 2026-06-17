"""Збереження розмов і звітів у SQLite.

Чому SQLite: файл-база, нуль налаштувань (для проду — Postgres, див. docs).
Зʼєднання відкриваємо на кожну операцію — просто й потоко-безпечно.
"""
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from bot.config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    scenario    INTEGER NOT NULL,
    level       INTEGER NOT NULL,
    started_at  TEXT,
    finished_at TEXT,
    turns       INTEGER,
    transcript  TEXT,        -- JSON: [["manager"/"owner", текст], ...]
    report      TEXT,        -- JSON звіту або NULL поки нема
    audio       TEXT         -- JSON: [["manager"/"owner", шлях_до_ogg], ...]
);

-- Лог КОЖНОЇ спроби розпізнавання (включно з провалами) — для перевірки точності STT.
CREATE TABLE IF NOT EXISTS stt_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    sid         TEXT,        -- session id розмови
    turn        INTEGER,
    audio_path  TEXT,        -- шлях до .ogg голосового користувача
    text        TEXT,        -- що почув Whisper ('' = провал)
    ok          INTEGER,     -- 1 = розпізнано, 0 = порожньо/провал
    created_at  TEXT
);
"""


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Створює таблицю, якщо її ще нема (безпечно викликати щоразу)."""
    # closing() гарантує закриття зʼєднання; внутрішній `conn` комітить транзакцію.
    with closing(_connect()) as conn, conn:
        conn.executescript(_SCHEMA)
        # Міграція: якщо БД створена до колонки audio — додаємо її.
        cols = {row[1] for row in conn.execute("PRAGMA table_info(conversations)")}
        if "audio" not in cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN audio TEXT")


def save_conversation(user_id: int, scenario: int, level: int, transcript: list,
                      turns: int, started_at: str | None = None,
                      report: dict | None = None, audio: list | None = None) -> int:
    """Зберігає розмову, повертає її id."""
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO conversations "
            "(user_id, scenario, level, started_at, finished_at, turns, transcript, report, audio) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (user_id, scenario, level, started_at,
             datetime.now(timezone.utc).isoformat(timespec="seconds"),
             turns, json.dumps(transcript, ensure_ascii=False),
             json.dumps(report, ensure_ascii=False) if report is not None else None,
             json.dumps(audio, ensure_ascii=False) if audio is not None else None),
        )
        return cur.lastrowid


def get_conversation(conv_id: int) -> dict | None:
    """Повертає розмову за id (transcript/report вже розпарсені) або None."""
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM conversations WHERE id=?", (conv_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["transcript"] = json.loads(d["transcript"]) if d["transcript"] else []
    d["report"] = json.loads(d["report"]) if d["report"] else None
    d["audio"] = json.loads(d["audio"]) if d.get("audio") else []
    return d


def list_conversations(user_id: int) -> list[dict]:
    """Короткий список розмов користувача (без транскрипту), новіші зверху."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT id, scenario, level, finished_at, turns FROM conversations "
            "WHERE user_id=? ORDER BY id DESC", (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def log_stt(user_id: int, sid: str, turn: int, audio_path: str, text: str, ok: bool) -> None:
    """Логує одну спробу розпізнавання (і успіх, і провал) — для перевірки точності STT."""
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT INTO stt_log (user_id, sid, turn, audio_path, text, ok, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, sid, turn, audio_path, text, int(ok),
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )


def list_stt(limit: int | None = None) -> list[dict]:
    """Усі спроби STT, новіші зверху (audio_path + що почув Whisper + ok)."""
    q = "SELECT * FROM stt_log ORDER BY id DESC"
    if limit:
        q += f" LIMIT {int(limit)}"
    with closing(_connect()) as conn:
        return [dict(r) for r in conn.execute(q).fetchall()]
