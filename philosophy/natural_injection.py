"""v17 Natural Philosophy Injection: одна опора при устойчивом паттерне."""

from typing import Optional, Tuple

# Паттерны устойчивого жизненного цикла (>=2 ключей)
STABLE_PATTERN_KEYS = (
    "волнами",
    "волна",
    "полгода ничего",
    "потом бац",
    "охота",
    "добыча",
    "бег",
    "поиск",
    "дыры",
    "непредсказуемо",
    "цикл",
    "снова и снова",
    "по кругу",
    "замкнутый круг",
    "каждый раз",
    "опять то же",
)

INJECTION_COOLDOWN_TURNS = 4


def detect_stable_pattern(text: str) -> Optional[str]:
    """Match если >=2 ключей из STABLE_PATTERN_KEYS. Возвращает 'pattern' или None."""
    if not text or len(text.strip()) < 10:
        return None
    t = (text or "").lower()
    matches = [k for k in STABLE_PATTERN_KEYS if k in t]
    return "pattern" if len(matches) >= 2 else None


def choose_philosophy_line(match: Optional[str], text: str) -> str:
    """wave/hunter/control -> stoic_control, sufficiency -> epicurean, identity -> existential."""
    if not match:
        return "stoic_control"
    t = text.lower()
    if any(k in t for k in ("достаточн", "мало", "границ", "хватит")):
        return "epicurean"
    if any(k in t for k in ("роль", "идентичн", "кто я", "смысл", "ценност")):
        return "existential"
    return "stoic_control"  # wave/hunter/control default


# Инъекция stoic_control: 6–10 строк, без слова «философия»
STOIC_CONTROL_INJECTION = """В цикле есть фаза паузы — не провал, а часть волны.
Разделение «влияю / не влияю» снижает напряжение: часть принимаешь как внешнее, часть — как зону действия.
Опора — в том, что повторяется: один шаг, ритуал, граница. Цикл не отменить, но можно выбрать, где стоять."""


EPICUREAN_INJECTION = """Достаточно мало — чтобы не страдать.
Граница «хватит» защищает от распыления.
Фокус на близком и простом снижает шум непредсказуемого."""


EXISTENTIAL_INJECTION = """Роль и позиция важнее разового результата.
Смысл создаётся выбором: как относиться к циклу, что считать ценным.
Даже в повторе остаётся пространство для позиции."""


def render_injection(line_id: str) -> str:
    """Возвращает текст инъекции 6–10 строк, без практики, макс 1 мягкий вопрос или без вопроса."""
    if line_id == "epicurean":
        return EPICUREAN_INJECTION
    if line_id == "existential":
        return EXISTENTIAL_INJECTION
    return STOIC_CONTROL_INJECTION


def should_inject(
    state: dict,
    stage: str,
    match: Optional[str],
    is_safety: bool = False,
) -> bool:
    """True если stage==guidance, match есть, cooldown прошёл, не safety."""
    if stage != "guidance" or not match or is_safety:
        return False
    last_inj = state.get("last_injection_turn", -10)
    turn = state.get("turn_index", 0)
    if turn - last_inj < INJECTION_COOLDOWN_TURNS:
        return False
    return True


def mark_injection_done(state: dict) -> None:
    state["last_injection_turn"] = state.get("turn_index", 0)


def insert_injection_after_first_paragraph(text: str, injection: str) -> str:
    """Вставить injection после первого смыслового абзаца, до финального вопроса."""
    if not text or not injection:
        return text
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paras) <= 1:
        return text + "\n\n" + injection
    # После первого абзаца
    result = paras[0] + "\n\n" + injection
    if len(paras) > 1:
        result += "\n\n" + "\n\n".join(paras[1:])
    return result.strip()
