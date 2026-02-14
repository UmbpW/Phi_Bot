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

# v19: debug tags — вычищать перед отправкой
DEBUG_TAG_PATTERN = re.compile(
    r"\[(?:pattern|mode|stage|lens):\s*[^\]]*\]",
    re.IGNORECASE,
)


def apply_style_guards(text: str, ban_empathy_openers: bool = False) -> str:
    """Удаляет BAN_PHRASES, BAN_DIRECTIVE, NO_DEV_LEXICON, debug tags, meta tail из текста."""
    if not text or not text.strip():
        return text
    original = text
    text = META_TAIL_RE.sub("", text)
    text = DEBUG_TAG_PATTERN.sub("", text).strip()
    lines = text.split("\n")
    result = []
    for ln in lines:
        ln_lower = ln.lower().strip()
        if ban_empathy_openers and any(ln_lower.startswith(p) for p in EMPATHY_OPENER_STARTS):
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
