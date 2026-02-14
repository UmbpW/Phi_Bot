"""SOURCE_RULE_LANGUAGE_MATCH: только RU editions для русскоязычных пользователей."""

from typing import Optional

# user_language: по умолчанию RU (бот русскоязычный)
DEFAULT_USER_LANGUAGE = "RU"

# Дефолтный стоический источник для RU
DEFAULT_STOIC_SOURCE_RU = "William Irvine"  # RU edition — «Ирвин У. Путь желания» и аналоги

# Современные стоические авторы с русскими переводами
MODERN_STOIC_AUTHORS_RU = (
    "William Irvine",      # Ирвин У. / А Guide to the Good Life
    "Massimo Pigliucci",   # Массимо Пильюччи
    "Ryan Holiday",        # Райан Холидей
)

# Строка для system prompt / philosophy style
SOURCE_RULE_INSTRUCTION_RU = """
## SOURCE_RULE_LANGUAGE_MATCH
- Если user_language == RU → предлагать только RU editions.
- Предпочитать современных стоических авторов с русскими переводами.
- default_stoic_source = William Irvine (RU edition).
"""

# SOURCE_SUGGESTION_RULE
SOURCE_SUGGESTION_RULE = """
## SOURCE_SUGGESTION_RULE
- max 1 source — максимум один источник за раз
- only after lens_lock established — только когда пользователь уже выбрал линию (active_lens)
- only soft phrasing — только мягкие формулировки («может откликнуться», «если захочешь углубиться»)
- no lists — без списков, маркированных пунктов, нумерации
"""


def get_user_language(telegram_lang_code: Optional[str]) -> str:
    """Маппинг language_code в user_language. По умолчанию RU."""
    if not telegram_lang_code:
        return DEFAULT_USER_LANGUAGE
    code = (telegram_lang_code or "").upper()[:2]
    if code in ("RU", "UK", "BE"):
        return "RU"
    return code or DEFAULT_USER_LANGUAGE


def should_offer_ru_sources_only(user_language: str) -> bool:
    """True если предлагать только RU editions."""
    return user_language.upper() == "RU"


def get_default_stoic_source(user_language: str) -> str:
    """Возвращает дефолтный стоический источник для языка."""
    if should_offer_ru_sources_only(user_language):
        return DEFAULT_STOIC_SOURCE_RU
    return "William Irvine"


def should_allow_source_suggestion(state: dict) -> bool:
    """SOURCE_SUGGESTION_RULE: только после lens_lock (active_lens установлена)."""
    return bool(state.get("active_lens"))
