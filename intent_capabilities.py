# intent_capabilities.py — CAPABILITIES INTENT: "что ты умеешь / чем полезен"
import re
from dataclasses import dataclass


@dataclass
class CapIntentResult:
    is_capabilities: bool
    score: int
    reasons: list[str]


def _norm(text: str) -> str:
    t = (text or "").lower().strip()
    t = t.replace("ё", "е")
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t, flags=re.UNICODE).strip()
    return t


def detect_capabilities_intent(user_text: str) -> CapIntentResult:
    t = _norm(user_text)

    if not t:
        return CapIntentResult(False, 0, ["empty"])

    # Быстрые исключения: если это явно "тема/проблема", не перехватываем
    topic_markers = [
        "дружб", "любов", "смерт", "деньг", "морал", "смысл", "выбор", "страх",
        "тревог", "сон", "бессон", "работ", "увол", "развод", "отношен", "сем",
        "апат", "депресс", "паник", "злост", "обид"
    ]
    if any(m in t for m in topic_markers) and ("что ты" not in t and "чем ты" not in t and "как ты" not in t):
        return CapIntentResult(False, 0, ["topic_like"])

    score = 0
    reasons: list[str] = []

    if "?" in (user_text or ""):
        score += 1
        reasons.append("has_question_mark")

    if re.search(r"\b(умеешь|можешь|способен|умеете|можете)\b", t):
        score += 2
        reasons.append("can_do_verbs")

    if re.search(r"(возможност|функц|фич|опц|режим|формат|инструмент)", t):
        score += 2
        reasons.append("capability_nouns")

    if re.search(r"\b(что|чем|как)\b", t) and "ты" in t:
        score += 1
        reasons.append("wh_question_about_you")

    if re.search(r"(о себе|про себя|как работаешь|как ты работаешь|как устроен|как устроено)", t):
        score += 2
        reasons.append("about_you")

    if re.search(r"(полезен|помогаешь|зачем ты|в чем смысл|для чего ты)", t):
        score += 1
        reasons.append("usefulness")

    if len(t) >= 140 and any(x in t for x in ["мне", "у меня", "я", "сегодня", "вчера", "почему", "помоги"]):
        score -= 2
        reasons.append("long_context_penalty")

    is_cap = score >= 3
    return CapIntentResult(is_cap, score, reasons)


CAPABILITIES_REPLY_RU = """Если чуть шире — я умею смотреть на один и тот же вопрос через разные философские взгляды.

Например:
— про страх: как стоики — через контроль, принятие неопределённости и тренировку спокойствия
— про смысл: как экзистенциалисты — через выбор, ответственность и "что я подтверждаю поступком"
— про деньги: как философию достаточности, свободы и зависимости от потока
— про дружбу: от добродетели и характера до взаимной поддержки и верности
— про мораль: как про принципы, последствия и человеческую меру
— про смерть: как про конечность, которая делает жизнь яснее (без мрачных лозунгов)

Можно попросить прямо:
«разбери по-стоически» / «а теперь по-буддийски» / «дай экзистенциальную оптику» / «сравни 2 подхода».

Я не навязываю школу — можем переключать оптику и искать ту, которая лучше объясняет твою тему.
"""
