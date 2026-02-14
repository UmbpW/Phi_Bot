"""Output sanitizer: удаляет debug-теги из финального текста пользователю."""

import re

DEBUG_TAG_PATTERN = re.compile(
    r"\[(pattern|mode|stage|lens|debug)[^\]]*\]",
    re.IGNORECASE,
)


def sanitize_output(text: str) -> str:
    """Удаляет служебные debug-теги из текста.

    Test cases:
        Вход:  "Текст\\n[pattern: W1]\\n[mode: warmup | stage: warmup]"
        Выход: "Текст"

        Вход:  "Ответ [pattern: G2] продолжение"
        Выход: "Ответ продолжение"
    """
    if not text:
        return text

    # удалить inline debug теги
    text = DEBUG_TAG_PATTERN.sub("", text)

    # схлопнуть двойные пробелы (не newlines)
    text = re.sub(r" +", " ", text)

    # удалить строки, которые стали пустыми после удаления
    lines = [ln.rstrip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln.strip() != ""]

    return "\n".join(lines).strip()
