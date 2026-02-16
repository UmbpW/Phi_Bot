"""Pattern Governor v12 + v17.2: cooldowns, philosophy pipeline priority."""

import random
from typing import Any, Optional

from router import detect_financial_pattern
from intent_capabilities import detect_capabilities_intent, CAPABILITIES_REPLY_RU
from utils.is_philosophy_question import (
    is_direct_philosophy_intent,
    is_philosophy_question as _is_philosophy_question,
)
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


# FIX C: pragmatic triggers — не афоризмы-осколки, не короткие паттерны
PRAGMATIC_TRIGGERS = (
    "конкретно", "конкретик", "конкрет", "по делу", "хватит", "перестань",
    "не надо философии", "без философии", "не коротко", "почему так коротко",
    "какой толк", "формальная фраза", "ты меня не слышишь",
)
# Fix Pack B: раздражение на короткие ответы → disable pattern + short
IRRITATION_SHORT_TRIGGERS = (
    "коротко", "обрывки", "формально", "шаблон",
)

FULL_Q_MARKERS = [
    "что делать", "не понимаю", "не получается", "помоги", "как быть",
    "как выйти", "устал", "тревож", "боюсь", "пустот", "смысл", "один",
    "деньги", "финанс", "отношен", "выбор", "решени", "нет сил",
    "плохо", "тупик", "завал", "депресс", "паник", "страх",
]

# FIX D: answer-first для "как/что делать" + темы состояния
STATE_TOPIC_MARKERS = (
    "сон", "бессонниц", "уснуть", "мысли не дают", "злость", "тревога", "паника",
    "апатия", "плохо", "устал", "разбит", "ничего не хочу",
)
ACTION_OPENERS = ("как ", "что делать", "что с этим", "помоги", "объясни", "расскажи", "почему")

# Fix Pack D: structure/steps markers → guidance, no triage
STRUCTURE_STEPS_MARKERS = (
    "дай модель", "дай шаги", "по делу", "без воды", "структура", "next steps",
    "план", "чек-лист", "приоритизируй", "только конкретика", "убери воду",
    "модель и шаги", "без коуч", "конкретика", "по номерам",
    "добавь философскую рамку", "философскую рамку", "не поддержка",
)

# Fix Pack D: religious markers → philosophy_pipeline, disable warmup
RELIGIOUS_MARKERS = (
    "бог", "господ", "грех", "молитв", "церков", "ислам", "коран", "библи",
    "православ", "катол", "конфесс", "пастор", "имам", "священ",
)

# Fix Pack D: Buddhism/tradition switch → explain_mode + philosophy_pipeline
BUDDHISM_SWITCH_MARKERS = (
    "через буддийскую", "через буддизм", "буддийская оптика", "буддийск",
    "не стоически, а", "не стоическ", "а через",
)


def _has_structure_steps_marker(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(m in t for m in STRUCTURE_STEPS_MARKERS)


def _has_religious_marker(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(m in t for m in RELIGIOUS_MARKERS)


def _has_buddhism_switch(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(m in t for m in BUDDHISM_SWITCH_MARKERS)


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


def _has_pragmatic_trigger(text: str) -> bool:
    """FIX C: пользователь хочет конкретики, не афоризмов."""
    t = (text or "").strip().lower()
    return any(tr in t for tr in PRAGMATIC_TRIGGERS)


def _is_action_state_request(text: str) -> bool:
    """FIX D: 'как/что делать/помоги' + темы состояния → answer-first, без triage."""
    t = (text or "").strip().lower()
    has_opener = any(o in t for o in ACTION_OPENERS)
    has_state = any(m in t for m in STATE_TOPIC_MARKERS)
    return has_opener and has_state


def _is_philosophy_chat_request(text: str) -> bool:
    """FIX D: 'давай просто поговорим про философию' → philosophy_pipeline, без triage."""
    t = (text or "").strip().lower()
    return "давай просто поговорим про философию" in t or "как разные традиции смотрят на" in t


def governor_plan(
    user_id: int,
    stage: str,
    user_text: str,
    context: dict,
    state: dict,
) -> dict:
    """Возвращает план для pattern engine."""
    # CAPABILITIES INTENT: "что ты умеешь / чем полезен" → canned reply, без warmup
    cap = detect_capabilities_intent(user_text)
    if cap.is_capabilities:
        return {
            "stage_override": "guidance",
            "answer_first_required": True,
            "disable_warmup": True,
            "disable_fork": True,
            "disable_option_close": True,
            "max_questions": 0,
            "max_practices": 0,
            "intent": "capabilities",
            "cap_score": cap.score,
            "direct_reply_text": CAPABILITIES_REPLY_RU,
        }

    # Fix Pack D: Buddhism/tradition switch → explain_mode + philosophy_pipeline (highest priority)
    if _has_buddhism_switch(user_text):
        return {
            "explain_mode": True,
            "philosophy_pipeline": True,
            "stage_override": "guidance",
            "disable_warmup": True,
            "disable_pattern_engine": True,
            "disable_option_close": True,
            "disable_short_mode": True,
            "answer_first_required": True,
            "max_questions": 1,
            "max_practices": 1,
        }

    # Fix Pack D: structure/steps markers → guidance, no triage
    if _has_structure_steps_marker(user_text):
        allows_phi = any(k in (user_text or "").lower() for k in ("философ", "рамк", "модель", "оптик"))
        return {
            "stage_override": "guidance",
            "answer_first_required": True,
            "disable_warmup": True,
            "disable_option_close": True,
            "disable_fork": True,
            "disable_pattern_engine": True,
            "max_questions": 1,
            "max_practices": 1,
            "philosophy_pipeline": allows_phi,
        }

    # Fix Pack D: religious markers → philosophy_pipeline, disable warmup
    if _has_religious_marker(user_text):
        return {
            "philosophy_pipeline": True,
            "allow_philosophy_examples": True,
            "stage_override": "guidance",
            "disable_warmup": True,
            "answer_first_required": True,
            "disable_pattern_engine": True,
            "max_questions": 1,
        }

    # FIX C: pragmatic triggers — disable pattern_engine
    if _has_pragmatic_trigger(user_text):
        return {
            "disable_pattern_engine": True,
            "disable_option_close": True,
            "disable_fork": True,
            "stage_override": "guidance",
            "answer_first_required": True,
            "disable_warmup": True,
        }

    # FIX D: action + state topic → answer-first, no triage
    if _is_action_state_request(user_text):
        return {
            "stage_override": "guidance",
            "answer_first_required": True,
            "disable_warmup": True,
            "disable_pattern_engine": True,
            "max_questions": 1,
        }

    # FIX D: philosophy chat request
    if _is_philosophy_chat_request(user_text):
        return {
            "stage_override": "guidance",
            "philosophy_pipeline": True,
            "disable_warmup": True,
            "disable_pattern_engine": True,
            "max_questions": 1,
        }

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

    # PATCH 5 + Fix Pack B: explain_mode — запросы на разъяснение (до warmup)
    if is_expand_request(user_text):
        plan = {}
        plan["explain_mode"] = True
        plan["stage_override"] = "guidance"
        plan["disable_warmup"] = True
        plan["disable_pattern_engine"] = True
        plan["disable_empathy_bridge"] = True
        plan["disable_option_close"] = True
        plan["disable_short_mode"] = True
        plan["max_questions"] = 1
        plan["max_practices"] = 1
        plan.setdefault("max_lenses", 2)
        return plan

    # Fix Pack B: раздражение на короткие → disable pattern, no short mode
    t_lower = (user_text or "").strip().lower()
    if any(tr in t_lower for tr in IRRITATION_SHORT_TRIGGERS):
        return {
            "disable_pattern_engine": True,
            "disable_option_close": True,
            "disable_warmup": True,
            "stage_override": "guidance",
            "answer_first_required": True,
            "disable_short_mode": True,
        }

    # Hotfix-A: direct philosophy — обход triage/orientation
    if is_direct_philosophy_intent(user_text):
        plan = {
            "force_philosophy_mode": True,
            "disable_warmup": True,
            "disable_pattern_engine": True,
            "stage_override": "guidance",
            "philosophy_pipeline": True,
            "answer_first_required": True,
            "disable_triage_patterns": True,
        }
        return plan

    # ТОЛЬКО ПОСЛЕ answer-first, explain и direct philosophy: warmup rules, uncertainty rules, small talk
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

    # FIX C: synth persona impatient_pragmatic — hates short answers
    uid_str = str(user_id)
    if "impatient_pragmatic" in uid_str:
        plan["disable_pattern_engine"] = True
        plan["disable_option_close"] = True

    return plan
