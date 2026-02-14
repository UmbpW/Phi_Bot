"""v17 Style Guards: ban meta-phrases, directive routing, dev lexicon."""

import re

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

# v19: debug tags — вычищать перед отправкой
DEBUG_TAG_PATTERN = re.compile(
    r"\[(?:pattern|mode|stage|lens):\s*[^\]]*\]",
    re.IGNORECASE,
)


def apply_style_guards(text: str) -> str:
    """Удаляет BAN_PHRASES, BAN_DIRECTIVE, NO_DEV_LEXICON, debug tags из текста."""
    if not text or not text.strip():
        return text
    text = DEBUG_TAG_PATTERN.sub("", text).strip()
    lines = text.split("\n")
    result = []
    for ln in lines:
        ln_lower = ln.lower().strip()
        if any(phrase in ln_lower for phrase in BAN_PHRASES):
            continue
        if any(phrase in ln_lower for phrase in BAN_DIRECTIVE_PHRASES):
            continue
        if any(word in ln_lower for word in NO_DEV_LEXICON):
            continue
        result.append(ln)
    return "\n".join(result).strip()
