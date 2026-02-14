"""Упаковка контекста для OpenAI: последние сообщения + опциональный summary."""

from typing import Any

MAX_HISTORY = 20
KEEP_USER = 2
KEEP_BOT = 2


def pack_context(user_id: int, state: dict, history_store: dict[int, list]) -> str:
    """Формирует блок контекста для передачи в модель.

    history_store[user_id] = [{"role":"user"|"assistant","content":...}, ...]
    Берёт последние 4–6 сообщений (2–3 user + 2–3 bot) по порядку.
    """
    history = history_store.get(user_id, [])
    if not history:
        return ""

    # Последние 6 сообщений (до текущего, который ещё не добавлен)
    tail = history[-(KEEP_USER + KEEP_BOT) * 2 :]
    parts = []
    for h in tail:
        role = h.get("role", "")
        content = (h.get("content") or "")[:400]
        if content:
            label = "Пользователь" if role == "user" else "Бот"
            parts.append(f"{label}: {content}")

    return "\n\n".join(parts) if parts else ""


def append_history(
    history_store: dict[int, list],
    user_id: int,
    role: str,
    content: str,
) -> None:
    """Добавить сообщение в историю. Ограничить до MAX_HISTORY."""
    if user_id not in history_store:
        history_store[user_id] = []
    history_store[user_id].append({"role": role, "content": content})
    hist = history_store[user_id]
    if len(hist) > MAX_HISTORY:
        history_store[user_id] = hist[-MAX_HISTORY:]
