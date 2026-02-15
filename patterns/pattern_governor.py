"""Pattern Governor v12 + v17.2: cooldowns, philosophy pipeline priority."""

import random
from typing import Any, Optional

from router import detect_financial_pattern
from utils.is_philosophy_question import is_philosophy_question as _is_philosophy_question
from utils.intent_gate import is_expand_request, is_philosophy_intent as _is_philosophy_intent

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


FULL_Q_MARKERS = [
    "что делать", "не понимаю", "не получается", "помоги", "как быть",
    "как выйти", "устал", "тревож", "боюсь", "пустот", "смысл", "один",
    "деньги", "финанс", "отношен", "выбор", "решени", "нет сил",
    "плохо", "тупик", "завал", "депресс", "паник", "страх",
]


def is_full_question(text: str) -> bool:
    """Содержательный вопрос → answer-first mode.
    1) len >= 220  2) len >= 160 + 2 маркера  3) len >= 160 + структура (. или ,)."""
    if not text:
        return False
    t = (text or "").strip().lower()

    if len(t) >= 220:
        return True

    hits = sum(1 for m in FULL_Q_MARKERS if m in t)
    if len(t) >= 160 and hits >= 2:
        return True

    if len(t) >= 160 and (t.count(".") >= 2 or t.count(",") >= 6):
        return True

    return False


def governor_plan(
    user_id: int,
    stage: str,
    user_text: str,
    context: dict,
    state: dict,
) -> dict:
    """Возвращает план для pattern engine."""
    # Answer-first must override warmup & patterns — ПЕРВОЕ правило, до warmup/uncertainty
    if is_full_question(user_text):
        plan = {}
        plan["stage_override"] = "guidance"
        plan["answer_first_required"] = True

        plan["disable_warmup"] = True
        plan["disable_pattern_engine"] = True
        plan["disable_empathy_bridge"] = True
        plan["disable_option_close"] = True

        plan["disable_fork"] = False

        plan["philosophy_pipeline"] = True
        plan["allow_philosophy_examples"] = True
        plan["add_bridge"] = False
        plan["force_philosophy_mode"] = False
        plan["force_repeat_options"] = False

        plan.setdefault("max_lenses", 3)
        plan.setdefault("max_practices", 1)
        plan.setdefault("max_questions", 1)

        return plan

    # PATCH 5: explain_mode — запросы на разъяснение (до warmup)
    if is_expand_request(user_text):
        plan = {}
        plan["explain_mode"] = True
        plan["stage_override"] = "guidance"

        plan["disable_warmup"] = True
        plan["disable_pattern_engine"] = True
        plan["disable_empathy_bridge"] = True
        plan["disable_option_close"] = True

        plan["max_questions"] = 0
        plan["max_practices"] = 1
        plan.setdefault("max_lenses", 2)

        return plan

    # ТОЛЬКО ПОСЛЕ answer-first и explain: warmup rules, uncertainty rules, small talk
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

    # Страховка: answer_first → pattern_engine жёстко выключен
    if plan.get("answer_first_required"):
        plan["disable_pattern_engine"] = True

    return plan
