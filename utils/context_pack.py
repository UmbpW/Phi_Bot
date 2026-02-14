"""Упаковка контекста для OpenAI: последние сообщения + опциональный summary."""

from typing import Any, Optional

MAX_HISTORY = 20
KEEP_USER = 2
KEEP_BOT = 2


def pack_context(
    user_id: int,
    state: dict,
    history_store: dict[int, list],
    user_language: Optional[str] = None,
) -> str:
    """Формирует блок контекста для передачи в модель.

    history_store[user_id] = [{"role":"user"|"assistant","content":...}, ...]
    Берёт последние 4–6 сообщений (2–3 user + 2–3 bot) по порядку.
    user_language: для SOURCE_RULE_LANGUAGE_MATCH (RU → только RU editions).
    """
    from philosophy.source_rule import get_user_language, should_allow_source_suggestion

    lang = get_user_language(user_language or state.get("user_language"))
    state["user_language"] = lang

    history = history_store.get(user_id, [])
    parts = []
    if lang:
        parts.append(f"[user_language: {lang}]")
    # SOURCE_SUGGESTION_RULE: только после lens_lock
    if should_allow_source_suggestion(state):
        parts.append("[source_suggestion_allowed: yes]")
    else:
        parts.append("[source_suggestion_allowed: no]")
    if history:
        tail = history[-(KEEP_USER + KEEP_BOT) * 2 :]
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
