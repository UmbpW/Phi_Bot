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
    "lens_general": [],  # fallback, всегда доступна
}


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
