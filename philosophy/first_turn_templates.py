"""First Turn Philosophy Gate: шаблоны ответа первого хода (answer-first, без generic warmup)."""

from typing import Optional, Tuple

# Religion/confession: topic question vs personal confession (PATCH: не MONEY для «расскажи про Бога»)
RELIGION_MARKERS = (
    "бог", "бога", "боге", "богом", "религ", "вера", "вере", "верю", "атеизм", "теизм", "деизм",
    "конфесс", "церков", "христиан", "ислам", "коран", "иудаизм", "тора",
    "будд", "будда", "буддизм", "дхарма", "карма", "нирван", "сансар",
    "грех", "молитв", "покаян", "рай", "ад",
)
TOPIC_ASK_MARKERS = (
    "расскажи", "объясни", "как", "почему", "есть ли", "существует ли",
    "позиция", "взгляд", "что думают",
)
PERSONAL_MARKERS = (
    "я ", "мне", "у меня", "со мной", "моя ", "мой ", "стыд", "вина",
    "страшно", "пугает", "сомневаюсь", "не верю", "верю",
)

RELIGION_BRIDGE = "Вопрос о Боге обычно упирается не только в «истину», но и в опору: смысл, страх, ответственность, надежду."
RELIGION_OPTICS = (
    "Теистическая оптика: Бог — личный источник смысла/нормы (часто в религиях книги).",
    "Деистическая/философская: Бог как первопричина/закон, без постоянного вмешательства.",
    "Атеистическая: смысл и этика строятся без сверхъестественного основания.",
    "Буддийская (классическая): нет необходимости в Творце; важнее причинность и освобождение от страдания.",
)
RELIGION_QUESTION = "Тебе интереснее: (1) что говорит буддизм, (2) философские доказательства, (3) как это влияет на жизнь и этику?"


def _is_religion_topic_question(text: str) -> bool:
    """Тематический вопрос о религии — НЕ шаблон first_turn, идёт в philosophy_pipeline."""
    t = (text or "").strip().lower()
    if not t:
        return False
    if not any(m in t for m in RELIGION_MARKERS):
        return False
    return any(a in t for a in TOPIC_ASK_MARKERS) or "?" in t or t.startswith("про ")


def _is_religious_personal_confession(text: str) -> bool:
    """Личная конфессиональная история — религия + личные маркеры, НЕ topic question.
    «Верю в себя» — НЕ религиозная конфессия (верю/вера требуют религиозного якоря)."""
    t = (text or "").strip().lower()
    if not t:
        return False
    if not any(m in t for m in RELIGION_MARKERS):
        return False
    # «верю/вера» без якоря (бог/грех/молитв/церков/ислам/христиан/будд/религ/конфесс) → не религия
    faith_only = any(m in t for m in ("вера", "вере", "верю", "верой", "веру")) and not any(
        a in t for a in ("бог", "грех", "молитв", "церков", "ислам", "христиан", "будд", "религ", "конфесс")
    )
    if faith_only:
        return False
    if _is_religion_topic_question(text):
        return False
    return any(p in t for p in PERSONAL_MARKERS)


# A) decision/нерешительность
DECISION_BRIDGE = "Выбор связан с риском и ответственностью — мозг ищет гарантию, которой нет."
DECISION_OPTICS = (
    "Стоики: отдели, что в зоне контроля, от того, что нет. Действуй в зоне влияния.",
    "Прагматизм: решение — эксперимент. Можно откатить или скорректировать.",
)
DECISION_PRACTICE = "Микро-практика: 1) Обратимость — что хуже, если ошибусь? 2) Десятилетний тест — через 10 лет это важно? 3) Один шаг на 1 день."
DECISION_QUESTION = "Какое решение сейчас зависло?"

# B) fear/anxiety/неопределённость
FEAR_BRIDGE = "Неопределённость вызывает тревогу — мозг пытается предсказать, но не может."
FEAR_OPTICS = (
    "Стоики: фокус на том, что контролируешь. Остальное — внешнее.",
    "Даос/буддизм: наблюдать волну, не бороться. Течение снижает сопротивление.",
)
FEAR_PRACTICE = "Микро-практика: инфогигиена (выключить ленту на 2 часа) + план на 10 минут (один шаг)."
FEAR_QUESTION = "Тебе сейчас нужнее спокойствие или план действий?"

# C) money/values/религии
MONEY_BRIDGE = "Деньги часто становятся символом безопасности и контроля."
MONEY_OPTICS = (
    "Стоики: деньги — инструмент, не цель. Контроль над отношением важнее суммы.",
    "Эпикур: достаточно мало — чтобы не страдать. Фокус на необходимом.",
    "Франкл: деньги служат ценностям. Смысл — в том, как используешь.",
)
CONFESSION_ADD = "В традициях — практики отпускания и доверия. Светский перевод: принять ограничения, найти опору в малом."
MONEY_QUESTION = "Тебе ближе контроль, достаточность или смысл?"


def _is_decision_intent(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in ("нереш", "решен", "выбор", "сомнева", "решить", "принять решение"))


def _is_fear_intent(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in ("страх", "тревог", "неопредел", "паник", "волнуюсь", "боюсь"))


def _is_money_intent(text: str) -> bool:
    """Деньги/финансы — не смысл жизни без денег."""
    t = text.lower()
    return any(k in t for k in ("деньг", "бедност", "богатств"))


def _is_meaning_life_intent(text: str) -> bool:
    """Смысл жизни / экзистенциальная пустота — без денег."""
    t = text.lower()
    return any(k in t for k in ("смысл", "зачем жить", "бессмыслен", "пустота", "зачем вообще"))


def render_first_turn_philosophy(user_text: str) -> Tuple[Optional[str], str]:
    """Возвращает (текст ответа, intent_label). None + «skip» — не отдавать шаблон, идти в philosophy_pipeline."""
    # 1) topic религии — НЕ отдаём first_turn шаблон
    if _is_religion_topic_question(user_text):
        return None, "skip"

    # 2) личная конфессиональная история — RELIGION_* шаблон
    if _is_religious_personal_confession(user_text):
        lines = [RELIGION_BRIDGE, ""] + list(RELIGION_OPTICS) + ["", RELIGION_QUESTION]
        return "\n".join(lines), "religion_confession"

    if _is_decision_intent(user_text):
        lines = [
            DECISION_BRIDGE,
            "",
            DECISION_OPTICS[0],
            DECISION_OPTICS[1],
            "",
            DECISION_PRACTICE,
            "",
            DECISION_QUESTION,
        ]
        return "\n".join(lines), "decision"
    if _is_fear_intent(user_text):
        lines = [
            FEAR_BRIDGE,
            "",
            FEAR_OPTICS[0],
            FEAR_OPTICS[1],
            "",
            FEAR_PRACTICE,
            "",
            FEAR_QUESTION,
        ]
        return "\n".join(lines), "fear"
    # FIX A: смысл жизни/пустота — НЕ деньги (отдельный шаблон)
    if _is_meaning_life_intent(user_text) and not _is_money_intent(user_text):
        MEANING_BRIDGE = "Когда всё кажется бессмысленным, мозг ищет один большой ответ — которого нет."
        MEANING_OPTICS = (
            "Стоики: смысл не в объяснении, а в действии. Что можно сделать сегодня, чтобы не предать себя?",
            "Экзистенциализм: смысл создаётся выбором. Не «зачем жить», а «ради чего я живу этот час».",
            "Франкл: смысл обнаруживается в ценностях — творчество, переживание, отношение.",
        )
        lines = [MEANING_BRIDGE, ""] + list(MEANING_OPTICS) + ["", "Тебе важнее облегчение сейчас или направление на ближайшее время?"]
        return "\n".join(lines), "meaning"

    if _is_money_intent(user_text):
        lines = [MONEY_BRIDGE, ""] + list(MONEY_OPTICS) + ["", MONEY_QUESTION]
        return "\n".join(lines), "money"
    # Fallback: decision (most common for philosophy intent)
    lines = [
        DECISION_BRIDGE,
        "",
        DECISION_OPTICS[0],
        DECISION_OPTICS[1],
        "",
        DECISION_PRACTICE,
        "",
        DECISION_QUESTION,
    ]
    return "\n".join(lines), "decision"
