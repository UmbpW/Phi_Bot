"""v16 Philosophy Guided Path: одна линия (lens lock), без картечи школ."""

from typing import Optional

# Темы для lens preview
LENS_PREVIEW_THEMES = (
    "деньг",
    "тревог",
    "тревож",
    "смысл",
    "выбор",
    "нестабильн",
    "поток",
    "риск",
    "решен",
    "нереш",
)


def detect_lens_preview_need(text: str) -> bool:
    """True если текст о деньгах, тревоге, смысле, выборе, нестабильности и т.д."""
    if not text or len(text.strip()) < 4:
        return False
    t = (text or "").lower()
    return any(theme in t for theme in LENS_PREVIEW_THEMES)


# Оптики по темам (контроль/буфер, достаточность, воспроизводимость)
LENS_OPTICS = {
    "control_buffer": (
        "Часть ситуации в зоне влияния, часть — нет. Фокус на том, что можно изменить.",
        "Буфер снижает шум: закрепить минимум, остальное — как получится.",
    ),
    "sufficiency_bounds": (
        "Достаточно мало — чтобы не страдать. Границы помогают не распыляться.",
        "«Нет» одному — «да» другому.",
    ),
    "reproducible_ability": (
        "Не результат разовый, а способность воспроизводить. Один шаг, затем ещё.",
        "Цикл — это фазы. Пауза тоже часть процесса.",
    ),
}


def render_lens_preview(theme: str) -> str:
    """2–3 короткие оптики (по 2 строки), без мета-фраз, без упражнений, без A/B/C."""
    lines = []
    for key, opts in LENS_OPTICS.items():
        lines.append(opts[0])
        lines.append(opts[1])
        lines.append("")
    if lines:
        lines.pop()  # убрать лишний \n
    return "\n".join(lines).strip()


def render_lens_soft_question() -> str:
    """Один мягкий вопрос без директив."""
    return "Какая из этих линий тебе сейчас ближе по ощущению?"


# Lens lock
LENS_LOCK_TURNS = 4


def get_active_lens(state: dict) -> Optional[str]:
    return state.get("active_lens")


def set_active_lens(state: dict, lens_id: str) -> None:
    state["active_lens"] = lens_id
    state["lens_lock_turns_left"] = LENS_LOCK_TURNS


def tick_lens_lock(state: dict) -> None:
    """Уменьшить lens_lock_turns_left на 1."""
    left = state.get("lens_lock_turns_left", 0)
    if left > 0:
        state["lens_lock_turns_left"] = left - 1


def is_lens_locked(state: dict) -> bool:
    """True если активен lock — нельзя добавлять другие школы."""
    return state.get("lens_lock_turns_left", 0) > 0


# Маппинг ответа пользователя на lens_id
LENS_CHOICE_KEYWORDS = {
    "control_buffer": ("контроль", "буфер", "влияю", "первая", "1"),
    "sufficiency_bounds": ("достаточ", "границ", "хватит", "вторая", "2"),
    "reproducible_ability": ("воспроизвод", "цикл", "способность", "третья", "3"),
}

# Маппинг lens_id -> system lens ID для select_lenses
LENS_TO_SYSTEM_ID = {
    "control_buffer": "lens_control_scope",
    "sufficiency_bounds": "lens_boundary",
    "reproducible_ability": "lens_micro_agency",
}


def detect_lens_choice(text: str) -> Optional[str]:
    """Если пользователь выбрал линию — вернуть lens_id, иначе None."""
    if not text or len(text.strip()) < 1:
        return None
    t = (text or "").lower().strip()
    for lens_id, keywords in LENS_CHOICE_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            return lens_id
    return None
