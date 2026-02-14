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
    "идем по линии",
    "идём по линии",
    "вариант a",
    "вариант b",
    "вариант c",
    "вариант a/b/c",
    "сейчас делаем так",
)

NO_DEV_LEXICON = ("картечь",)


def apply_style_guards(text: str) -> str:
    """Удаляет BAN_PHRASES, BAN_DIRECTIVE, NO_DEV_LEXICON из текста."""
    if not text or not text.strip():
        return text
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
