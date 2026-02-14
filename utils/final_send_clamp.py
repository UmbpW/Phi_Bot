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


# v21.4: meta-tail-to-fork/close — замена хвоста мета-фраз на fork или закрытие
META_TAIL_ENDINGS = (
    "чтобы не давать пустых советов",
    "важно понять",
    "нужно понять",
    "хочу понять",
    "давай уточним",
    "уточни, пожалуйста",
    "расскажи подробнее",
)

FINANCE_CLOSE_POOL = [
    "Иногда достаточно на сегодня вернуть себе один управляемый участок — чтобы снова почувствовать почву под ногами.",
    "Смысл сейчас не в том, чтобы решить всё разом, а в том, чтобы вернуть себе малую устойчивость в пределах доступного.",
    "Когда всё кажется монолитом, полезно разделить его на части и начать с той, которая поддаётся.",
]

GENERAL_FORK_POOL = [
    "Что сейчас сильнее всего тянет вниз: усталость/выгорание, здоровье, или ощущение, что всё разваливается сразу?",
    "Это больше про нехватку сил или про то, что не видно направления?",
    "Главнее сейчас вернуть силы или вернуть ясность?",
]


def ends_with_meta_tail(text: str) -> bool:
    """Проверяет, заканчивается ли ответ мета-фразой в последних ~220 символах."""
    t = (text or "").strip().lower()
    if not t:
        return False
    tail = t[-220:]
    return any(x in tail for x in META_TAIL_ENDINGS)


def strip_last_meta_sentence(text: str) -> str:
    """Убрать последнее предложение (грубое удаление мета-хвоста)."""
    s = (text or "").strip()
    parts = re.split(r"(?<=[.!?…])\s+", s)
    if len(parts) <= 1:
        return s
    return " ".join(parts[:-1]).strip()


def meta_tail_to_fork_or_close(
    text: str,
    mode_tag: str | None = None,
    max_questions: int = 1,
) -> str:
    """Если ответ заканчивается мета-фразой — заменить на fork или закрытие.
    Fork если вопросов ещё нет, иначе — закрывающую фразу."""
    if not text or not text.strip():
        return text
    if not ends_with_meta_tail(text):
        return text

    base = strip_last_meta_sentence(text)
    q_count = base.count("?")
    if q_count < max_questions:
        return (base + "\n\n" + random.choice(GENERAL_FORK_POOL)).strip()
    return (base + "\n\n" + random.choice(FINANCE_CLOSE_POOL)).strip()
