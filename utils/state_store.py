"""Minimal file-backed state persistence for stage/state between restarts.

Хранит в /tmp/phi_bot_state.json. TODO: заменить на Redis при наличии Railway KV.
"""

import json
import os
from pathlib import Path
from typing import Any

STATE_PATH = Path(os.environ.get("PHI_STATE_PATH", "/tmp/phi_bot_state.json"))


def load_state() -> dict[str, Any]:
    """Загрузить state из диска. Ключи — str(user_id)."""
    if not STATE_PATH.exists():
        return {}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): v for k, v in data.items()}  # keys as str for JSON
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    """Сохранить state на диск."""
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=0)
    except OSError:
        pass  # /tmp может быть read-only в некоторых конфигурациях
