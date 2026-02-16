# intent_topic_v2.py — PATCH E + E1.1: Topic Gate V2
import re
from functools import lru_cache

TOPIC_PREFIXES = [
    "будд", "стоик", "экзист", "аристот", "сократ", "платон",
    "ницш", "конфуц", "кант", "гегел", "хайдег", "камю",
]

# E1.1: no risky single-letter tokens like "я"
TOPIC_NOUNS = [
    "философи", "бог", "смерт", "дружб", "любов", "деньг", "морал",
    "смысл", "страдан", "страх", "счаст", "добро", "зло",
]

TOPIC_PATTERNS = [
    r"\bкакие бывают\b\s+\w+",
    r"\bкакие есть\b.*философи",
    r"\bчто такое\b\s+\w+",
    r"\bрасскажи(те)?\b\s+про",
    r"\bкак\b\s+\w+\s+(смотрит|понимает|объясняет)",
    r"\bкак\b\s+в\s+\w+",
    r"\bсуществует ли\b",
    r"\bесть ли\b\s+\w+",
    r"\bвзгляд\b\s+\w+\s+на",
]


def _normalize(text: str) -> str:
    """E1.1: unify with P1-style normalization."""
    t = (text or "").lower().replace("ё", "е")
    t = re.sub(r"\s+", " ", t).strip()
    return t


@lru_cache(maxsize=2048)
def topic_score(text: str) -> int:
    t = _normalize(text)
    score = 0

    for p in TOPIC_PREFIXES:
        if p in t:
            score += 2

    for n in TOPIC_NOUNS:
        if n in t:
            score += 1

    for pat in TOPIC_PATTERNS:
        if re.search(pat, t):
            score += 3

    return score


def is_topic_high(text: str) -> bool:
    return topic_score(text) >= 5


def is_topic_mid(text: str) -> bool:
    s = topic_score(text)
    return 3 <= s < 5
