"""v17 Style Guards: ban meta-phrases, directive routing, dev lexicon."""

import re

# v20.2: meta tail killer — вырезать "если хочешь...", "давай продолжим...", "продолжим с..."
META_TAIL_RE = re.compile(
    r"(если хочешь[^.\n]*\.)|(давай продолжим[^.\n]*\.)|(продолжим с[^.\n]*\.)",
    re.IGNORECASE,
)

BAN_PHRASES = (
    "философски",
    "с философской точки зрения",
    "философский критерий",
    "философская оптика",
    "полезен разворот",
)

BAN_DIRECTIVE_PHRASES = (
    "давай выберем путь",
    "выберем направление",
    "мне важно выбрать",
    "идем по линии",
    "идём по линии",
    "вариант a",
    "вариант b",
    "вариант c",
    "вариант a/b/c",
    "сейчас делаем так",
)

NO_DEV_LEXICON = ("картечь",)

# v20.2: empathy openers — запрет в finance/philosophy modes
EMPATHY_OPENER_STARTS = ("с таким", "когда тревога", "это выматывает")

# v21: answer-first — расширенный список empathy openers
EMPATHY_OPENER_STARTS_ANSWER_FIRST = ("с таким", "это тяжело", "это выматывает", "похоже тебе", "когда тревога")

# v21: meta tail — предложения с этими фразами удаляются целиком
META_TAIL_SENTENCE_PHRASES = ("если хочешь", "давай продолжим", "смотреть", "разобрать глубже", "выберем направление")

# v19: debug tags — вычищать перед отправкой
DEBUG_TAG_PATTERN = re.compile(
    r"\[(?:pattern|mode|stage|lens):\s*[^\]]*\]",
    re.IGNORECASE,
)


def _split_sentences(text: str) -> list:
    """Разбить на предложения по . ! ?"""
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def apply_style_guards(text: str, ban_empathy_openers: bool = False, answer_first: bool = False) -> str:
    """Удаляет BAN_PHRASES, BAN_DIRECTIVE, NO_DEV_LEXICON, debug tags, meta tail.
    v21 answer_first: meta tail sentence filter, extended empathy openers."""
    if not text or not text.strip():
        return text
    original = text
    text = META_TAIL_RE.sub("", text)
    text = DEBUG_TAG_PATTERN.sub("", text).strip()
    # v21: meta tail sentence filter — удалить предложения с навигацией
    if answer_first:
        sentences = _split_sentences(text)
        sentences = [s for s in sentences if not any(p in s.lower() for p in META_TAIL_SENTENCE_PHRASES)]
        text = " ".join(sentences).strip()
        # v21: empathy opener — удалить первое предложение, если начинается с empathy
        if sentences:
            first_lower = sentences[0].lower().strip()
            if any(first_lower.startswith(p) for p in EMPATHY_OPENER_STARTS_ANSWER_FIRST):
                sentences = sentences[1:]
                text = " ".join(sentences).strip()
    lines = text.split("\n")
    result = []
    opener_list = EMPATHY_OPENER_STARTS_ANSWER_FIRST if answer_first else EMPATHY_OPENER_STARTS
    for ln in lines:
        ln_lower = ln.lower().strip()
        if ban_empathy_openers and any(ln_lower.startswith(p) for p in opener_list):
            continue
        if any(phrase in ln_lower for phrase in BAN_PHRASES):
            continue
        if any(phrase in ln_lower for phrase in BAN_DIRECTIVE_PHRASES):
            continue
        if any(word in ln_lower for word in NO_DEV_LEXICON):
            continue
        result.append(ln)
    if len(result) == 0:
        return original
    return "\n".join(result).strip()
