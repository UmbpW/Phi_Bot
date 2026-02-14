"""Philosophy responder: 3–4 оптики + вопрос выбора. Confessions: сравнительная антропология."""

from typing import Optional, Tuple

# Статические блоки (стоики, даос/буддизм, экзистенциалисты)
STOIC_OPTIQUE = (
    "Стоики: важнее отделить то, что от тебя зависит, от того, что нет. "
    "Спокойствие — через отношение к событию, не через контроль внешнего."
)
DAO_BUDDHIST_OPTIQUE = (
    "Даос/буддизм: наблюдать, не бороться. Течение, а не противостояние. "
    "Принятие «как есть» снижает внутреннее сопротивление."
)
EXISTENTIAL_OPTIQUE = (
    "Экзистенциалисты/Франкл: смысл создаётся выбором и ценностями. "
    "Даже в ограничениях остаётся пространство для позиции."
)
EPICUREAN_OPTIQUE = (
    "Эпикур: достаточно мало, чтобы не страдать. "
    "Фокус на простом и близком снижает шум."
)

CHOICE_QUESTION = "Тебе ближе оптика A (спокойствие через отношение), B (наблюдение/течение) или C (смысл/выбор)?"

# Конфессии: нейтральные наблюдения + светский перевод
CONFESSION_OBSERVATIONS = (
    "В христианстве страх часто проживают через молитву и общину.",
    "В буддизме — через наблюдение и отпускание привязанности.",
    "В исламе — через доверие и сдачу намерения.",
)
SECULAR_TRANSLATION = "Светский перевод: «отпустить контроль», «принять ограничения», «найти опору в малом» — общие мотивы."


def _is_confession_question(text: str) -> bool:
    """Вопрос про конфессии/религию."""
    t = (text or "").lower()
    return any(
        x in t
        for x in ("конфесси", "религ", "молитв", "церков", "будд", "христианств", "ислам", "вера")
    )


def respond_philosophy_question(user_text: str, context: Optional[dict] = None) -> Tuple[str, Optional[dict]]:
    """Возвращает (ответ, pending_info).

    pending_info = {"kind":"fork","options":["A","B","C"],"default":"A","prompt":...} или None.
    Формат: ≤12–14 строк, 3 блока оптик + вопрос выбора.
    """
    context = context or {}

    lines = ["Дам 3 оптики:"]
    lines.append("")
    lines.append("(А) " + STOIC_OPTIQUE)
    lines.append("(Б) " + DAO_BUDDHIST_OPTIQUE)
    lines.append("(В) " + EXISTENTIAL_OPTIQUE)

    if _is_confession_question(user_text):
        lines.append("")
        lines.append("Про традиции:")
        for obs in CONFESSION_OBSERVATIONS[:2]:
            lines.append("— " + obs)
        lines.append(SECULAR_TRANSLATION)

    lines.append("")
    lines.append(CHOICE_QUESTION)

    pending = {
        "kind": "fork",
        "options": ["A", "B", "C"],
        "default": "A",
        "prompt": CHOICE_QUESTION,
        "created_turn": context.get("turn_index", 0),
    }
    return "\n".join(lines), pending


def respond_philosophy_question_legacy(user_text: str) -> str:
    """Обратная совместимость: возвращает только текст."""
    text, _ = respond_philosophy_question(user_text)
    return text
