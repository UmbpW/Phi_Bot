"""First Turn Philosophy Gate: шаблоны ответа первого хода (answer-first, без generic warmup)."""

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


def _is_money_or_confession_intent(text: str) -> bool:
    t = text.lower()
    return any(
        k in t
        for k in (
            "деньг",
            "бедност",
            "богатств",
            "конфесс",
            "религ",
            "христиан",
            "ислам",
            "будд",
            "смысл",
            "зачем жить",
        )
    )


def render_first_turn_philosophy(user_text: str) -> tuple[str, str]:
    """Возвращает (текст ответа, intent_label для лога). ≤14 строк, 1 вопрос в конце."""
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
    if _is_money_or_confession_intent(user_text):
        is_confession = any(
            k in user_text.lower()
            for k in ("конфесс", "религ", "христиан", "ислам", "будд", "молитв", "вера")
        )
        lines = [
            MONEY_BRIDGE,
            "",
            MONEY_OPTICS[0],
            MONEY_OPTICS[1],
            MONEY_OPTICS[2],
        ]
        if is_confession:
            lines.extend(["", CONFESSION_ADD])
        lines.extend(["", MONEY_QUESTION])
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
