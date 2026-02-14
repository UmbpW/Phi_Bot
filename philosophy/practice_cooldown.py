"""v17 Practice Cooldown: не давать практику каждый ход."""

import re

# Фразы-директивы практики (удалять при forbid_practice)
PRACTICE_PATTERNS = (
    r"Попробуй выписать[^.]*\.",  # "Попробуй выписать 2 пункта: влияю / не влияю."
    r"Отметь один пункт[^.]*\.",   # "Отметь один пункт, где действие возможно сегодня."
    r"Микро-практика[^.]*\.",
)
# Целые строки с практикой (построчно)
PRACTICE_LINE_PREFIXES = (
    "попробуй выписать",
    "отметь один пункт",
    "микро-практика",
)


def strip_practice_content(text: str) -> str:
    """Удаляет параграфы/строки с практикой при cooldown."""
    if not text or not text.strip():
        return text
    lines = text.split("\n")
    result = []
    for ln in lines:
        ln_lower = ln.lower().strip()
        if any(ln_lower.startswith(prefix) for prefix in PRACTICE_LINE_PREFIXES):
            continue
        if any(re.search(pat, ln, re.I) for pat in PRACTICE_PATTERNS):
            continue
        result.append(ln)
    return "\n".join(result).strip()


def contains_practice(text: str) -> bool:
    """True если в тексте есть практика."""
    if not text:
        return False
    t = text.lower()
    return any(p in t for p in ("попробуй выписать", "отметь один пункт", "микро-практика"))


def tick_practice_cooldown(state: dict) -> None:
    """Уменьшить practice_cooldown_turns на 1 (мин 0)."""
    v = state.get("practice_cooldown_turns", 0)
    if v > 0:
        state["practice_cooldown_turns"] = v - 1


COOLDOWN_AFTER_PRACTICE = 3
