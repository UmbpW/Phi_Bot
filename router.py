"""Роутер для выбора линз по ключевым словам."""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# Маппинг: имя линзы -> список ключевых слов (нижний регистр)
LENS_KEYWORDS: dict[str, list[str]] = {
    "lens_programming": [
        "код", "программирование", "python", "javascript", "разработка",
        "функция", "баг", "ошибка", "api", "алгоритм", "git", "тест",
    ],
    "lens_productivity": [
        "продуктивность", "тайм-менеджмент", "задачи", "цели",
        "планирование", "привычки", "эффективность", "управление временем",
    ],
    "lens_psychology": [
        "психология", "эмоции", "стресс", "мотивация", "отношения",
        "чувства", "депрессия", "тревога", "настроение",
    ],
    "lens_science": [
        "наука", "исследование", "эксперимент", "данные", "статистика",
        "гипотеза", "теория", "научн",
    ],
    "lens_business": [
        "бизнес", "стартап", "маркетинг", "продажи", "стратегия",
        "доход", "инвест", "конкурен",
    ],
    "lens_control_scope": [
        "хаос", "не контролирую", "всё валится", "тревога", "перегруз",
        "неопределённ", "не могу контролировать",
    ],
    "lens_expectation_gap": [
        "ожидал", "должно было", "рассчитывал", "разочарование",
        "кризис", "карьера", "отношения", "не оправдалось",
    ],
    "lens_mortality_focus": [
        "время", "не успею", "жизнь проходит", "смысл", "приоритеты",
        "конец", "успевать",
    ],
    "lens_role_position": [
        "как поступить", "моя позиция", "решение", "конфликт",
        "ответственность", "занять позицию",
    ],
    "lens_micro_agency": [
        "не могу начать", "нет сил", "апатия", "прокрастинация",
        "низкая энергия", "ничего не делаю",
    ],
    "lens_boundary": [
        "давят", "требуют", "не хочу", "границ", "давление",
        "ожидания других", "отказывать",
    ],
    "lens_narrative": [
        "я такой", "моя жизнь", "всегда так", "самооценка",
        "идентичность", "кризис", "история обо мне",
    ],
    "lens_finance_rhythm": [
        "волнами", "то пусто", "то густо", "поток", "охотник", "добыча",
        "запас", "ритм", "пауза между", "волновой доход",
    ],
    "lens_general": [],  # fallback, всегда доступна
}


# v19: финансовый режим → lens_finance_rhythm
FINANCIAL_PATTERNS = (
    "зарабатываю много но нет накоплений",
    "деньги уходят",
    "не копится",
    "куда уходят деньги",
    "высокий доход но нет сбережений",
    "зарабатываю",
    "доход",
    "траты",
    "дыры",
    "не копится",
    "нет накоплений",
    "боюсь что денег не будет",
)


def detect_financial_pattern(text: str) -> bool:
    """Проверяет финансовый паттерн в тексте."""
    t = (text or "").lower()
    return any(p in t for p in FINANCIAL_PATTERNS)


def _normalize_text(text: str) -> str:
    """Нормализует текст для поиска: нижний регистр, без лишних символов."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s\-]", " ", text)
    return text


def select_lenses(
    user_text: str,
    available_lenses: dict[str, str],
    max_lenses: int = 3,
) -> list[str]:
    """Выбирает 2–3 линзы по ключевым словам.

    Args:
        user_text: Текст запроса пользователя
        available_lenses: dict имя_линзы -> содержимое
        max_lenses: максимум линз (2–3)

    Returns:
        Список имён выбранных линз
    """
    normalized = _normalize_text(user_text)
    words = set(normalized.split())

    scores: list[tuple[str, int]] = []
    for lens_name, keywords in LENS_KEYWORDS.items():
        if lens_name not in available_lenses:
            continue
        if lens_name == "lens_general":
            continue  # используем только как fallback
        score = sum(1 for kw in keywords if kw in normalized or kw in words)
        if score > 0:
            scores.append((lens_name, score))

    scores.sort(key=lambda x: (-x[1], x[0]))
    selected = [name for name, _ in scores[:max_lenses]]

    if not selected:
        selected = ["lens_general"]

    return selected
