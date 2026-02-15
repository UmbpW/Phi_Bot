"""First Turn Philosophy Gate: пропуск generic warmup для философских/когнитивных вопросов."""

import re
from typing import Any, Optional

# v19: блокируем philosophy при этих темах (деньги, тревога — в finance/warmup)
PHILOSOPHY_INTENT_BLOCK = ("тревог", "тревож", "неопредел", "деньг", "бедност", "богатств")

# v19: суженный philosophy intent — явные философские темы
PHILOSOPHY_INTENT_KEYS = (
    "нереш",
    "решен",
    "выбор",
    "сомнева",
    "страх",
    "смысл",
    "зачем жить",
    "как философ",
    "философ",
    "стоик",
    "камю",
    "франкл",
    "даос",
    "экзист",
    "конфесс",
    "религ",
    "христиан",
    "ислам",
    "будд",
)

# PATCH 5: expand/explain-запросы
EXPAND_PATTERNS = [
    r"\b(поясни|объясни)\b",
    r"\b(детальнее|подробнее|разверни|раскрой)\b",
    r"\b(не понимаю|не понял|не поняла)\b",
    r"\b(покажи|приведи пример|пример)\b",
    r"\b(как это работает|что ты имеешь в виду)\b",
    r"\b(разбери|разложи)\b",
]


def is_expand_request(text: str) -> bool:
    """True если запрос на разъяснение/расширение — explain_mode."""
    if not text:
        return False
    t = (text or "").strip().lower()
    return any(re.search(p, t) for p in EXPAND_PATTERNS)


# Паттерн: только выбор/смысл/нерешительность (без тревоги)
HOW_PATTERN = re.compile(
    r".*(как|что)\s+(перестать|побороть|научиться|сделать).*"
    r"(выбор|смысл|сомнева|нереш)",
    re.IGNORECASE | re.DOTALL,
)


def is_philosophy_intent(text: str) -> bool:
    """True если вопрос философский/когнитивный. v19: блок при тревоге/деньгах."""
    if not text or len(text.strip()) < 4:
        return False
    t = (text or "").lower()
    if any(k in t for k in PHILOSOPHY_INTENT_BLOCK):
        return False
    if any(k in t for k in PHILOSOPHY_INTENT_KEYS):
        return True
    if HOW_PATTERN.search(t):
        return True
    return False


def should_skip_warmup_first_turn(
    state: Optional[dict],
    user_text: str,
    history_count: int = 0,
    stage: Optional[str] = None,
) -> bool:
    """True если первый ход + философский intent — пропустить warmup, дать philosophy-first.
    Safety/crisis не трогаем (вызывающий код должен проверить safety до этого)."""
    if not state:
        return False
    if not is_philosophy_intent(user_text):
        return False
    # Первый ход: turn_index 0 или пустая история
    turn = state.get("turn_index", 0)
    is_first = turn == 0 or history_count == 0
    if not is_first:
        return False
    # Stage warmup или ещё не задан
    st = stage or state.get("stage", "warmup")
    return st in (None, "warmup")
