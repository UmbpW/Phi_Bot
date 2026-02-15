"""Логирование диалогов, фидбека и safety-событий — по пользователям."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
LOGS_DIR = PROJECT_ROOT / "logs"
USERS_DIR = LOGS_DIR / "users"

# PostgreSQL (Railway) — опционально
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
_db_conn = None


def _get_db_conn():
    """Ленивое подключение к PostgreSQL (Railway требует sslmode)."""
    global _db_conn
    if not DATABASE_URL:
        return None
    if _db_conn is not None and not _db_conn.closed:
        return _db_conn
    try:
        import psycopg2
        url = DATABASE_URL
        if "sslmode" not in url.lower():
            url += "?sslmode=require" if "?" not in url else "&sslmode=require"
        _db_conn = psycopg2.connect(url)
        cur = _db_conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dialogs (
                id SERIAL PRIMARY KEY, ts TIMESTAMPTZ, user_id BIGINT,
                text_in TEXT, lenses TEXT, text_out TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS feedback_log (
                id SERIAL PRIMARY KEY, ts TIMESTAMPTZ, user_id BIGINT,
                message_id BIGINT, rating VARCHAR(32)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS safety_log (
                id SERIAL PRIMARY KEY, ts TIMESTAMPTZ, user_id BIGINT,
                text_in TEXT, reason VARCHAR(64)
            )
        """)
        _db_conn.commit()
        cur.close()
        print("[DB] PostgreSQL connected, tables ready")
        return _db_conn
    except Exception as e:
        print(f"[DB] Connection error: {e}")
        _db_conn = None
        return None


def _user_dir(user_id: int) -> Path:
    """Папка логов пользователя: logs/users/{user_id}/"""
    path = USERS_DIR / str(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_dialog(
    user_id: int,
    text_in: str,
    lenses: list[str],
    text_out: str,
) -> None:
    """Логирует диалог в файл и (если DATABASE_URL) в PostgreSQL."""
    ts = _ts()
    record = {
        "ts": ts,
        "user_id": user_id,
        "text_in": text_in,
        "lenses": lenses,
        "text_out": text_out,
    }
    udir = _user_dir(user_id)
    with open(udir / "dialogs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    conn = _get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO dialogs (ts, user_id, text_in, lenses, text_out) VALUES (%s, %s, %s, %s, %s)",
                (ts, user_id, text_in, json.dumps(lenses, ensure_ascii=False), text_out),
            )
            conn.commit()
            cur.close()
        except Exception as e:
            conn.rollback()
            print(f"[DB] Insert dialogs error: {e}")


def log_feedback(
    user_id: int,
    message_id: int,
    rating: str,
) -> None:
    """Логирует фидбек в файл и (если DATABASE_URL) в PostgreSQL."""
    ts = _ts()
    record = {"ts": ts, "user_id": user_id, "message_id": message_id, "rating": rating}
    udir = _user_dir(user_id)
    with open(udir / "feedback.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    conn = _get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO feedback_log (ts, user_id, message_id, rating) VALUES (%s, %s, %s, %s)",
                (ts, user_id, message_id, rating),
            )
            conn.commit()
            cur.close()
        except Exception as e:
            conn.rollback()
            print(f"[DB] Insert feedback error: {e}")


def log_event(event_name: str, **kwargs) -> None:
    """Логирует generic event в файл (events.jsonl)."""
    ts = _ts()
    record = {"ts": ts, "event": event_name, **kwargs}
    # user_id для папки; если нет — в общий events.jsonl
    user_id = kwargs.get("user_id")
    if user_id is not None:
        udir = _user_dir(user_id)
        path = udir / "events.jsonl"
    else:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        path = LOGS_DIR / "events.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_safety_event(
    user_id: int,
    text_in: str,
    reason: str = "self_harm_indicators",
) -> None:
    """Логирует safety-событие в файл и (если DATABASE_URL) в PostgreSQL."""
    ts = _ts()
    record = {"ts": ts, "user_id": user_id, "text_in": text_in, "reason": reason}
    udir = _user_dir(user_id)
    with open(udir / "safety.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    conn = _get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO safety_log (ts, user_id, text_in, reason) VALUES (%s, %s, %s, %s)",
                (ts, user_id, text_in, reason),
            )
            conn.commit()
            cur.close()
        except Exception as e:
            conn.rollback()
            print(f"[DB] Insert safety error: {e}")


def export_dialogs_from_db() -> list[dict]:
    """Экспорт диалогов из PostgreSQL (для /export)."""
    conn = _get_db_conn()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute("SELECT ts, user_id, text_in, lenses, text_out FROM dialogs ORDER BY ts")
        rows = cur.fetchall()
        cur.close()
        return [
            {
                "ts": str(r[0]),
                "user_id": r[1],
                "text_in": r[2],
                "lenses": json.loads(r[3]) if r[3] else [],
                "text_out": r[4],
            }
            for r in rows
        ]
    except Exception:
        return []
