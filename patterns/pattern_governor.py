"""Pattern Governor v12: cooldowns, collision resolution, philosophy routing."""

import random
from typing import Any, Optional

# Триггеры философского вопроса
PHILOSOPHY_TRIGGERS = (
    "как философ",
    "что философ",
    "философия денег",
    "как думать о деньгах",
    "что думал",
    "стоики",
    "камю",
    "франкл",
)

# Короткие ответы — не переспрашивать "что имел в виду"
SHORT_AMBIGUOUS = ("оба", "все", "да", "нет", "ок", "окей", "и то и то")


def should_add_bridge(
    user_id: int,
    stage: str,
    state: dict,
) -> bool:
    """Bridge не чаще чем раз в 2 user turns. Warmup: 1.0 на первом, 0.6 далее. Guidance: 0.5."""
    turn = state.get("turn_index", 0)
    last_bridge = state.get("last_bridge_turn", -10)

    if turn - last_bridge < 2:
        return False  # cooldown

    if stage == "warmup":
        if turn <= 1:
            return True
        return random.random() < 0.6

    if stage == "guidance":
        return random.random() < 0.5

    return False


def resolve_pattern_collisions(context: dict) -> dict:
    """Mutual exclusion: fork vs option_close, warmup/safety без option_close."""
    ctx = dict(context)
    stage = ctx.get("stage", "")

    if ctx.get("want_fork"):
        ctx["want_option_close"] = False
    if stage == "warmup":
        ctx["want_option_close"] = False
    if stage == "safety" or ctx.get("is_safety"):
        ctx["want_option_close"] = False

    return ctx


def is_philosophy_question(text: str) -> bool:
    """True если триггеры философского вопроса или 'философ' в тексте."""
    if not text or len(text.strip()) < 3:
        return False
    t = text.lower().strip()
    if "философ" in t:
        return True
    return any(tr in t for tr in PHILOSOPHY_TRIGGERS)


def is_short_ambiguous(text: str) -> bool:
    """Короткий неоднозначный ответ — 'оба', 'все', 'да', 'нет'."""
    t = (text or "").strip().lower()
    return t in SHORT_AMBIGUOUS or (len(t) <= 3 and t.isalpha())


def governor_plan(
    user_id: int,
    stage: str,
    user_text: str,
    context: dict,
    state: dict,
) -> dict:
    """Возвращает план для pattern engine."""
    ctx = resolve_pattern_collisions(context)

    plan = {
        "add_bridge": should_add_bridge(user_id, stage, state),
        "disable_pattern_engine": False,
        "disable_option_close": False,
        "disable_fork": False,
        "force_philosophy_mode": False,
        "force_repeat_options": False,
    }

    if is_short_ambiguous(user_text) and state.get("last_options"):
        plan["force_repeat_options"] = True

    if is_philosophy_question(user_text):
        plan["force_philosophy_mode"] = True
        plan["disable_pattern_engine"] = True

    if stage == "guidance" and ctx.get("want_fork"):
        plan["disable_option_close"] = True

    return plan
