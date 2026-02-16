"""v21.1 Final send clamp: ban-opener + meta-tail hard drop. Последний шаг перед отправкой.
v21.2: looks_incomplete + add_closing_sentence (completion guard)."""

import random
import re
from typing import Optional


def _split_sentences(text: str) -> list:
    """Разбить на предложения по . ! ?"""
    if not text or not text.strip():
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


# v21.1: ban-opener — первое предложение (financial_rhythm / philosophy_pipeline / answer-first)
# v21.5: + meta-подводки «Когда X — легко Y» (не связаны с вопросом)
BAN_OPENER_STARTS = (
    "похоже", "похоже,", "похоже что", "кажется", "кажется,", "с таким",
    "когда ответов много", "когда внутри нет ясности", "когда нет ясности",
    "когда внутри много", "когда легко утонуть", "когда легко запутаться",
)

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
    mode_tag: Optional[str] = None,
    stage: str = "",
    answer_first_required: bool = False,
    philosophy_pipeline: bool = False,
    explain_mode: bool = False,
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

    # A1) Ban-opener — только для financial/philosophy/answer-first/explain
    apply_ban_opener = (
        mode_tag == "financial_rhythm"
        or philosophy_pipeline
        or answer_first_required
        or explain_mode
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


# FIX B2: висящие конструкции — обрывы на : ; — , ... …
HANGING_ENDINGS = (":", ";", "—", ",", "...", "…")
HANGING_PHRASES_TAIL = (
    "помогает не", "рождается не", "уверенность здесь", "иногда",
    "обычно", "это потому что", "злость обычно", "так как", "потому что", "когда",
)
HANGING_PHRASES_START = (
    "запись помогает не", "иногда мысли не", "уверенность здесь",
    "вариант без", "первый —", "второй —",
)


def looks_incomplete(text: str) -> bool:
    """Проверяет, выглядит ли ответ незавершённым (обрубленным).
    FIX B2: + висящие конструкции, обрывы на : ; — , фразы-обрывки."""
    if not text:
        return True
    t = text.strip()
    if len(t) < 240:  # коротко для "полного вопроса"
        return True
    if t[-1] not in ".!?…":
        return True
    # висящие окончания
    if any(t.rstrip().endswith(e) for e in HANGING_ENDINGS):
        return True
    last_80 = t[-80:].lower()
    if any(last_80.endswith(p) or p in last_80[-40:] for p in HANGING_PHRASES_TAIL):
        return True
    # защита от "обрубка": последняя строка слишком короткая
    last = t.split("\n")[-1].strip() if "\n" in t else t
    if len(last) < 18 and t[-1] != "?":
        return True
    return False


def _strip_hanging_tail(text: str) -> str:
    """Удалить висящий хвост до последнего полного предложения."""
    s = (text or "").strip()
    if not s:
        return s
    parts = re.split(r"(?<=[.!?…])\s+", s)
    if len(parts) <= 1:
        # нет полных предложений — вернуть всё кроме висящего конца
        for end in HANGING_ENDINGS:
            if s.rstrip().endswith(end):
                # отрезать от последнего полного слова
                words = s.rsplit(None, 1)
                if len(words) >= 2:
                    return words[0].rstrip(":;,—…")
        return s
    return " ".join(parts[:-1]).strip()


def add_closing_sentence(text: str) -> str:
    """Добавляет нейтральное философское закрытие без коуч-лексики и meta-навигации.
    FIX B2: при висящем хвосте сначала отрезать обрыв."""
    s = (text or "").strip()
    if not s:
        return text
    if s[-1] in HANGING_ENDINGS or any(s.lower()[-50:].strip().endswith(p) for p in HANGING_PHRASES_TAIL):
        s = _strip_hanging_tail(s)
    return (s.rstrip() + "\n\n" + random.choice(CLOSING_POOL)).strip()


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
    mode_tag: Optional[str] = None,
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


# PATCH 3: Completion Guard — мета-фразы, диагностика, незакрытая подводка
META_TAIL_TRIGGERS = [
    "важно понять",
    "нужно понять",
    "чтобы не давать",
    "чтобы не гадать",
    "давай уточним",
    "уточню одно",
    "уточни, пожалуйста",
    "если хочешь — продолжим",
    "если хочешь продолжим",
    "разобрать глубже или упростить",
    "смотреть рамку или практику",
]

DIAGNOSTIC_TAIL_TRIGGERS = [
    "сейчас звучит так",
    "похоже, сейчас",
    "похоже сейчас",
    "выглядит так",
    "будто страдает",
    "и это изматывает",
    "но сейчас",
]

FORK_QUESTION_POOL_P3 = [
    "Что в этом сейчас главнее: страх, что поток может сорваться, или раздражение от непредсказуемых дыр и трат?",
    "Это больше про непредсказуемость будущего или про ощущение, что контроль ускользает?",
    "Если выбрать одну точку: тебя сильнее держит страх потери опоры или усталость от постоянной необходимости «добывать»?",
]

CLOSE_SENTENCE_POOL_P3 = [
    "На этом месте достаточно просто увидеть узел яснее — без рывка и без давления.",
    "Иногда уже одно различение того, что именно болит, возвращает немного опоры.",
    "Пока не нужно решать всё сразу: важно, что ты уже описал структуру проблемы, а не просто чувство.",
]


def _tail_p3(text: str, n: int = 280) -> str:
    t = (text or "").strip().lower()
    return t[-n:] if len(t) > n else t


def _ends_with_trigger_p3(text: str) -> bool:
    tail = _tail_p3(text)
    return any(x in tail for x in META_TAIL_TRIGGERS) or any(x in tail for x in DIAGNOSTIC_TAIL_TRIGGERS)


def _strip_last_sentence_p3(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return s
    parts = re.split(r"(?<=[.!?…])\s+", s)
    if len(parts) <= 1:
        return s
    return " ".join(parts[:-1]).strip()


def completion_guard(text: str, max_questions: int = 1, user_text: Optional[str] = None) -> str:
    """PATCH 3 + FIX B2: мета-фразы, диагностика, висящие конструкции → repair или close."""
    s = (text or "").strip()
    if not s:
        return s

    # FIX B2: висящие конструкции и обрывы — strip + add closing
    if looks_incomplete(s):
        base = _strip_hanging_tail(s)
        if len(base) < 100:
            base = s
        return (base.rstrip() + "\n\n" + random.choice(CLOSING_POOL)).strip()

    if not _ends_with_trigger_p3(s):
        return s

    base = _strip_last_sentence_p3(s)

    if len(base) < 200:
        base = s

    qn = (base or "").count("?")
    if qn < max_questions:
        return (base + "\n\n" + random.choice(FORK_QUESTION_POOL_P3)).strip()
    return (base + "\n\n" + random.choice(CLOSE_SENTENCE_POOL_P3)).strip()
