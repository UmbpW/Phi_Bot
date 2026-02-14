"""Philosophy Match: состояние по пользователю для мягкой подсказки оптики."""

from typing import Any, Optional

# Хранилище: user_id -> profile
_PROFILES: dict[int, dict[str, Any]] = {}


def _ensure_profile(user_id: int) -> dict[str, Any]:
    if user_id not in _PROFILES:
        pm_init_user(user_id)
    return _PROFILES[user_id]


def pm_init_user(user_id: int) -> None:
    """Инициализирует профиль пользователя."""
    _PROFILES[user_id] = {
        "turns": 0,
        "lens_counts": {},
        "mode_counts": {},
        "last_suggest_turn": 0,
    }


def pm_record_signal(
    user_id: int,
    lens_id: Optional[str] = None,
    mode_id: Optional[str] = None,
    lens_ids: Optional[list] = None,
) -> None:
    """Записывает сигналы линз/режима и увеличивает turns на 1 за вызов."""
    profile = _ensure_profile(user_id)
    profile["turns"] = profile.get("turns", 0) + 1

    for lid in lens_ids or ([lens_id] if lens_id else []):
        if lid:
            key = lid.replace("lens_", "") if lid.startswith("lens_") else lid
            profile["lens_counts"][key] = profile["lens_counts"].get(key, 0) + 1
    if mode_id:
        profile["mode_counts"][mode_id] = profile["mode_counts"].get(mode_id, 0) + 1


def pm_get_profile(user_id: int) -> dict[str, Any]:
    """Возвращает профиль пользователя."""
    return _ensure_profile(user_id).copy()


def pm_set_last_suggest_turn(user_id: int, turn: int) -> None:
    """Обновляет last_suggest_turn после показа карточки."""
    profile = _ensure_profile(user_id)
    profile["last_suggest_turn"] = turn
