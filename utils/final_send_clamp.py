"""v21.1 Final send clamp: ban-opener + meta-tail hard drop. Последний шаг перед отправкой.
v21.2: looks_incomplete + add_closing_sentence (completion guard)."""

import random
import re


def _split_sentences(text: str) -> list:
    """Разбить на предложения по . ! ?"""
    if not text or not text.strip():
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


# v21.1: ban-opener — первое предложение (financial_rhythm / philosophy_pipeline / answer-first)
BAN_OPENER_STARTS = ("похоже", "похоже,", "похоже что", "кажется", "кажется,", "с таким")

# v21.1: meta-tail hard drop — предложения с этими фразами удаляются целиком
META_TAIL_HARD_PHRASES = (
    "если хочешь",
    "давай продолжим",
    "продолжим с",
    "можем разобрать",
    "хочешь — разберём",
    "хочешь разберём",
)


def final_send_clamp(
    text: str,
    mode_tag: str | None = None,
    stage: str = "",
    answer_first_required: bool = False,
    philosophy_pipeline: bool = False,
) -> str:
    """Финальный clamp перед отправкой. Вызывать последним, после agency/option_close.

    A1) Ban-opener (sentence-level): при mode in (financial_rhythm, philosophy_pipeline) или answer_first
        — удалить первое предложение, если начинается с BAN_OPENER_STARTS.
    A2) Meta-tail hard drop: удалить целиком предложения, содержащие META_TAIL_HARD_PHRASES.
    """
    if not text or not text.strip():
        return text

    sentences = _split_sentences(text)
    if not sentences:
        return text

    # A1) Ban-opener — только для financial/philosophy/answer-first
    apply_ban_opener = (
        mode_tag == "financial_rhythm"
        or philosophy_pipeline
        or answer_first_required
    )
    if apply_ban_opener and sentences:
        first_lower = sentences[0].lower().strip()
        if any(first_lower.startswith(p) for p in BAN_OPENER_STARTS):
            sentences = sentences[1:]

    # A2) Meta-tail hard drop — всегда, в любом месте ответа
    sentences = [s for s in sentences if not any(p in s.lower() for p in META_TAIL_HARD_PHRASES)]

    if not sentences:
        return text  # fallback: не обнулять ответ

    return " ".join(sentences).strip()


# v21.2: completion guard — защита от незавершённых ответов
CLOSING_POOL = [
    "Иногда достаточно на сегодня вернуть себе один управляемый участок — чтобы снова почувствовать почву под ногами.",
    "Смысл сейчас не в том, чтобы решить всё разом, а в том, чтобы вернуть себе малую устойчивость в пределах доступного.",
    "Когда всё кажется монолитом, полезно разделить его на части и начать с той, которая поддаётся.",
]


def looks_incomplete(text: str) -> bool:
    """Проверяет, выглядит ли ответ незавершённым (обрубленным)."""
    if not text:
        return True
    t = text.strip()
    if len(t) < 240:  # коротко для "полного вопроса"
        return True
    if t[-1] not in ".!?…":
        return True
    # защита от "обрубка": последняя строка слишком короткая
    last = t.split("\n")[-1].strip() if "\n" in t else t
    if len(last) < 18 and t[-1] != "?":
        return True
    return False


def add_closing_sentence(text: str) -> str:
    """Добавляет нейтральное философское закрытие без коуч-лексики и meta-навигации."""
    return text.rstrip() + "\n\n" + random.choice(CLOSING_POOL)
