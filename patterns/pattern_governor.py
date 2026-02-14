"""Pattern Governor v12 + v17.2: cooldowns, philosophy pipeline priority."""

import random
from typing import Any, Optional

from router import detect_financial_pattern
from utils.is_philosophy_question import is_philosophy_question as _is_philosophy_question
from utils.intent_gate import is_philosophy_intent as _is_philosophy_intent

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
    """True если философский вопрос или конфессии (сравнительная антропология)."""
    return _is_philosophy_question(text)


def is_short_ambiguous(text: str) -> bool:
    """Короткий неоднозначный ответ — 'оба', 'все', 'да', 'нет'."""
    t = (text or "").strip().lower()
    return t in SHORT_AMBIGUOUS or (len(t) <= 3 and t.isalpha())


def is_full_question(text: str) -> bool:
    """v21/v21.3: содержательный вопрос → answer-first mode.
    Срабатывает если: len > 180 ИЛИ ≥2 маркеров."""
    if not text:
        return False
    t = (text or "").strip()
    t_lower = t.lower()
    if len(t) > 180:
        return True
    markers = [
        "как выйти",
        "что делать",
        "не получается",
        "тяжелой",
        "ситуации",
        "нет сил",
        "все плохо",
        "не вижу выхода",
        "не понимаю что делать",
    ]
    hit = sum(1 for m in markers if m in t_lower)
    return hit >= 2


def governor_plan(
    user_id: int,
    stage: str,
    user_text: str,
    context: dict,
    state: dict,
) -> dict:
    """Возвращает план для pattern engine."""
    # v21.3 ПЕРВОЕ правило: answer-first перекрывает warmup/uncertainty/small talk
    if is_full_question(user_text):
        return {
            "add_bridge": False,
            "disable_pattern_engine": True,
            "disable_option_close": True,
            "disable_fork": False,
            "disable_warmup": True,
            "disable_empathy_bridge": True,
            "force_philosophy_mode": False,
            "force_repeat_options": False,
            "stage_override": "guidance",
            "answer_first_required": True,
            "philosophy_pipeline": True,
            "allow_philosophy_examples": True,
            "max_lenses": 3,
            "max_practices": 1,
            "max_questions": 1,
        }
    # ТОЛЬКО ПОСЛЕ answer-first: warmup rules, uncertainty rules, small talk
    # v20.1 Warmup Hard Guard: длинные/финансовые — сразу guidance, без warmup patterns
    text_len = len((user_text or "").strip())
    if text_len > 250:
        return {
            "add_bridge": False,
            "disable_pattern_engine": True,
            "disable_option_close": True,
            "disable_fork": False,
            "force_philosophy_mode": False,
            "force_repeat_options": False,
            "stage_override": "guidance",
        }
    if detect_financial_pattern(user_text):
        return {
            "add_bridge": False,
            "disable_pattern_engine": True,
            "disable_option_close": True,
            "disable_fork": False,
            "force_philosophy_mode": False,
            "force_repeat_options": False,
            "stage_override": "guidance",
        }

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

    # v17.2 Philosophy Pipeline Priority: is_philosophy_intent (broader) до pattern_engine
    if _is_philosophy_intent(user_text) or _is_philosophy_question(user_text):
        plan["philosophy_pipeline"] = True
        plan["force_philosophy_mode"] = True
        plan["disable_pattern_engine"] = True
        plan["disable_short_templates"] = True
        plan["disable_list_templates"] = True

    if stage == "guidance" and ctx.get("want_fork"):
        plan["disable_option_close"] = True

    return plan
