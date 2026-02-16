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
# v21.1: добавлены похоже/кажется для final_send_clamp (ban-opener)
# v21.5: + meta-подводки «Когда X — легко Y» (не связаны с вопросом)
EMPATHY_OPENER_STARTS_ANSWER_FIRST = (
    "с таким", "это тяжело", "это выматывает", "похоже тебе", "похоже", "кажется", "когда тревога",
    "когда ответов много", "когда внутри нет ясности", "когда нет ясности",
    "когда внутри много", "когда легко утонуть", "когда легко запутаться",
)

# v21: meta tail — предложения с этими фразами удаляются целиком
# v21.1: расширен список (полный в final_send_clamp)
META_TAIL_SENTENCE_PHRASES = (
    "если хочешь", "давай продолжим", "продолжим с", "смотреть", "разобрать глубже", "выберем направление",
    "можем разобрать", "хочешь — разберём", "хочешь разберём",
)

# FIX-6: Philosophy voice softener — методичные фразы → живые
STYLE_REWRITE = {
    "Есть оптика": "Можно посмотреть так",
    "Есть рамка": "Один из полезных разворотов здесь",
    "В философской линии": "Если смотреть через одну философскую линию",
}


def apply_style_rewrite(text: str) -> str:
    """FIX-6: замена методичных фраз на более живые."""
    if not text or not text.strip():
        return text
    out = text
    for old, new in STYLE_REWRITE.items():
        out = out.replace(old, new)
    return out


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


# PATCH 4: meta tail strip + question clamp
META_TAIL_PATTERNS = [
    r"\bесли хочешь\b.*$",
    r"\bесли хотите\b.*$",
    r"\bможем продолжить\b.*$",
    r"\bдавай продолжим\b.*$",
    r"\bразобрать глубже или упростить\b.*$",
    r"\bразобрать глубже\b.*$",
    r"\bупростить\b.*$",
    r"\bсмотреть рамку или практику\b.*$",
    r"\bрамку или практику\b.*$",
    r"\bпродолжим про причины или про следующий шаг\b.*$",
    r"\bпродолжим с одного примера\b.*$",
    r"\bвыберем направление\b.*$",
    r"\bчтобы не давать пустых советов\b.*$",
    r"\bважно понять\b.*$",
]


def strip_meta_tail(text: str) -> str:
    """Удаляет мета-хвосты в последних 500 символах."""
    s = (text or "").strip()
    if not s:
        return s

    head = s[:-500] if len(s) > 500 else ""
    tail = s[-500:] if len(s) > 500 else s

    for pat in META_TAIL_PATTERNS:
        tail = re.sub(pat, "", tail, flags=re.IGNORECASE | re.DOTALL).strip()

    out = (head + tail).strip()
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def _split_sentences_for_clamp(text: str) -> list:
    """Грубо: делим по . ! ? … + переносы."""
    s = (text or "").strip()
    if not s:
        return []
    parts = re.split(r"(?<=[.!?…])\s+", s)
    return [p.strip() for p in parts if p.strip()]


def clamp_questions(text: str, max_questions: int = 1) -> str:
    """Максимум max_questions вопросительных предложений; лишние — в утверждения."""
    s = (text or "").strip()
    if not s:
        return s

    qcount = s.count("?")
    if qcount <= max_questions:
        return s

    sentences = _split_sentences_for_clamp(s)
    kept = []
    questions_kept = 0

    for sent in sentences:
        is_q = "?" in sent
        if is_q:
            if questions_kept < max_questions:
                kept.append(sent)
                questions_kept += 1
            else:
                replaced = sent.replace("?", "").strip()
                replaced = re.sub(r"^(и\s+)?(еще|ещё)\s+", "", replaced, flags=re.IGNORECASE).strip()
                if replaced:
                    kept.append(replaced + ".")
        else:
            kept.append(sent)

    out = " ".join(kept).strip()
    out = re.sub(r"\s+\.", ".", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out
