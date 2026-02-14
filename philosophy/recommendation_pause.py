"""v17.1 Recommendation Pause Rule: при рекомендации источника — без вопросов, без практики, без fork."""

import re

# Маркеры рекомендации источника
RECO_MARKERS = (
    "книга",
    "статья",
    "почитать",
    "автор",
    "издание",
)

# Авторы (часто в рекомендациях)
AUTHOR_MARKERS = ("ирвин", "ирвин у", "пильюччи", "пиглюччи", "холидей")

# Мягкая завершающая строка без вопроса
SOFT_CLOSING_LINE = "Если откликнется — можно просто походить с этой мыслью немного."


def detect_recommendation(text: str, source_recommendation_flag: bool = False) -> bool:
    """True если в тексте есть рекомендация источника (книга/статья/автор)."""
    if source_recommendation_flag:
        return True
    if not text or len(text.strip()) < 10:
        return False
    t = text.lower()
    if any(m in t for m in RECO_MARKERS):
        return True
    if any(m in t for m in AUTHOR_MARKERS):
        return True
    return False


def _remove_question_sentences(text: str) -> str:
    """Удаляет все предложения, заканчивающиеся на ? или ？."""
    if not text:
        return text
    # Разбиваем на предложения (по . ! ?)
    sentences = re.split(r"(?<=[.!?？])\s+", text)
    result = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if s.endswith("?") or s.endswith("？"):
            continue
        result.append(s)
    return " ".join(result).strip()


def _ends_abruptly(text: str) -> bool:
    """True если текст заканчивается слишком резко (короткое предложение, союз в конце)."""
    if not text or len(text) < 20:
        return True
    # Заканчивается на союз/частицу
    if re.search(r"\s+[иано]\s*$", text, re.I):
        return True
    last_sentence = text.strip().split(".")[-1].strip().split("!")[-1].strip()
    if len(last_sentence) < 15:
        return True
    return False


def apply_recommendation_pause(text: str) -> str:
    """Удаляет вопросы, добавляет мягкую завершающую строку при необходимости."""
    if not text or not text.strip():
        return text
    result = _remove_question_sentences(text)
    if not result:
        return text
    result = re.sub(r"\s+", " ", result).strip()
    if _ends_abruptly(result):
        result = result.rstrip(".,;: ") + ".\n\n" + SOFT_CLOSING_LINE
    return result
