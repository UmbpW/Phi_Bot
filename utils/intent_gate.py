"""First Turn Philosophy Gate: пропуск generic warmup для философских/когнитивных вопросов."""

import re
from typing import Any, Optional

# v19: блокируем philosophy при этих темах (деньги, тревога — в finance/warmup)
PHILOSOPHY_INTENT_BLOCK = ("тревог", "тревож", "неопредел", "деньг", "бедност", "богатств")

# v19: суженный philosophy intent — явные философские темы
PHILOSOPHY_INTENT_KEYS = (
    "нереш",
    "решен",
    "выбор",
    "сомнева",
    "страх",
    "смысл",
    "зачем жить",
    "как философ",
    "философ",
    "стоик",
    "камю",
    "франкл",
    "даос",
    "экзист",
    "конфесс",
    "религ",
    "христиан",
    "ислам",
    "будд",
)

# PATCH 6: turbid/unclear — общие "плохо/устал/пусто" без явной темы
UNCLEAR_MARKERS = [
    "плохо", "устал", "пусто", "не хочу", "ничего не хочу", "ничего не работает",
    "тяжело", "херово", "пипец", "завал", "не могу", "не понимаю", "всё бессмысленно",
    "нет сил", "опустош", "тревож", "страшно", "один", "одна",
]

# BUG2: ориентация не должна быть дефолтом для религиозных тем
# «вер» только как отдельное слово (вера/верой/верю), не «проверка»/«уверенность»
# «верю/вера» — религиозны ТОЛЬКО при наличии религиозного якоря рядом (иначе «верю в себя» = общая фраза)
RELIGION_ANCHORS = (
    "бог", "грех", "молитв", "церков", "ислам", "христиан", "будд", "религ", "конфесс",
)
ORIENTATION_RELIGION_ALWAYS = (
    "бог", "грех", "молитв", "церков", "ислам", "христиан", "будд", "религ", "конфесс",
    "стыд", "вина", "совест",
)
FAITH_MARKERS_NEED_ANCHOR = (" вера", " верой", " веру", " верю", "вера ", "верой ", "веру ", "верю ")

# BUG2: расширены под вера/стыд/вина; «вер» — только целые формы, не «провер»
TOPIC_MARKERS = [
    "деньг", "финанс", "сон", "работ", "отношен", "любов", "смерт", "здоров",
    "тело", "проект", "долг", "кредит", "аренд", "родител", "ребен", "семь",
    "вера", "верой", "веру", "верю", "стыд", "вина", "грех", "совест", "религ", "молитв", "конфликт",
]

# BUG2: ack/close — «понял, спасибо» и т.п., не triage
ACK_CLOSE_PHRASES = (
    "понял", "спасибо", "ясно", "ок всё", "ок, всё", "всё ясно", "принял",
    "хорошо", "благодарю", "ясненько", "окей", "ясно спасибо",
    "понятно", "принято", "супер", "отлично",
)


def is_ack_close_intent(text: str) -> bool:
    """True если короткое подтверждение/закрытие — ack, не orientation."""
    if not text:
        return False
    t = (text or "").strip().lower().replace(",", " ").replace(".", " ")
    t = " ".join(t.split())
    if len(t) > 25:
        return False
    if t in ACK_CLOSE_PHRASES:
        return True
    return any(t.startswith(p) for p in ("понял", "спасибо", "ясно", "принял")) or (
        t.startswith("ок") and len(t) <= 12
    )


def has_religion_in_orientation_context(text: str) -> bool:
    """True если текст про религию/веру — orientation не должен быть дефолтом.
    «Верю/вера» считаются религиозными только при религиозном якоре рядом
    (бог/грех/молитв/церков/ислам/христиан/будд/религ/конфесс). «Верю в себя» → False.
    «Стыд/вина/совест» и якоря — всегда True (проверяем первыми)."""
    if not text:
        return False
    t = (text or "").strip().lower()
    if any(m in t for m in ORIENTATION_RELIGION_ALWAYS):
        return True
    has_anchor = any(a in t for a in RELIGION_ANCHORS)
    has_faith = any(m in t for m in FAITH_MARKERS_NEED_ANCHOR) or t.startswith("вера ") or t.startswith("верой ") or t.startswith("веру ") or t.startswith("верю ")
    return has_faith and has_anchor


def is_unclear_message(text: str) -> bool:
    """True если короткий/расплывчатый вход без конкретной темы → orientation fallback.
    BUG2: ack/close и religion markers — не unclear."""
    if not text:
        return True
    t = (text or "").strip().lower()

    if is_ack_close_intent(text):
        return False
    if has_religion_in_orientation_context(text):
        return False
    if len(t) >= 160:
        return False
    if any(m in t for m in TOPIC_MARKERS):
        return False
    if len(t) <= 70:
        return True
    if any(m in t for m in UNCLEAR_MARKERS):
        return True
    return False


# PATCH 5 + Fix Pack B: expand/explain-запросы
EXPAND_PATTERNS = [
    r"\b(поясни|объясни)\b",
    r"\b(детальнее|подробнее|разверни|раскрой)\b",
    r"\b(не понимаю|не понял|не поняла)\b",
    r"\b(покажи|приведи пример|пример)\b",
    r"\b(как это работает|что ты имеешь в виду)\b",
    r"\b(разбери|разложи)\b",
]

# Fix Pack B: EXPLAIN_REQUEST — расширенный список триггеров
EXPLAIN_REQUEST_TRIGGERS = (
    "объясни", "объясни детальнее", "детальнее", "подробнее", "шире", "разверни",
    "разбери", "разложи", "на кусочки", "поясни", "как это работает",
    "покажи", "покажи оба", "дай пример", "приведи пример", "расшифруй",
    "не понимаю", "не понял", "не поняла", "раскрой",
)


def is_explain_request(text: str) -> bool:
    """Fix Pack B: True если запрос на разъяснение/расширение — explain_mode.
    Расширенный список триггеров с учётом contains."""
    if not text:
        return False
    t = (text or "").strip().lower().replace("  ", " ")
    return any(tr in t for tr in EXPLAIN_REQUEST_TRIGGERS)


def is_expand_request(text: str) -> bool:
    """True если запрос на разъяснение/расширение — explain_mode. Alias для is_explain_request."""
    return is_explain_request(text)


# Паттерн: только выбор/смысл/нерешительность (без тревоги)
HOW_PATTERN = re.compile(
    r".*(как|что)\s+(перестать|побороть|научиться|сделать).*"
    r"(выбор|смысл|сомнева|нереш)",
    re.IGNORECASE | re.DOTALL,
)


def is_philosophy_intent(text: str) -> bool:
    """True если вопрос философский/когнитивный. v19: блок при тревоге/деньгах."""
    if not text or len(text.strip()) < 4:
        return False
    t = (text or "").lower()
    if any(k in t for k in PHILOSOPHY_INTENT_BLOCK):
        return False
    if any(k in t for k in PHILOSOPHY_INTENT_KEYS):
        return True
    if HOW_PATTERN.search(t):
        return True
    return False


def should_skip_warmup_first_turn(
    state: Optional[dict],
    user_text: str,
    history_count: int = 0,
    stage: Optional[str] = None,
) -> bool:
    """True если первый ход + философский intent — пропустить warmup, дать philosophy-first.
    Safety/crisis не трогаем (вызывающий код должен проверить safety до этого)."""
    if not state:
        return False
    if not is_philosophy_intent(user_text):
        return False
    # Первый ход: turn_index 0 или пустая история
    turn = state.get("turn_index", 0)
    is_first = turn == 0 or history_count == 0
    if not is_first:
        return False
    # Stage warmup или ещё не задан
    st = stage or state.get("stage", "warmup")
    return st in (None, "warmup")
