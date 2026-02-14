"""Agency Layer v13: меньше мета-вопросов, больше инициативы и примеров."""

import re
from typing import Any, Optional

# Фразы непонимания — агент даёт пример вместо уточнений
DONT_UNDERSTAND_TRIGGERS = (
    "не понимаю",
    "не ясно",
    "я запутался",
    "запутался",
    "непонятно",
    "не понятно",
)

# Термины с примерами
TERM_EXAMPLES = {
    "рамка": {
        "деньги": "Деньги: «часть в зоне контроля, часть нет». Ты можешь влиять на расходы сегодня, но не на курс валюты.\nРамка — это угол взгляда, который помогает разделить «влияю / не влияю».",
        "ответственность": "Ответственность: «я могу отвечать за свои действия, но не за чужие решения». Ты выбираешь, как реагировать, а не как поступят другие.\nРамка — способ структурировать мысль, не обвиняя себя за всё.",
        "стабильность": "Стабильность: «что можно закрепить сейчас, а что остаётся неопределённым». Опора — в малом, что ты контролируешь.\nРамка — это граница между «где я могу действовать» и «где нет».",
        "default": "Пример: «часть в зоне контроля, часть нет». Разделение помогает снизить шум.\nРамка — угол взгляда, который структурирует мысль.",
    },
    "линза": {
        "деньги": "Через линзу «разрыв ожиданий»: ждал повышения — не получил. Разочарование = зазор между ожиданием и реальностью.\nЛинза — фильтр, через который смотришь на ситуацию.",
        "ответственность": "Через линзу «границы»: где твоя зона, где чужая. «Я могу сказать нет» — уже действие.\nЛинза — оптика, которая выделяет один аспект.",
        "стабильность": "Через линзу «мини-действие»: один шаг на 5 минут. Не «решить всё», а «что возможно сейчас».\nЛинза — инструмент взгляда на ситуацию под определённым углом.",
        "default": "Через линзу «зона контроля»: разделить «влияю / не влияю». Один шаг в зоне влияния.\nЛинза — оптика, через которую смотришь на ситуацию.",
    },
    "оптика": {
        "деньги": "Оптика денег: не «достаточно ли», а «что в зоне контроля». Расходы, приоритеты, шаги — что можно изменить сейчас.\nОптика — способ взгляда, фокус на одном измерении.",
        "ответственность": "Оптика ответственности: «за что я отвечаю, за что нет». Твои действия — да, чужие решения — нет.\nОптика — угол зрения на ситуацию.",
        "стабильность": "Оптика стабильности: «что закрепить в малом». Один ритуал, один шаг — опора в неопределённости.\nОптика — способ видеть структуру в хаосе.",
        "default": "Оптика «зона контроля»: разделить влияемое и нет. Один шаг в зоне влияния.\nОптика — угол зрения на ситуацию.",
    },
}


def _detect_topic(user_text: str) -> str:
    """Определяет тему по ключевым словам."""
    t = (user_text or "").lower()
    if "деньг" in t or "денег" in t or "зарплат" in t or "расход" in t:
        return "деньги"
    if "ответствен" in t or "виноват" in t or "должен" in t:
        return "ответственность"
    if "стабильн" in t or "неопределённ" in t or "хаос" in t:
        return "стабильность"
    return "default"


def is_meta_format_question(text: str) -> bool:
    """True если текст — мета-вопрос о формате ответа (список схем, какой формат и т.д.)."""
    if not text or not text.strip():
        return False
    t = text.lower().strip()

    # Явные паттерны
    if "список" in t and "схем" in t:
        return True
    if "разобрать" in t and ("глубже" in t or "упрост" in t):
        return True
    if "рамку" in t and "практик" in t:
        return True
    if "какой формат" in t:
        return True
    if "как тебе удобнее" in t:
        return True
    if "что именно показать" in t:
        return True

    # Общий паттерн: вопрос о выборе формата, а не содержания
    format_choice = re.search(
        r"(как|в каком|в каком виде|в каком формате|что показать|что именно).*"
        r"(показать|дать|рассказать|сформулировать)",
        t,
    )
    if format_choice and "?" in text:
        return True

    return False


def _is_question_sentence(s: str) -> bool:
    """Проверяет, является ли строка вопросительным предложением."""
    s = s.strip()
    return bool(s) and (s.endswith("?") or s.endswith("？"))


def strip_meta_format_questions(text: str) -> tuple[str, int]:
    """Удаляет предложения-мета-вопросы о формате. Возвращает (текст, количество удалённых)."""
    if not text or not text.strip():
        return text, 0
    sentences = re.split(r"(?<=[.!?])\s+", text)
    result = []
    stripped_count = 0
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if _is_question_sentence(s) and is_meta_format_question(s):
            stripped_count += 1
            continue
        result.append(s)
    return " ".join(result).strip(), stripped_count


def term_example_first(term: str, user_context: dict) -> str:
    """Возвращает короткий пример для термина (рамка/линза/оптика) по теме."""
    term_lower = (term or "").lower().strip()
    if term_lower not in TERM_EXAMPLES:
        term_lower = "рамка"  # fallback

    examples = TERM_EXAMPLES.get(term_lower, TERM_EXAMPLES["рамка"])
    user_text = user_context.get("user_text", "") or ""
    topic = _detect_topic(user_text)
    example = examples.get(topic) or examples["default"]
    return example


def _ask_question_allowed(count: int) -> bool:
    """Разрешить вопрос: 1й, 3й, 5й... — с вопросом; 2й, 4й, 6й... — без вопроса."""
    return (count % 2) == 0


def should_ask_question(user_id: int, state: dict) -> bool:
    """answer>ask: каждый 2-й ход guidance — без вопроса."""
    count = state.get("guidance_turns_count", 0)
    return _ask_question_allowed(count)


def fork_density_guard(user_id: int, state: dict) -> bool:
    """Разрешить fork/option_close не чаще 1 раза в 3 guidance-turns."""
    current = state.get("guidance_turns_count", 0)
    last = state.get("last_fork_turn", -10)
    return (current - last) >= 3


def handle_i_dont_understand(user_text: str) -> bool:
    """True если пользователь выражает непонимание — дать пример вместо уточнений."""
    if not user_text:
        return False
    t = (user_text or "").lower().strip()
    return any(phrase in t for phrase in DONT_UNDERSTAND_TRIGGERS)


def is_term_question(user_text: str) -> Optional[str]:
    """Если пользователь спрашивает 'что такое рамка/линза/оптика' — вернуть термин."""
    if not user_text:
        return None
    t = (user_text or "").lower()
    ask_triggers = "что так" in t or "что такое" in t or "объясни" in t or "поясни" in t
    if not ask_triggers:
        return None
    if "рамк" in t:
        return "рамка"
    if "линз" in t:
        return "линза"
    if "оптик" in t:
        return "оптика"
    return None


def remove_questions(text: str) -> str:
    """Удаляет вопросительные предложения, оставляет утверждения.
    Фразу «если хочешь — продолжим» оставляет без '?'."""
    if not text or not text.strip():
        return text
    # Сохраняем мягкое предложение продолжить
    text = re.sub(r"(если хочешь\s*[—\-]\s*продолжим)\s*[?？]\s*", r"\1. ", text, flags=re.IGNORECASE)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    result = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if s.endswith("?") or s.endswith("？"):
            continue
        result.append(s)
    return " ".join(result).strip()


# Микро-шаг при "не понимаю" — без вопроса
DONT_UNDERSTAND_MICRO_STEP = "Если хочешь — продолжим с одного примера."


def replace_clarifying_with_example(text: str, micro_step: str = "") -> str:
    """Заменяет каскад уточняющих вопросов на микро-шаг (при handle_i_dont_understand)."""
    micro_step = micro_step or DONT_UNDERSTAND_MICRO_STEP
    # Удаляем блоки типа "что именно непонятно: ..." или "уточни: ..."
    text = re.sub(
        r"(что именно (непонятно|не ясно)|уточни[^\?]*|что конкретно[^\?]*)\??\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Добавляем микро-шаг в конец
    if micro_step and not text.endswith("."):
        text = text.rstrip() + ". " + micro_step
    elif micro_step:
        text = text.rstrip() + " " + micro_step
    return text.strip()
