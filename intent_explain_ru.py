# intent_explain_ru.py — PATCH F: Explain Expander
import re
from functools import lru_cache

EXPLAIN_MARKERS = [
    "объясни", "поясни", "детальнее", "подробнее", "разверни",
    "разбери", "на кусочки", "расшифруй", "что ты имеешь в виду",
    "почему", "приведи пример", "пример", "шире", "расширь",
    "не понимаю", "я не понимаю", "уточни", "раскрой мысль",
]

EXPLAIN_PATTERNS = [
    r"\bобъясни\b",
    r"\bпоясни\b",
    r"\bдетальн(ее|ей)\b",
    r"\bподробн(ее|ей)\b",
    r"\bразверн(и|и-ка)\b",
    r"\bразбер(и|и-ка)\b",
    r"\bпочему\b",
    r"\bне понимаю\b",
    r"\bчто ты имеешь в виду\b",
    r"\bприведи пример\b|\bпример\b",
    r"\bрасшир(ь|ь-ка)\b|\bшире\b",
]


def _norm(t: str) -> str:
    t = (t or "").lower().replace("ё", "е")
    t = re.sub(r"\s+", " ", t).strip()
    return t


@lru_cache(maxsize=2048)
def explain_score(text: str) -> int:
    t = _norm(text)
    score = 0

    for m in EXPLAIN_MARKERS:
        if m in t:
            score += 1

    for pat in EXPLAIN_PATTERNS:
        if re.search(pat, t):
            score += 2

    # bonus if user explicitly asks to expand/clarify
    if "объясни" in t or "поясни" in t or "детальнее" in t or "подробнее" in t:
        score += 2

    return score


def detect_explain_intent(text: str) -> bool:
    return explain_score(text) >= 3
