"""First Turn Philosophy Gate: пропуск generic warmup для философских/когнитивных вопросов."""

import re
from typing import Any, Optional

# Ключи философского/когнитивного intent (RU, case-insensitive)
PHILOSOPHY_INTENT_KEYS = (
    "нереш",
    "решен",
    "выбор",
    "сомнева",
    "страх",
    "тревог",
    "тревож",
    "неопредел",
    "смысл",
    "зачем жить",
    "как философ",
    "философ",
    "стоик",
    "камю",
    "франкл",
    "даос",
    "экзист",
    "деньг",
    "бедност",
    "богатств",
    "конфесс",
    "религ",
    "христиан",
    "ислам",
    "будд",
)

# Паттерн: вопрос с "как" + (перестать/побороть/научиться) в контексте выбора/страха
HOW_PATTERN = re.compile(
    r".*(как|что)\s+(перестать|побороть|научиться|сделать).*"
    r"(выбор|страх|смысл|тревог|тревож|сомнева|нереш)",
    re.IGNORECASE | re.DOTALL,
)


def is_philosophy_intent(text: str) -> bool:
    """True если вопрос философский/когнитивный (решение, смысл, страх, конфессии и т.д.)."""
    if not text or len(text.strip()) < 4:
        return False
    t = (text or "").lower()
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
