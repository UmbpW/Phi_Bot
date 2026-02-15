"""Автоматические проверки UX-регрессий для eval."""

import re
from typing import Optional


def is_too_short(text: str, min_len: int = 350) -> bool:
    """Ответ слишком короткий."""
    if not text:
        return True
    return len((text or "").strip()) < min_len


def has_meta_tail(text: str) -> bool:
    """Содержит тех.метки [mode: [pattern:."""
    if not text:
        return False
    t = (text or "").strip()
    return "[mode:" in t or "[pattern:" in t or "[telemetry]" in t


def repeats_user_opening(user_text: str, bot_text: str) -> bool:
    """Бот перефразирует первые слова пользователя в начале ответа."""
    if not user_text or not bot_text:
        return False
    user_words = set((user_text or "").lower().split()[:5])
    bot_first = (bot_text or "").strip().lower().split()[:8]
    overlap = sum(1 for w in bot_first if len(w) > 3 and w in user_words)
    return overlap >= 3


def looks_like_warmup_triage(text: str) -> bool:
    """Похоже на triage «состояние/смысл/опора» когда не должен."""
    if not text:
        return False
    t = (text or "").lower()
    markers = ["три зоны", "состояние", "смысл", "опора", "выбери угол", "напиши одно слово"]
    return sum(1 for m in markers if m in t) >= 2


def looks_like_context_drop(prev_user: str, bot_text: str) -> bool:
    """Бот похоже потерял контекст — generic ответ на конкретный вопрос."""
    if not prev_user or not bot_text:
        return False
    prev_lower = (prev_user or "").lower()
    bot_lower = (bot_text or "").lower()
    if len(prev_user.strip()) < 30:
        return False
    context_words = [w for w in prev_lower.split() if len(w) > 4][:5]
    matches = sum(1 for w in context_words if w in bot_lower)
    return matches == 0 and len(prev_user) > 50


def looks_incomplete(text: str) -> bool:
    """Заканчивается обрывом без точки."""
    if not text:
        return True
    t = (text or "").strip()
    if not t:
        return True
    incomplete_endings = ("иногда", "обычно", "это потому что", "злость обычно", "так как", "потому что", "когда")
    last_50 = t[-50:].lower()
    if t[-1] in ".!?":
        return False
    return any(last_50.endswith(e) or e in last_50[-20:] for e in incomplete_endings)


def run_checks(user_text: str, bot_text: str, prev_user: Optional[str] = None) -> dict:
    """Прогон всех проверок. Возвращает счётчики."""
    result = {
        "too_short": is_too_short(bot_text),
        "meta_tail": has_meta_tail(bot_text),
        "repeats_opening": repeats_user_opening(user_text, bot_text) if user_text else False,
        "warmup_triage": looks_like_warmup_triage(bot_text),
        "context_drop": looks_like_context_drop(prev_user or "", bot_text) if prev_user else False,
        "incomplete": looks_incomplete(bot_text),
    }
    return result
