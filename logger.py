"""Логирование диалогов, фидбека и safety-событий — по пользователям."""

import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
LOGS_DIR = PROJECT_ROOT / "logs"
USERS_DIR = LOGS_DIR / "users"


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
    """Логирует диалог в logs/users/{user_id}/dialogs.jsonl."""
    udir = _user_dir(user_id)
    record = {
        "ts": _ts(),
        "user_id": user_id,
        "text_in": text_in,
        "lenses": lenses,
        "text_out": text_out,
    }
    with open(udir / "dialogs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_feedback(
    user_id: int,
    message_id: int,
    rating: str,
) -> None:
    """Логирует фидбек в logs/users/{user_id}/feedback.jsonl."""
    udir = _user_dir(user_id)
    record = {
        "ts": _ts(),
        "user_id": user_id,
        "message_id": message_id,
        "rating": rating,
    }
    with open(udir / "feedback.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_safety_event(
    user_id: int,
    text_in: str,
    reason: str = "self_harm_indicators",
) -> None:
    """Логирует safety-событие в logs/users/{user_id}/safety.jsonl."""
    udir = _user_dir(user_id)
    record = {
        "ts": _ts(),
        "user_id": user_id,
        "text_in": text_in,
        "reason": reason,
    }
    with open(udir / "safety.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
