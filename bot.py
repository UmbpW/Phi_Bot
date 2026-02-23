"""
Phi Bot — Telegram-бот MVP на aiogram 3.x.
Запуск: python bot.py
"""

import asyncio
import hashlib
import logging
import os
import sys
from typing import Optional
import re
import tempfile
from pathlib import Path

# v20 telemetry — только server logs
APP_VERSION = os.getenv("APP_VERSION", "dev")
GIT_SHA = os.getenv("GIT_SHA", "unknown")
_logger = logging.getLogger("phi.telemetry")
if not _logger.handlers:
    _logger.addHandler(logging.StreamHandler())
    _logger.setLevel(logging.INFO)


def _hash_text(text: str) -> str:
    if not text:
        return "none"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]

from aiogram import Bot, Dispatcher, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.filters import CommandStart, Command
from dotenv import load_dotenv
from openai import OpenAI

from logger import (
    _get_db_conn,
    export_dialogs_from_db,
    log_dialog,
    log_event,
    log_feedback,
    log_safety_event,
)
from prompt_loader import (
    build_system_prompt,
    load_all_lenses,
    load_system_prompt,
    load_warmup_prompt,
    load_philosophy_style,
)
from router import select_lenses, detect_financial_pattern
from safety import check_safety, get_safe_response
from state_pm import pm_get_profile, pm_record_signal, pm_set_last_suggest_turn
from philosophy_map import PHILOSOPHY_MAP, pm_score_philosophies
from prompt_loader import load_file
from response_postprocess import postprocess_response
from utils.final_send_clamp import (
    add_closing_sentence,
    completion_guard,
    final_send_clamp,
    looks_incomplete,
    meta_tail_to_fork_or_close,
)
from utils.output_sanitizer import sanitize_output
from utils.send_pipeline import send_text
from utils.telegram_idempotency import IdempotencyMiddleware
from utils.state_store import load_state, save_state
from utils.short_ack import is_short_ack
from utils.context_pack import pack_context, append_history
from utils.intent_gate import (
    is_ack_close_intent,
    is_unclear_message,
    should_skip_warmup_first_turn,
    has_religion_in_orientation_context,
)
from utils.context_anchor import apply_context_anchor
from philosophy.first_turn_templates import render_first_turn_philosophy
from patterns.pattern_engine import (
    load_patterns,
    choose_pattern,
    render_pattern,
    enforce_constraints,
    build_ux_prefix,
    strip_echo_first_line,
    get_option_close_line,
)
from patterns.pattern_governor import (
    governor_plan,
    resolve_pattern_collisions,
    is_philosophy_question,
    _has_buddhism_switch,
)
from intent_philosophy_topic import detect_philosophy_topic_intent
from intent_topic_v2 import is_topic_high
from intent_philo_graph import is_philo_graph_intent, extract_names_naive
from patterns.agency_layer import (
    strip_meta_format_questions,
    term_example_first,
    should_ask_question,
    fork_density_guard,
    handle_i_dont_understand,
    is_term_question,
    remove_questions,
    replace_clarifying_with_example,
)
from philosophy.philosophy_responder import respond_philosophy_question
from philosophy.guided_path import (
    detect_lens_preview_need,
    render_lens_preview,
    render_lens_soft_question,
    detect_lens_choice,
    set_active_lens,
    tick_lens_lock,
    is_lens_locked,
    get_active_lens,
    LENS_TO_SYSTEM_ID,
)
from philosophy.natural_injection import (
    detect_stable_pattern,
    choose_philosophy_line,
    render_injection,
    should_inject,
    mark_injection_done,
    insert_injection_after_first_paragraph,
)
from philosophy.recommendation_pause import (
    detect_recommendation,
    apply_recommendation_pause,
)
from philosophy.style_guards import clamp_questions, strip_meta_tail, apply_style_guards
from response_postprocess import format_readability_ru
from semantic_blocks import format_reply_md
from philosophy.practice_cooldown import (
    strip_practice_content,
    contains_practice,
    tick_practice_cooldown,
    COOLDOWN_AFTER_PRACTICE,
    clamp_to_first_practice_only,
)

# PhiloBase v1: lazy-loaded philosophy graph DB
_PHILO_DB = None


def get_philo_db():
    """Lazy singleton for PhiloDB (Wikidata-sourced philosophy graph)."""
    global _PHILO_DB
    if _PHILO_DB is None:
        try:
            from eval.philo.query import PhiloDB
            path = os.environ.get("PHILO_DB_PATH", "eval/philo/philo_db.yaml")
            _PHILO_DB = PhiloDB(path)
        except Exception:
            _PHILO_DB = False  # placeholder when DB missing
    return _PHILO_DB if _PHILO_DB else None


def try_graph_answer_ru(text: str) -> Optional[str]:
    """Optional: when user names two philosophers, try shortest_path. Return None if unsure."""
    from intent_philo_graph import RU_TO_EN_PHILO

    db = get_philo_db()
    if not db or not db.nodes:
        return None
    names = extract_names_naive(text or "")
    if len(names) < 2:
        return None
    candidates = []
    for n in names[:2]:
        key = (n or "").strip().lower()
        found = db.find_by_name(n)
        if found:
            candidates.append(found[0]["id"])
            continue
        en_key = RU_TO_EN_PHILO.get(key)
        search = en_key if en_key else key
        for node in db.nodes.values():
            if search in node["name"].lower():
                candidates.append(node["id"])
                break
        else:
            return None
    if len(candidates) != 2:
        return None
    path = db.shortest_path(candidates[0], candidates[1])
    if not path:
        return None
    nodes = [db.nodes[i]["name"] for i in path]
    return f"[PhiloDB path] {' → '.join(nodes)}"


BOT_VERSION = "Phi_Bot v21.4-meta-tail-to-fork"


def finalize_reply(text: str, plan: Optional[dict] = None) -> str:
    """Fix Pack B + PATCH F + PATCH G: unified postprocess.
    Порядок: strip_meta_tail → format_reply_md (semantic blocks) → clamp_practice → style_guards
    → completion_guard → meta_tail_to_fork → clamp_questions → readability."""
    if plan is None:
        plan = {}
    out = (text or "").strip()
    if not out:
        return out
    out = strip_meta_tail(out)
    # PATCH G: semantic blocks Markdown (longform/explain/philosophy only)
    out, blocks_used = format_reply_md(out, plan)
    plan["blocks_used"] = blocks_used
    out = clamp_to_first_practice_only(out)
    ban_empathy = plan.get("philosophy_pipeline") or plan.get("answer_first_required") or plan.get("explain_mode")
    out = apply_style_guards(out, ban_empathy_openers=ban_empathy, answer_first=plan.get("answer_first_required", False))
    out = completion_guard(out, max_questions=plan.get("max_questions", 1))
    out = meta_tail_to_fork_or_close(out, max_questions=plan.get("max_questions", 1))
    out = clamp_questions(out, max_questions=plan.get("max_questions", 1))
    # PATCH F: readability formatter ПОСЛЕДНИМ — clamp_questions использует " ".join() и затирает переносы
    if not plan.get("disable_readability_formatter"):
        out = format_readability_ru(out)
    return out.strip()

DEBUG = os.getenv("DEBUG", "0") == "1"

# Feature flags
ENABLE_TOOLS_CMD = True
ENABLE_LENS_CMD = True
ENABLE_SESSION_CLOSE_CHOICE = True
ENABLE_PHILOSOPHY_MATCH = True
ENABLE_PATTERN_ENGINE = True
PM_MIN_TURNS = 5
PM_MIN_CONFIDENCE = 0.6
PM_COOLDOWN_TURNS = 25

# Stage machine v8: warmup | guidance
USER_STAGE: dict[int, str] = {}
USER_MSG_COUNT: dict[int, int] = {}
LAST_LENS_BY_USER: dict[int, list[str]] = {}  # последние линзы для /lens

# Governor state v12 + pending follow-through v14
USER_STATE: dict[int, dict] = {}  # turn_index, last_bridge_turn, last_options, pending, ...
HISTORY_STORE: dict[int, list] = {}  # user_id -> [{"role":"user"|"assistant","content":...}]

# Человекочитаемые названия линз
LENS_NAMES: dict[str, str] = {
    "lens_micro_agency": "Мини-действие",
    "lens_control_scope": "Зона контроля",
    "lens_boundary": "Границы",
    "lens_expectation_gap": "Разрыв ожиданий",
    "lens_finance_rhythm": "Финансовый ритм",
    "lens_role_position": "Роль и позиция",
    "lens_narrative": "Сюжет",
    "lens_mortality_focus": "Время и выбор",
}

META_LECTURE_PATTERNS = (
    "скажу честно", "по философии", "как учит", "правильный взгляд",
    "согласно учению", "в философии", "философы считают",
)

GUIDANCE_TRIGGERS = (
    "что делать", "как быть", "что делать дальше", "помоги решить",
    "что мне делать", "подскажи что", "посоветуй что",
)

RESISTANCE_TRIGGERS = (
    "зачем отвечать", "зачем ты", "не хочу отвечать", "не буду отвечать",
    "зачем это", "не буду",
)
CONFUSION_TRIGGERS = (
    "не понимаю", "запутался", "неясно", "не знаю что", "не понятно",
)

# Загрузка .env из папки Phi_Bot
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

TELEGRAM_TOKEN = (os.getenv("TELEGRAM_TOKEN") or "").strip()
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = (os.getenv("OPENAI_MODEL") or "gpt-5.2").strip()
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
EXPORT_TOKEN = (os.getenv("EXPORT_TOKEN") or "").strip()

if not os.getenv("PHI_EVAL") and not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не задан в .env")
# Eval mode: placeholder token (9 digits:35 chars) — бот не используется для отправки
if os.getenv("PHI_EVAL") and not TELEGRAM_TOKEN:
    TELEGRAM_TOKEN = "111111111:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не задан в .env")

def _health_payload() -> dict:
    """v20: /health endpoint payload (только server-side)."""
    try:
        sp = load_system_prompt()
        sp_hash = _hash_text(sp)
    except Exception:
        sp_hash = "load_error"
    return {
        "status": "ok",
        "app_version": APP_VERSION,
        "git_sha": GIT_SHA,
        "openai_model": os.getenv("OPENAI_MODEL"),
        "system_prompt_hash": sp_hash,
    }


bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
dp.update.outer_middleware(IdempotencyMiddleware())
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Кнопки фидбека
FEEDBACK_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="👍 Полезно", callback_data="fb_useful"),
            InlineKeyboardButton(text="👎 Не полезно", callback_data="fb_not_useful"),
        ]
    ]
)


def transcribe_voice(audio_path: Path) -> str:
    """Транскрибирует голосовое через OpenAI Whisper."""
    try:
        with open(audio_path, "rb") as f:
            transcription = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="ru",
            )
        return (transcription.text or "").strip()
    except Exception as e:
        return f"[Ошибка распознавания: {e}]"


def _explain_mode_instructions_ru() -> str:
    """PATCH F + PATCH G: инструкция для режима разъяснения + blocks contract."""
    return (
        "Пользователь просит разъяснение. Сделай ответ более развернутым и понятным: "
        "1) кратко переформулируй, что именно объясняешь; "
        "2) разложи на 2–4 смысловых блока; "
        "3) дай 1 короткий пример; "
        "4) завершай без вопросов. "
        "Пиши читабельно: абзацы и маркеры, без полотна. "
        "Тон: живой, спокойный, без формальностей и без давления.\n\n"
        "---\n"
        "[EXPLAIN_MODE_BLOCKS_CONTRACT] Если пользователь просит «объясни», «разбери», «шире», «покажи варианты», «сравни», «поясни детальнее»: "
        "1) Сформируй ответ как семантические блоки в JSON и помести его строго между тегами: <BLOCKS_JSON> ... </BLOCKS_JSON> "
        "2) Схема JSON: {\"lead\": \"1–2 предложения по сути\", \"sections\": [{\"title\": \"Заголовок\", \"body\": \"2–5 предложений\", \"bullets\": []}], "
        "\"bridge\": null, \"question\": \"опционально один финальный вопрос\"} "
        "3) Никаких других тегов, никакого второго дублирующего блока. "
        "4) Не добавляй мета-фразы про «рамки», «оптики», «сейчас разберём философски» — начинай по делу."
    )


def _get_stage(user_id: int, user_text: str) -> str:
    """Возвращает stage: warmup или guidance."""
    count = USER_MSG_COUNT.get(user_id, 0)
    text_lower = (user_text or "").lower().strip()
    if any(tr in text_lower for tr in GUIDANCE_TRIGGERS):
        return "guidance"
    if count <= 1:
        return "warmup"
    return "guidance"


EXISTENTIAL_KEYWORDS = (
    "бессмыслен", "пустота", "пусто", "экзистенциальн", "зачем жить",
    "выгоран", "перегруз", "ничего не хочу", "нет сил", "устал от всего",
)


def _is_existential(user_text: str) -> bool:
    """Проверяет экзистенциальный контекст запроса."""
    t = (user_text or "").lower()
    return any(kw in t for kw in EXISTENTIAL_KEYWORDS)


def _trim_existential(text: str) -> str:
    """Ограничение: не более 2 философских рамок, каждая ≤2 предложения."""
    if not text:
        return text
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    result = []
    for block in blocks[:2]:
        sentences = re.split(r"(?<=[.!?])\s+", block)[:2]
        result.append(" ".join(s.strip() for s in sentences if s.strip()))
    return "\n\n".join(result) if result else text


def _is_meta_lecture(text: str) -> bool:
    """Проверяет мета-лекционный тон."""
    if not text or len(text) < 100:
        return False
    t = text.lower()
    if t.count("\n") > 12:  # >14 строк
        return True
    return any(p in t for p in META_LECTURE_PATTERNS)


def _extract_response_text(response) -> str:
    """Извлекает текст из response OpenAI."""
    if hasattr(response, "output_text") and response.output_text:
        return str(response.output_text).strip()
    text_parts = []
    if hasattr(response, "output") and response.output:
        for item in response.output:
            content = getattr(item, "content", None) or []
            for block in content:
                text = getattr(block, "text", None)
                if text:
                    text_parts.append(str(text))
    result = "\n".join(text_parts).strip() if text_parts else ""
    return result or "Не удалось получить ответ."


def _approx_tokens_from_text(s: str) -> int:
    """Грубая оценка: ~4 символа на токен для RU/EN микса."""
    if not s:
        return 0
    return max(1, (len(s) + 3) // 4)


def _cache_salt() -> str:
    """FIX V1.2: соль для кэша — меняется при смене системного промпта или кода."""
    sp = os.getenv("SYSTEM_PROMPT_HASH", "").strip()
    sha = os.getenv("GIT_SHA", "").strip()
    appv = os.getenv("APP_VERSION", "").strip()
    parts = [p for p in [sp, sha, appv] if p]
    return "|".join(parts) if parts else "nosalt"


def _extract_usage(response, inst: str, input_text: str, output_text: str) -> dict:
    """Извлекает usage из response; при отсутствии — приблизительная оценка."""
    usage = {}
    usage_obj = getattr(response, "usage", None)
    if usage_obj:
        usage = {
            "input_tokens": getattr(usage_obj, "input_tokens", None) or getattr(usage_obj, "input_tokens_count", None),
            "output_tokens": getattr(usage_obj, "output_tokens", None) or getattr(usage_obj, "output_tokens_count", None),
            "total_tokens": getattr(usage_obj, "total_tokens", None) or getattr(usage_obj, "total_tokens_count", None),
        }
    if not usage.get("input_tokens"):
        usage["input_tokens"] = _approx_tokens_from_text(inst) + _approx_tokens_from_text(input_text)
    if not usage.get("output_tokens"):
        usage["output_tokens"] = _approx_tokens_from_text(output_text)
    if not usage.get("total_tokens"):
        usage["total_tokens"] = (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)
    return usage


# TEST COST OPTIMIZER V1.1: список метаданных вызовов LLM для телеметрии (очищается в начале каждого generate_reply_core)
EVAL_CALL_METAS: list = []


# E1.1: cost control — eval can skip LLM intent classifier for topic_mid
EVAL_SKIP_LLM_INTENT = os.getenv("EVAL_SKIP_LLM_INTENT", "0") == "1"


def llm_classify_topic_intent(user_text: str) -> bool:
    """PATCH E: cheap intent classifier via mini model — философско-понятийный вопрос?"""
    if EVAL_SKIP_LLM_INTENT:
        return False
    t = (user_text or "").strip()
    if not t:
        return False
    key_obj = {"ns": "intent_topic_llm", "v": 1, "text": t.lower()}
    cache_dir = os.getenv("EVAL_CACHE_DIR", "eval/cache").strip()
    try:
        from eval.llm_cache import cache_get, cache_put
        hit = cache_get(cache_dir, key_obj)
        if hit is not None and isinstance(hit, dict):
            return hit.get("is_topic", False)
    except Exception:
        pass
    instructions = (
        "Классифицируй запрос пользователя. "
        "Это философско-понятийный вопрос (объяснить идею, школу, концепт, взгляд философии)? "
        "Ответ только JSON: {\"is_topic\": true} или {\"is_topic\": false}"
    )
    model = os.getenv("INTENT_CLASSIFIER_MODEL", "gpt-4o-mini")
    try:
        response = openai_client.responses.create(
            model=model,
            instructions=instructions,
            input=t,
            max_output_tokens=20,
        )
        text = (_extract_response_text(response) or "").strip().lower()
        is_topic = bool(re.search(r'is_topic["\']?\s*:\s*true', text))
    except Exception:
        is_topic = False
    try:
        from eval.llm_cache import cache_put
        cache_put(cache_dir, key_obj, {"is_topic": is_topic})
    except Exception:
        pass
    return is_topic


def call_openai(
    system_prompt: str,
    user_text: str,
    force_short: bool = False,
    context_block: str = "",
) -> str:
    """Вызывает OpenAI Responses API. context_block — упакованный контекст диалога.
    TEST COST OPTIMIZER V1: при EVAL_CACHE_DIR — кэш; при EVAL_MODEL — модель; при EVAL_MAX_TOKENS — лимит."""
    model_name = os.getenv("EVAL_MODEL") or OPENAI_MODEL
    inst = system_prompt
    if force_short:
        inst += "\n\nОтветь короче и разговорнее. Без лекций."
    input_text = user_text
    if context_block:
        input_text = f"[Контекст диалога]\n{context_block}\n\n[Текущее сообщение]\n{user_text}"

    cache_dir = os.getenv("EVAL_CACHE_DIR", "").strip()
    use_cache = bool(cache_dir) and os.getenv("EVAL_USE_CACHE", "1") != "0"
    max_tokens_env = os.getenv("EVAL_MAX_TOKENS")
    max_output_tokens = int(max_tokens_env) if max_tokens_env and max_tokens_env.isdigit() else None

    key_obj = {
        "salt": _cache_salt(),
        "ns": "bot",
        "model": model_name,
        "instructions": inst,
        "input": input_text,
        "force_short": force_short,
    }
    if use_cache:
        try:
            from eval.llm_cache import cache_get, cache_put
            hit = cache_get(cache_dir, key_obj)
            if hit and isinstance(hit, dict) and "text" in hit:
                meta = {"cached_hit": True, "model": model_name, "usage": hit.get("usage", {})}
                if os.getenv("EVAL_CACHE_DIR"):
                    EVAL_CALL_METAS.append(meta)
                return hit["text"]
        except Exception:
            pass

    kwargs = {"model": model_name, "instructions": inst, "input": input_text}
    if max_output_tokens:
        kwargs["max_output_tokens"] = max_output_tokens

    try:
        response = openai_client.responses.create(**kwargs)
        text = _extract_response_text(response)
        usage = _extract_usage(response, inst, input_text, text)
        if use_cache:
            try:
                from eval.llm_cache import cache_put
                cache_put(cache_dir, key_obj, {"text": text, "usage": usage})
            except Exception:
                pass
        if os.getenv("EVAL_CACHE_DIR"):
            EVAL_CALL_METAS.append({"cached_hit": False, "model": model_name, "usage": usage})
        return text
    except Exception as e:
        if DEBUG:
            print(f"[Phi] model {model_name} failed, fallback to gpt-5.2-mini: {e}")
        if os.getenv("EVAL_MODEL"):
            raise
        try:
            fallback_model = "gpt-5.2-mini"
            response = openai_client.responses.create(
                model=fallback_model,
                instructions=inst,
                input=input_text,
            )
            text = _extract_response_text(response)
            usage = _extract_usage(response, inst, input_text, text)
            if os.getenv("EVAL_CACHE_DIR"):
                EVAL_CALL_METAS.append({"cached_hit": False, "model": fallback_model, "usage": usage})
            return text
        except Exception as e2:
            return f"Ошибка API: {str(e2)}"


TOOLS_MENU = """Инструменты Phi Bot

1) Зона контроля — разделить «влияю / не влияю». Когда хаос, перегруз, много всего.
2) Мини-агентность — один шаг на 5 минут. Когда не могу начать, нет сил.
3) Границы — одна фраза «да / нет / не сейчас». Когда давят, требуют.
4) Разрыв ожиданий — «ожидал / получил». Когда разочарование, не оправдалось.
5) Роль и позиция — участник / наблюдатель / лидер. Когда не знаю как поступить.
6) Сюжет — «это глава, не вся книга». Когда я такой, всегда так, самооценка.

Напиши: «хочу инструмент 2» — и я разверну его."""

# BUG2: ack/close — короткий ответ без triage
ACK_CLOSE_REPLY_RU = "Хорошо. Если захочешь продолжить разговор — напиши."

# PATCH 6: Orientation fallback — мягкий вход для расплывчатых сообщений
ORIENTATION_MESSAGE_RU = (
    "Слышу, что сейчас непросто. Чтобы не стрелять советами мимо, давай выберем угол.\n\n"
    "Обычно такие вещи лежат в одной из трёх зон:\n"
    "— **Состояние**: тревога, усталость, злость, апатия, бессонница.\n"
    "— **Смысл/выбор**: зачем жить, что важно, как решаться, куда идти.\n"
    "— **Опора/мировоззрение**: во что верить, как держаться, как разные традиции смотрят на это.\n\n"
    "Напиши одно слово: **состояние**, **смысл** или **опора** — и я продолжу в этом направлении."
)


def _state_to_persist() -> dict:
    """Собрать state для сохранения на диск. FIX A: synth user_id не персистим."""
    import time
    out = {}
    for uid, state in USER_STATE.items():
        if str(uid).startswith("synth:"):
            continue
        stage = USER_STAGE.get(uid, "warmup")
        out[str(uid)] = {
            "stage": stage,
            "msg_count": USER_MSG_COUNT.get(uid, 0),
            "turn_index": state.get("turn_index", 0),
            "guidance_turns_count": state.get("guidance_turns_count", 0),
            "last_fork_turn": state.get("last_fork_turn", -10),
            "last_bridge_turn": state.get("last_bridge_turn", -10),
            "last_options": state.get("last_options"),
            "pending": state.get("pending"),
            "last_user_text": state.get("last_user_text", ""),
            "last_bot_text": state.get("last_bot_text", ""),
            # v17 Philosophy Guided Path + Natural Injection
            "active_lens": state.get("active_lens"),
            "lens_lock_turns_left": state.get("lens_lock_turns_left", 0),
            "last_injection_turn": state.get("last_injection_turn", -10),
            "active_philosophy_line": state.get("active_philosophy_line"),
            "practice_cooldown_turns": state.get("practice_cooldown_turns", 0),
            "last_lens_preview_turn": state.get("last_lens_preview_turn"),
            "user_language": state.get("user_language"),
            "onboarding_shown": state.get("onboarding_shown"),
            "pending_orientation": state.get("pending_orientation"),
            "orientation_lock": state.get("orientation_lock"),
            "force_expand_next": state.get("force_expand_next"),
            "last_updated": time.time(),
        }
    return out


def _execute_pending_follow_through(
    user_id: int,
    user_text: str,
    state: dict,
) -> Optional[str]:
    """Если short_ack + pending активен: выполнить follow-through, вернуть reply_text. Иначе None."""
    pending = state.get("pending")
    if not pending:
        return None
    created = pending.get("created_turn", 0)
    if state.get("turn_index", 0) - created > 6:
        state["pending"] = None
        return None

    kind = pending.get("kind", "")
    prompt = pending.get("prompt", "")
    options = pending.get("options") or []
    default = pending.get("default") or (options[0] if options else None)

    if kind == "fork":
        choice = default or (options[0] if options else "option_1")
        # Короткий ответ по выбранной ветке
        main_prompt = load_system_prompt()
        ctx = f"Контекст: {prompt[:200]}. Пользователь выбрал '{choice}'. Дай 2–4 предложения по этой ветке. Без нового вопроса о выборе."
        reply = call_openai(main_prompt, ctx, force_short=True)
        reply = postprocess_response(reply, "guidance")
        state["pending"] = None
        return reply
    if kind == "offer_action":
        # Один микро-шаг по контексту
        main_prompt = load_system_prompt()
        ctx = f"Контекст: {prompt[:200]}. Дай 1 конкретный микро-шаг (что сделать сейчас). Максимум 1 вопрос по содержанию."
        reply = call_openai(main_prompt, ctx, force_short=True)
        reply = postprocess_response(reply, "guidance")
        state["pending"] = None
        return reply
    if kind == "question":
        # Продолжить по контексту последнего бота
        last_bot = state.get("last_bot_text", "")[:300]
        if last_bot:
            main_prompt = load_system_prompt()
            ctx = f"Предыдущий вопрос/предложение бота: {last_bot}. Пользователь согласился. Продолжи диалог — 1 шаг или уточнение."
            reply = call_openai(main_prompt, ctx, force_short=True)
            reply = postprocess_response(reply, "guidance")
            state["pending"] = None
            return reply
    state["pending"] = None
    return None


def _load_persisted_state() -> None:
    """Загрузить state с диска в USER_STATE, USER_STAGE, USER_MSG_COUNT."""
    data = load_state()
    for uid_str, blob in data.items():
        try:
            uid = int(uid_str)
        except (ValueError, TypeError):
            continue
        USER_STAGE[uid] = blob.get("stage", "warmup")
        USER_MSG_COUNT[uid] = blob.get("msg_count", 0)
        USER_STATE[uid] = {
            "turn_index": blob.get("turn_index", 0),
            "last_bridge_turn": blob.get("last_bridge_turn", -10),
            "last_options": blob.get("last_options"),
            "guidance_turns_count": blob.get("guidance_turns_count", 0),
            "last_fork_turn": blob.get("last_fork_turn", -10),
            "pending": blob.get("pending"),
            "last_user_text": blob.get("last_user_text", ""),
            "last_bot_text": blob.get("last_bot_text", ""),
            # v17
            "active_lens": blob.get("active_lens"),
            "lens_lock_turns_left": blob.get("lens_lock_turns_left", 0),
            "last_injection_turn": blob.get("last_injection_turn", -10),
            "active_philosophy_line": blob.get("active_philosophy_line"),
            "practice_cooldown_turns": blob.get("practice_cooldown_turns", 0),
            "last_lens_preview_turn": blob.get("last_lens_preview_turn"),
            "user_language": blob.get("user_language"),
            "onboarding_shown": blob.get("onboarding_shown"),
            "pending_orientation": blob.get("pending_orientation", False),
            "orientation_lock": blob.get("orientation_lock", False),
            "force_expand_next": blob.get("force_expand_next", False),
        }


ONBOARDING_MESSAGE_RU = """
Привет. Это философский диалог-бот.

Здесь можно говорить:
— о смысле, тревоге, выборе, усталости, деньгах, отношениях
— о философских подходах: стоицизм, экзистенциализм, буддизм и других
— о сложных жизненных ситуациях и внутренних вопросах

Я отвечаю не лозунгами и не "универсальными советами", а через понятные рамки и разные философские оптики.

Примеры:
— «Меня тревожат деньги, хотя доход нормальный — разберём?»
— «Как стоики смотрят на страх смерти?»
— «Ответь на мою ситуацию через буддизм / через стоиков»

Можно просто описать, что происходит — даже если вопрос пока не сформулирован.
"""

ABOUT_TEXT = (
    "Этот бот — секулярный философский агент поддержки.\n"
    "Он помогает размышлять и находить опору через философские рамки и вопросы.\n\n"
    "Это не психотерапия и не медицинская помощь.\n"
    "Если у вас кризисное состояние или риск причинить себе вред — важно обратиться к живому специалисту или в местные службы помощи.\n\n"
    "Бот работает в тестовом режиме."
)


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Приветствие по /start. Онбординг — только пример работы бота, не часть диалога.
    Если после /start идёт текст (/start привет) — после онбординга обрабатываем хвост как обычное сообщение."""
    uid = message.from_user.id if message.from_user else 0
    # Хвост: /start привет → tail = "привет"
    raw = (message.text or "").strip()
    parts = raw.split(None, 1)
    tail = (parts[1].strip() if len(parts) > 1 else "") or ""
    # Онбординг не считается первым ответом: очищаем историю, диалог начинается с нуля
    if uid in HISTORY_STORE:
        HISTORY_STORE[uid] = []
    USER_STAGE[uid] = "warmup"
    USER_MSG_COUNT[uid] = 0
    USER_STATE[uid] = {
        "turn_index": 0,
        "last_bridge_turn": -10,
        "last_options": None,
        "guidance_turns_count": 0,
        "last_fork_turn": -10,
        "pending": None,
        "last_user_text": "",
        "last_bot_text": "",
        "active_lens": None,
        "lens_lock_turns_left": 0,
        "last_injection_turn": -10,
        "active_philosophy_line": None,
        "practice_cooldown_turns": 0,
        "last_lens_preview_turn": None,
        "onboarding_shown": True,
        "pending_orientation": False,
    }
    save_state(_state_to_persist())
    log_event("onboarding_shown", user_id=uid)
    await send_text(bot, message.chat.id, ONBOARDING_MESSAGE_RU.strip())
    if tail:
        await process_user_query(message, tail, update_id=None)


@dp.message(Command("about"))
async def cmd_about(message: Message) -> None:
    """Дисклеймер и описание бота."""
    await send_text(bot, message.chat.id, ABOUT_TEXT)


@dp.message(Command("version"))
async def cmd_version(message: Message) -> None:
    """Версия бота."""
    await send_text(bot, message.chat.id, BOT_VERSION)


@dp.message(Command("tools"))
async def cmd_tools(message: Message) -> None:
    """Меню инструментов (6 пунктов)."""
    if not ENABLE_TOOLS_CMD:
        await send_text(bot, message.chat.id, "Команда отключена.")
        return
    await send_text(bot, message.chat.id, TOOLS_MENU)


@dp.message(Command("lens"))
async def cmd_lens(message: Message) -> None:
    """Текущая линза, stage, альтернативы."""
    if not ENABLE_LENS_CMD:
        await send_text(bot, message.chat.id, "Команда отключена.")
        return
    uid = message.from_user.id if message.from_user else 0
    stage = USER_STAGE.get(uid, "—")
    last_lenses = LAST_LENS_BY_USER.get(uid)
    popular = ["lens_control_scope", "lens_micro_agency", "lens_boundary"]
    if last_lenses:
        current = LENS_NAMES.get(last_lenses[0], last_lenses[0])
        alts = [LENS_NAMES.get(n, n) for n in last_lenses[1:3]]
        for p in popular:
            if len(alts) >= 2:
                break
            name = LENS_NAMES.get(p, p)
            if name not in alts and p not in last_lenses:
                alts.append(name)
    else:
        current = "—"
        alts = [LENS_NAMES.get(p, p) for p in popular[:3]]
    lines = [
        f"Текущая линза: {current}",
        f"Stage: {stage}",
        f"Альтернативы: {', '.join(alts[:2])}",
    ]
    await send_text(bot, message.chat.id, "\n".join(lines))


@dp.message(Command("philosophy"))
async def cmd_philosophy(message: Message) -> None:
    """Лучшая философия по текущему профилю или «мало сигналов»."""
    if not ENABLE_PHILOSOPHY_MATCH:
        await send_text(bot, message.chat.id, "Функция отключена.")
        return
    uid = message.from_user.id if message.from_user else 0
    profile = pm_get_profile(uid)
    pid, conf = pm_score_philosophies(profile)
    if not pid or conf < PM_MIN_CONFIDENCE:
        await send_text(bot, message.chat.id, "Пока мало сигналов — продолжим диалог.")
        return
    card_path = PROJECT_ROOT / PHILOSOPHY_MAP[pid]["card"]
    text = load_file(card_path) if card_path.exists() else ""
    if not text:
        await send_text(bot, message.chat.id, "Пока мало сигналов — продолжим диалог.")
        return
    await send_text(bot, message.chat.id, "Кажется, тебе может откликнуться такая оптика:\n\n" + text)


def _maybe_suggest_philosophy_match(
    user_id: int,
    stage: str,
    is_safety: bool,
):
    """Возвращает текст подсказки философской оптики или None."""
    if not ENABLE_PHILOSOPHY_MATCH or stage != "guidance" or is_safety:
        return None
    profile = pm_get_profile(user_id)
    if profile["turns"] < PM_MIN_TURNS:
        return None
    if profile["turns"] - profile.get("last_suggest_turn", 0) < PM_COOLDOWN_TURNS:
        return None
    pid, conf = pm_score_philosophies(profile)
    if not pid or conf < PM_MIN_CONFIDENCE:
        return None
    card_path = PROJECT_ROOT / PHILOSOPHY_MAP[pid]["card"]
    text = load_file(card_path) if card_path.exists() else ""
    if not text:
        return None
    pm_set_last_suggest_turn(user_id, profile["turns"])
    return "Кажется, тебе может откликнуться такая философская оптика:\n\n" + text


def generate_reply_core(user_id: int, user_text: str) -> dict:
    """Headless pipeline: router → lenses → postprocess → completion_guard.

    Возвращает: {"reply_text": str, "telemetry": dict, "mode": str|None, "stage": str|None}
    Использует глобальные USER_STATE, HISTORY_STORE, USER_STAGE, USER_MSG_COUNT, LAST_LENS_BY_USER.
    Вызывается из process_user_query и из eval/run_synth_simulation.
    TEST COST OPTIMIZER V1.1: в eval очищает EVAL_CALL_METAS для телеметрии.
    """
    if os.getenv("EVAL_CACHE_DIR"):
        EVAL_CALL_METAS.clear()
    if not user_text:
        return {"reply_text": "Не удалось распознать текст.", "telemetry": {}, "mode": None, "stage": None}
    state = USER_STATE.get(user_id)
    if not state:
        return {"reply_text": "[Ошибка: нет state]", "telemetry": {}, "mode": None, "stage": None}

    if is_short_ack(user_text) and state.get("pending"):
        reply_text = _execute_pending_follow_through(user_id, user_text, state)
        if reply_text:
            append_history(HISTORY_STORE, user_id, "user", user_text)
            state["last_user_text"] = user_text
            state["last_bot_text"] = reply_text
            append_history(HISTORY_STORE, user_id, "assistant", reply_text)
            return {"reply_text": finalize_reply(reply_text, {}), "telemetry": {"stage": "guidance", "intent": "short_ack"}, "mode": None, "stage": "guidance"}

    if check_safety(user_text):
        safe_text = get_safe_response()
        return {"reply_text": finalize_reply(safe_text, {"max_questions": 1}), "telemetry": {"stage": "safety", "intent": "safety"}, "mode": None, "stage": "safety"}

    history_count = len(HISTORY_STORE.get(user_id, []))
    current_stage = USER_STAGE.get(user_id)
    # FIX: концептуальные вопросы (бог, философы 21 века) — не использовать first_turn gate,
    # иначе fallback "decision" даёт ответ про выбор/зона контроля вместо ответа на вопрос
    # PHILOBASE: граф влияний/связи философов → philosophy pipeline, не first_turn
    is_concept = (
        detect_philosophy_topic_intent(user_text)[0]
        or is_topic_high(user_text)
        or is_philo_graph_intent(user_text)
    )
    skip_warmup = should_skip_warmup_first_turn(state, user_text, history_count, current_stage)
    # BUG1: telemetry для отладки роутинга
    _logger.info(
        "routing: history_count=%s stage=%s is_concept=%s skip_warmup=%s",
        history_count, current_stage, is_concept, skip_warmup,
    )
    if skip_warmup and not is_concept:
        gate_text, gate_label = render_first_turn_philosophy(user_text)
        # BUG1: hard-guard — религия + вопрос ⇒ никогда first_turn (идти в pipeline)
        if gate_text and has_religion_in_orientation_context(user_text):
            if any(m in (user_text or "").lower() for m in ("расскажи", "объясни", "как ", "какие", "?")):
                gate_text, gate_label = None, "skip"
        if not gate_text or gate_label == "skip":
            gate_text = None
        # gate_text=None/skip: user попадёт в историю в основном pipeline (append_history ниже, ~1197)
        _logger.info("first_turn gate_label=%s gate_text=%s", gate_label, "yes" if gate_text else "no")
        if gate_text:
            gate_text = enforce_constraints(gate_text, "guidance", load_patterns().get("global_constraints", {}))
            USER_STAGE[user_id] = "guidance"
            USER_MSG_COUNT[user_id] = USER_MSG_COUNT.get(user_id, 0) + 1
            state["turn_index"] = state.get("turn_index", 0) + 1
            state["guidance_turns_count"] = state.get("guidance_turns_count", 0) + 1
            append_history(HISTORY_STORE, user_id, "user", user_text)
            # Не добавлять gate-ответ в историю — иначе «заражает» последующие ответы
            # append_history(HISTORY_STORE, user_id, "assistant", gate_text)  # skip
            state["last_user_text"] = user_text
            state["last_bot_text"] = gate_text
            return {"reply_text": finalize_reply(gate_text, {"max_questions": 1}), "telemetry": {"stage": "guidance", "first_turn_gate": True, "intent": "first_turn_gate", "label": gate_label}, "mode": None, "stage": "guidance"}

    USER_MSG_COUNT[user_id] = USER_MSG_COUNT.get(user_id, 0) + 1
    stage = _get_stage(user_id, user_text)
    USER_STAGE[user_id] = stage
    turn_index = state.get("turn_index", 0) + 1
    state["turn_index"] = turn_index

    text_lower = (user_text or "").lower()
    is_resistance = any(tr in text_lower for tr in RESISTANCE_TRIGGERS)
    is_confusion = any(tr in text_lower for tr in CONFUSION_TRIGGERS)
    want_fork = detect_financial_pattern(user_text)
    want_option_close = ENABLE_SESSION_CLOSE_CHOICE and stage == "guidance" and not (user_text or "").rstrip().endswith("?")

    context = {"stage": stage, "user_text_len": len((user_text or "").strip()), "is_safety": False, "is_resistance": is_resistance, "is_confusion": is_confusion, "want_fork": want_fork, "want_option_close": want_option_close, "enable_philosophy_match": ENABLE_PHILOSOPHY_MATCH}
    context = resolve_pattern_collisions(context)
    # E1.1: pass None when EVAL_SKIP_LLM_INTENT → topic_mid won't trigger LLM
    plan = governor_plan(
        user_id, stage, user_text, context, state,
        llm_classify_fn=None if EVAL_SKIP_LLM_INTENT else llm_classify_topic_intent,
    )
    # PHILOBASE: early routing for influence/connections questions
    if is_philo_graph_intent(user_text):
        plan.setdefault("stage_override", "guidance")
        plan["philosophy_pipeline"] = True
        plan["disable_warmup"] = True
        plan["answer_first_required"] = True
        plan["max_questions"] = 1
        db = get_philo_db()
        philo_hint = (
            "\n\n[PHILO_DB]\n"
            "You can use PhiloDB graph: nodes (philosopher, school) and edges (influenced, inspired, member_of, criticized/opposed_by). "
            "If user asks about movements/schools/traditions: use school nodes + member_of edges. "
            "If user asks 'who criticized/opposed': use criticized/opposed_by edges when present; otherwise answer normally. "
            "Nodes may include birth_year, era (ancient/medieval/early_modern/modern/contemporary) and centrality for ranking. "
            "Format in Markdown with bold headings. Mention Wikidata as source. "
            "Optional: suggest link to philosophy-graph visualization for exploration."
        )
        plan["system_prompt_extra"] = philo_hint
    if plan.get("direct_reply_text"):
        reply_text = finalize_reply(plan["direct_reply_text"], plan)
        append_history(HISTORY_STORE, user_id, "user", user_text)
        append_history(HISTORY_STORE, user_id, "assistant", reply_text)
        state["last_user_text"] = user_text
        state["last_bot_text"] = reply_text
        state["turn_index"] = turn_index
        USER_STAGE[user_id] = "guidance"
        tel = {"stage": "guidance", "intent": "capabilities", "cap_score": plan.get("cap_score", 0)}
        return {"reply_text": reply_text, "telemetry": tel, "mode": None, "stage": "guidance"}
    stage = plan.get("stage_override") or stage
    USER_STAGE[user_id] = stage

    if state.get("orientation_lock"):
        plan["disable_fork"] = True
        plan["disable_pattern_engine"] = True

    context["stage"] = stage
    context["philosophy_pipeline"] = plan.get("philosophy_pipeline", False)
    context["disable_list_templates"] = plan.get("disable_list_templates", False)
    context["answer_first_required"] = plan.get("answer_first_required", False)
    context["explain_mode"] = plan.get("explain_mode", False)

    if plan.get("philosophy_pipeline") or detect_financial_pattern(user_text) or plan.get("explain_mode"):
        want_option_close = False

    handled_orientation_choice = False
    if state.get("pending_orientation"):
        choice = (user_text or "").strip().lower()
        state["pending_orientation"] = False
        state["orientation_lock"] = True
        handled_orientation_choice = True
        if "сост" in choice:
            plan["stage_override"] = "guidance"
            plan["philosophy_pipeline"] = False
            plan["force_philosophy_mode"] = False
        elif "смысл" in choice:
            plan["stage_override"] = "guidance"
            plan["philosophy_pipeline"] = True
            plan["force_philosophy_mode"] = True
        elif any(x in choice for x in ("опор", "миров", "вера")):
            plan["stage_override"] = "guidance"
            plan["philosophy_pipeline"] = True
            plan["force_philosophy_mode"] = True
            plan["allow_confessions"] = True
        else:
            plan["stage_override"] = "guidance"
            plan["disable_warmup"] = True
        plan["disable_fork"] = True
        plan["disable_pattern_engine"] = True
        stage = plan.get("stage_override") or stage
        USER_STAGE[user_id] = stage

    # BUG2: ack/close («понял, спасибо») — короткий ответ, без triage; stage=guidance чтобы след. вопрос не warmup
    if is_ack_close_intent(user_text):
        USER_STAGE[user_id] = "guidance"
        append_history(HISTORY_STORE, user_id, "user", user_text)
        append_history(HISTORY_STORE, user_id, "assistant", ACK_CLOSE_REPLY_RU)
        state["last_user_text"] = user_text
        state["last_bot_text"] = ACK_CLOSE_REPLY_RU
        return {"reply_text": finalize_reply(ACK_CLOSE_REPLY_RU, {"max_questions": 0}), "telemetry": {"stage": "guidance", "intent": "ack_close"}, "mode": None, "stage": "guidance"}

    if (
        not handled_orientation_choice
        and not plan.get("force_philosophy_mode")
        and is_unclear_message(user_text)
        and stage == "warmup"
        and not plan.get("disable_warmup")
        and not plan.get("philosophy_pipeline")
        and not plan.get("answer_first_required")
        and not plan.get("explain_mode")
    ):
        state["pending_orientation"] = True
        append_history(HISTORY_STORE, user_id, "user", user_text)
        append_history(HISTORY_STORE, user_id, "assistant", ORIENTATION_MESSAGE_RU)
        state["last_user_text"] = user_text
        state["last_bot_text"] = ORIENTATION_MESSAGE_RU
        return {"reply_text": finalize_reply(ORIENTATION_MESSAGE_RU, {"max_questions": 1}), "telemetry": {"stage": "warmup", "orientation": True, "intent": "orientation"}, "mode": None, "stage": "warmup"}

    mode_tag = None
    selected_names = []
    pattern_id = None
    forbid_practice = False
    injection_this_turn = False
    has_reco = False
    guidance_ctx_for_completion = None
    reply_text = ""

    last_preview = state.get("last_lens_preview_turn")
    if last_preview is not None and turn_index - 1 == last_preview and stage == "guidance":
        chosen = detect_lens_choice(user_text)
        if chosen:
            set_active_lens(state, chosen)
            state["last_lens_preview_turn"] = None
            plan["force_philosophy_mode"] = False

    if plan.get("force_repeat_options") and state.get("last_options"):
        opts = state["last_options"]
        if isinstance(opts, list) and len(opts) >= 2:
            reply_text = "Ок, начнём с (1), потом перейдём к (2). С какого?"
        elif opts:
            line = opts[0] if isinstance(opts, list) else opts
            reply_text = f"Ок. {line} — с какого начнём?"
        else:
            reply_text = "Уточни, пожалуйста — с чего начать?"
        want_option_close = False
    elif plan.get("force_philosophy_mode") and not plan.get("philosophy_pipeline") and not get_active_lens(state) and len((user_text or "").strip()) <= 250 and not detect_financial_pattern(user_text):
        # Lens preview только для расплывчатых запросов (поговорим про философию). Конкретные topic-вопросы (расскажи про X) — в LLM, не preview
        reply_text = render_lens_preview("guidance" if detect_lens_preview_need(user_text) else "default") + "\n\n" + render_lens_soft_question()
        reply_text = enforce_constraints(reply_text, "guidance", load_patterns().get("global_constraints", {}))
        state["last_lens_preview_turn"] = turn_index
        want_option_close = False
    elif plan.get("force_philosophy_mode") and not get_active_lens(state) and (len((user_text or "").strip()) > 250 or detect_financial_pattern(user_text)):
        plan["force_philosophy_mode"] = False
    elif stage == "warmup" and not plan.get("disable_warmup") and not plan.get("philosophy_pipeline"):
        selected_names = []
        reply_from_pattern = False
        if ENABLE_PATTERN_ENGINE and not plan.get("disable_pattern_engine"):
            pattern = choose_pattern("warmup", context)
            if pattern:
                pattern_id = pattern.get("id", "")
                reply_text = render_pattern(pattern, context)
                reply_text = enforce_constraints(reply_text, "warmup", load_patterns().get("global_constraints", {}))
                state["last_bridge_turn"] = turn_index
                reply_from_pattern = True
            else:
                ctx = pack_context(user_id, state, HISTORY_STORE, user_language=state.get("user_language"))
                reply_text = call_openai(load_warmup_prompt(), user_text, context_block=ctx)
                reply_text = postprocess_response(reply_text, stage)
        else:
            ctx = pack_context(user_id, state, HISTORY_STORE, user_language=state.get("user_language"))
            reply_text = call_openai(load_warmup_prompt(), user_text, context_block=ctx)
            reply_text = postprocess_response(reply_text, stage)
        if reply_from_pattern and reply_text and len((reply_text or "").strip()) < 120 and "?" not in reply_text and "\n\n" not in reply_text:
            ctx = pack_context(user_id, state, HISTORY_STORE, user_language=state.get("user_language"))
            reply_text = call_openai(load_warmup_prompt(), user_text, context_block=ctx)
            reply_text = postprocess_response(reply_text, stage)
    else:
        if plan.get("philosophy_pipeline"):
            USER_STAGE[user_id] = "guidance"
            stage = "guidance"
        state["guidance_turns_count"] = state.get("guidance_turns_count", 0) + 1
        term = is_term_question(user_text)
        if term:
            reply_text = term_example_first(term, {"user_text": user_text})
            reply_text = enforce_constraints(reply_text, "guidance", load_patterns().get("global_constraints", {}))
            want_option_close = False
        else:
            raw_llm_text = ""
            main_prompt = load_system_prompt()
            all_lenses = load_all_lenses()
            active_lens = get_active_lens(state)
            if active_lens and active_lens in LENS_TO_SYSTEM_ID:
                selected_names = [LENS_TO_SYSTEM_ID[active_lens]]
            elif detect_financial_pattern(user_text):
                selected_names = ["lens_finance_rhythm"]
                mode_tag = "financial_rhythm"
            else:
                selected_names = select_lenses(user_text, all_lenses, max_lenses=plan.get("max_lenses", 3))
                # P1: philosophy concept questions — не подменять lens_general на lens_control_scope
                if "lens_general" in selected_names and "lens_control_scope" in all_lenses and not plan.get("philosophy_pipeline"):
                    selected_names = ["lens_control_scope" if n == "lens_general" else n for n in selected_names]
                    selected_names = list(dict.fromkeys(selected_names))
                if plan.get("answer_first_required"):
                    selected_names = selected_names[:3]
                elif plan.get("explain_mode"):
                    selected_names = selected_names[: plan.get("max_lenses", 2)]
            lens_contents = [all_lenses.get(n, "") for n in selected_names]
            lens_contents = [c for c in lens_contents if c]
            system_prompt = build_system_prompt(main_prompt, lens_contents)
            system_prompt += plan.get("system_prompt_extra", "")
            system_prompt += "\n\nExistential: макс. 2 рамки, каждая ≤2 предложения."
            if state.get("force_expand_next"):
                system_prompt += "\n\n---\nforce_expand_next: Дай развёрнутый ответ с объяснением и примером. Не менее 2 абзацев."
                state["force_expand_next"] = False
            phi_style = load_philosophy_style()
            if phi_style:
                system_prompt += "\n\n---\n" + phi_style
            # Fix Pack D: anti-too-short — floor 900 при богатом запросе
            user_len = len((user_text or "").strip())
            rich_request = user_len >= 80 and (stage in ("guidance", "analysis") or plan.get("answer_first_required") or plan.get("philosophy_pipeline"))
            if rich_request and not plan.get("philosophy_pipeline") and not plan.get("explain_mode"):
                system_prompt += "\n\nОтвет: развёрнуто, не менее 900 символов. Без ultra-short."
            if plan.get("philosophy_pipeline"):
                system_prompt += (
                    "\n\nОтвет: развёрнуто, не менее ~900 символов. Без короткого режима."
                    "\n---\nЗАПРЕЩЕНО: начинать с абстрактной подводки («Когда ответов много», «Когда внутри нет ясности» и т.п.). Сразу отвечать на вопрос."
                    "\n---\nОдин связный ответ. Не дублировать содержание вторым блоком."
                    "\nЕсли ответ длинный — вторую часть не начинать с «Продолжу», «Дальше». Продолжать тот же ответ без вступления, сразу по делу."
                )
            if plan.get("explain_mode"):
                # Fix Pack D2: structure requirement вместо только length floor
                expl = (
                    "\n\n---\nEXPLAIN_MODE: Структура обязательна (без заголовков, но по смыслу):\n"
                    "1) Первый абзац: заявленная оптика (если попросили через буддизм/другую — именно её рамку). "
                    "2) Середина: 2–3 пункта или нумерованные предложения — как это работает в случае пользователя. "
                    "3) Конец: одно практическое переформулирование (не новая практика каждый раз), затем макс 1 вопрос. "
                    "Практика — макс 1, только если просит советы. СТРОГО не менее 900 символов."
                )
                if _has_buddhism_switch(user_text or ""):
                    expl += (
                        "\n\n---\nБУДДИЙСКАЯ ОПТИКА: Мягко, без лекции. Ключи: дуккха/танха (привязанность к контролю), "
                        "непостоянство, осознанность к тяге к определённости. Переведи на язык пользователя, не академично."
                    )
                elif any(k in (user_text or "").lower() for k in ("пример", "покажи", "как выглядит", "на моём случае", "на моем случае")):
                    expl += " Обязательно включи конкретный пример."
                system_prompt += expl
                # PATCH F: Explain Expander — развернуто и читабельно
                system_prompt += "\n\n---\n" + _explain_mode_instructions_ru()
            if plan.get("allow_philosophy_examples") and (detect_financial_pattern(user_text) or any(k in (user_text or "").lower() for k in ("смысл", "выбор", "решен", "нереш", "ценност"))):
                system_prompt += "\n\n---\nv21.1 Multi-style: 2–3 оптики. Максимум 3 школы, 1 вопрос, 1 практика."
            ctx = pack_context(user_id, state, HISTORY_STORE, user_language=state.get("user_language"))
            if plan.get("explain_mode"):
                ctx = (ctx + f"\n\n[explain_mode: true]\n[explain_topic: {(user_text or '')[:200]}]").strip() if ctx else f"[explain_mode: true]\n[explain_topic: {(user_text or '')[:200]}]"
            if plan.get("system_prompt_extra"):
                path_hint = try_graph_answer_ru(user_text or "")
                if path_hint:
                    ctx = (ctx + f"\n\n{path_hint}").strip() if ctx else path_hint
            guidance_ctx_for_completion = {"system_prompt": system_prompt, "ctx": ctx, "user_text": user_text}
            reply_text = call_openai(system_prompt, user_text, context_block=ctx)
            # Fix Pack D: не укорачивать при rich_request / explain / philosophy
            if _is_meta_lecture(reply_text) and not plan.get("philosophy_pipeline") and not plan.get("explain_mode") and not plan.get("disable_short_mode") and not rich_request:
                reply_text = call_openai(system_prompt, user_text, force_short=True, context_block=ctx)
            if _is_existential(user_text) and stage != "guidance":
                reply_text = _trim_existential(reply_text)
            raw_llm_text = reply_text
            reply_text = postprocess_response(reply_text, stage, philosophy_pipeline=plan.get("philosophy_pipeline", False), mode_tag=mode_tag, answer_first_required=plan.get("answer_first_required", False), explain_mode=plan.get("explain_mode", False))
            # Fix Pack D: retry expand if floor violated (rich request, answer < 900)
            # P1: plan.min_chars overrides default (e.g. philosophy_topic → 900)
            # TEST COST OPTIMIZER: skip expand when EVAL_NO_EXPAND=1
            needs_floor = rich_request or plan.get("philosophy_pipeline") or plan.get("explain_mode") or plan.get("min_chars")
            floor_chars = int(plan.get("min_chars") or os.getenv("EVAL_MIN_CHARS", "900"))
            if (
                needs_floor
                and not os.getenv("EVAL_NO_EXPAND")
                and len((reply_text or "").strip()) < floor_chars
                and guidance_ctx_for_completion
            ):
                expand_hint = f"Ответ должен быть не менее {floor_chars} символов. Разверни мысль, добавь пример или слой анализа."
                gc = guidance_ctx_for_completion
                ctx_expand = (gc["ctx"] + f"\n\n[требование: {expand_hint}]").strip() if gc.get("ctx") else f"[требование: {expand_hint}]"
                reply_text2 = call_openai(gc["system_prompt"], gc["user_text"], context_block=ctx_expand)
                if len((reply_text2 or "").strip()) >= floor_chars:
                    reply_text = postprocess_response(reply_text2, stage, philosophy_pipeline=plan.get("philosophy_pipeline", False), mode_tag=mode_tag, answer_first_required=plan.get("answer_first_required", False), explain_mode=plan.get("explain_mode", False))
            stable_match = detect_stable_pattern(user_text)
            if should_inject(state, stage, stable_match, is_safety=False):
                line_id = choose_philosophy_line(stable_match, user_text)
                injection = render_injection(line_id)
                reply_text = insert_injection_after_first_paragraph(reply_text, injection)
                mark_injection_done(state)
                state["active_philosophy_line"] = line_id
                injection_this_turn = True
            forbid_practice = state.get("practice_cooldown_turns", 0) > 0 or injection_this_turn
            if forbid_practice:
                reply_text = strip_practice_content(reply_text)
            if handle_i_dont_understand(user_text):
                reply_text = replace_clarifying_with_example(reply_text)
            if not should_ask_question(user_id, state):
                reply_text = remove_questions(reply_text)
            has_reco = stage != "safety" and detect_recommendation(reply_text)
            if has_reco:
                forbid_practice = True
                reply_text = strip_practice_content(reply_text)
            fork_allowed = fork_density_guard(user_id, state)
            context["mode_tag"] = mode_tag
            if ENABLE_PATTERN_ENGINE and not plan.get("disable_pattern_engine"):
                constraints = load_patterns().get("global_constraints", {})
                prefix, bridge_cat = build_ux_prefix("guidance", context, state) if plan.get("add_bridge") else (None, None)
                if bridge_cat:
                    state["last_bridge_category"] = bridge_cat
                    state["last_bridge_turn"] = turn_index
                stripped = strip_echo_first_line(reply_text)
                if prefix and stripped != reply_text:
                    reply_text = prefix + "\n\n" + stripped
                elif stripped != reply_text:
                    reply_text = stripped
                if want_option_close and not plan.get("disable_option_close") and not plan.get("disable_fork") and fork_allowed and not has_reco:
                    opt_line = get_option_close_line()
                    reply_text = reply_text.rstrip() + "\n\n" + opt_line
                    state["last_options"] = [opt_line]
                    state["pending"] = {"kind": "fork", "options": ["1", "2"], "default": "1", "prompt": opt_line, "created_turn": turn_index}
                reply_text = enforce_constraints(reply_text, "guidance", constraints, plan)
            else:
                if want_option_close and not plan.get("disable_option_close") and not plan.get("disable_fork") and fork_allowed and not has_reco:
                    opt_line = get_option_close_line()
                    reply_text = reply_text.rstrip() + "\n\n" + opt_line
                    state["last_options"] = [opt_line]
                    state["pending"] = {"kind": "fork", "options": ["1", "2"], "default": "1", "prompt": opt_line, "created_turn": turn_index}
            if plan.get("answer_first_required") and len(reply_text or "") < 180 and raw_llm_text:
                reply_text = raw_llm_text

    if stage == "guidance" and selected_names:
        LAST_LENS_BY_USER[user_id] = selected_names
    if not plan.get("force_philosophy_mode"):
        pm_suggestion = _maybe_suggest_philosophy_match(user_id, stage, is_safety=False)
        if pm_suggestion:
            reply_text = reply_text.rstrip() + "\n\n" + pm_suggestion
    if want_option_close and not plan.get("disable_fork") and not (ENABLE_PATTERN_ENGINE and stage == "guidance") and not has_reco:
        reply_text = reply_text.rstrip() + "\n\nХочешь продолжить: (1) про причины или (2) про следующий шаг?"
    if stage in ("warmup", "guidance"):
        reply_text, _ = strip_meta_format_questions(reply_text)
    if has_reco and stage != "safety":
        reply_text = apply_recommendation_pause(reply_text)
        state["practice_cooldown_turns"] = max(state.get("practice_cooldown_turns", 0), 2)
    if stage == "guidance":
        if contains_practice(reply_text) and not forbid_practice:
            state["practice_cooldown_turns"] = COOLDOWN_AFTER_PRACTICE
        tick_practice_cooldown(state)
        tick_lens_lock(state)
    prev_user_for_anchor = state.get("last_user_text")
    append_history(HISTORY_STORE, user_id, "user", user_text)
    append_history(HISTORY_STORE, user_id, "assistant", reply_text)
    state["last_user_text"] = user_text
    state["last_bot_text"] = reply_text
    clamp_kw = {"mode_tag": mode_tag, "stage": stage, "answer_first_required": plan.get("answer_first_required", False), "philosophy_pipeline": plan.get("philosophy_pipeline", False), "explain_mode": plan.get("explain_mode", False)}
    reply_text = final_send_clamp(reply_text, **clamp_kw)
    if stage == "guidance" and looks_incomplete(reply_text):
        reply_text2 = add_closing_sentence(reply_text)
        reply_text2 = final_send_clamp(reply_text2, **clamp_kw)
        if looks_incomplete(reply_text2) and guidance_ctx_for_completion:
            gc = guidance_ctx_for_completion
            reply_text2 = call_openai(gc["system_prompt"], gc["user_text"], context_block=gc["ctx"])
            reply_text2 = postprocess_response(reply_text2, stage, philosophy_pipeline=plan.get("philosophy_pipeline", False), mode_tag=mode_tag, answer_first_required=plan.get("answer_first_required", False), explain_mode=plan.get("explain_mode", False))
            reply_text2 = final_send_clamp(reply_text2, **clamp_kw)
        reply_text = reply_text2
    # Fix Pack D2: context anchor before finalize (prev_user = previous turn's user message)
    reply_text, _anchor_dbg = apply_context_anchor(
        reply_text, user_text, prev_user=prev_user_for_anchor,
        turn_index=state.get("turn_index", 0), plan=plan, debug=False
    )
    reply_text = finalize_reply(reply_text, plan)
    if stage == "guidance" and len((reply_text or "").strip()) < 280:
        state["force_expand_next"] = True
    if state.get("orientation_lock"):
        state["orientation_lock"] = False
    telemetry = {"stage": stage, "mode_tag": mode_tag, "lenses": selected_names, "pattern_id": pattern_id, "intent": plan.get("intent", "none"), "blocks_used": plan.get("blocks_used", "none")}
    return {"reply_text": reply_text, "telemetry": telemetry, "mode": mode_tag, "stage": stage}


async def process_user_query(message: Message, user_text: str, update_id: Optional[int] = None) -> None:
    """Обрабатывает текст пользователя (общая логика для текста и голоса)."""
    user_id = message.from_user.id if message.from_user else 0
    # BUG3: логирование для отладки дублей
    _logger.info(
        "update_id=%s message_id=%s chat_id=%s user_id=%s text=%s",
        update_id, getattr(message, "message_id", None), message.chat.id, user_id,
        (user_text or "")[:80].replace("\n", " "),
    )

    if not user_text:
        await send_text(bot, message.chat.id, "Не удалось распознать текст. Попробуйте написать или записать снова.")
        return

    # State persistence: загрузить с диска перед обработкой
    _load_persisted_state()

    # SOURCE_RULE_LANGUAGE_MATCH: сохранить user_language из Telegram
    _lang_code = getattr(message.from_user, "language_code", None) if message.from_user else None

    state = USER_STATE.get(user_id)
    if state and _lang_code:
        from philosophy.source_rule import get_user_language
        state["user_language"] = get_user_language(_lang_code)
    if not state:
        USER_STATE[user_id] = {
            "turn_index": 0,
            "last_bridge_turn": -10,
            "last_options": None,
            "guidance_turns_count": 0,
            "last_fork_turn": -10,
            "pending": None,
            "last_user_text": "",
            "last_bot_text": "",
            "active_lens": None,
            "lens_lock_turns_left": 0,
            "last_injection_turn": -10,
            "active_philosophy_line": None,
            "practice_cooldown_turns": 0,
            "last_lens_preview_turn": None,
            "user_language": None,
            "onboarding_shown": False,
            "pending_orientation": False,
            "orientation_lock": False,
        }
        state = USER_STATE[user_id]
        if _lang_code:
            from philosophy.source_rule import get_user_language
            state["user_language"] = get_user_language(_lang_code)

    # Core pipeline (общий для bot и eval)
    result = generate_reply_core(user_id, user_text)
    reply_text = result.get("reply_text", "")

    if result.get("stage") == "safety":
        log_safety_event(user_id, user_text)
    tel = result.get("telemetry", {})
    log_dialog(user_id, user_text, tel.get("lenses", []), reply_text)
    save_state(_state_to_persist())
    corr = f"u{update_id}_m{getattr(message, 'message_id', '?')}" if update_id else None
    await send_text(bot, message.chat.id, reply_text, reply_markup=FEEDBACK_KEYBOARD, correlation_id=corr)


@dp.message(F.voice)
async def handle_voice(message: Message, **kwargs) -> None:
    """Обработка голосовых сообщений."""
    status_msg = await send_text(bot, message.chat.id, "Слушаю...")
    try:
        file = await bot.get_file(message.voice.file_id)
        ext = "ogg"  # Telegram отправляет голос в OGG
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        await bot.download_file(file.file_path, destination=tmp_path)
        try:
            user_text = transcribe_voice(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)
        if status_msg:
            await status_msg.delete()
        await process_user_query(message, user_text or "", update_id=kwargs.get("update_id"))
    except Exception as e:
        if status_msg:
            await status_msg.edit_text(f"Не удалось обработать голос: {e}")


@dp.message(F.text)
async def handle_message(message: Message, **kwargs) -> None:
    """Обработка текстовых сообщений. BUG3: guard от команд, update_id для логов."""
    text = (message.text or "").strip()
    if text.startswith("/"):
        return  # команды обрабатывают Command/CommandStart, не F.text
    await process_user_query(message, text or message.text or "", update_id=kwargs.get("update_id"))


@dp.callback_query(F.data.startswith("fb_"))
async def handle_feedback(callback: CallbackQuery) -> None:
    """Обработка кнопок фидбека."""
    if not callback.data or not callback.message:
        return
    user_id = callback.from_user.id if callback.from_user else 0
    message_id = callback.message.message_id
    rating = "useful" if callback.data == "fb_useful" else "not_useful"
    log_feedback(user_id, message_id, rating)
    await callback.answer("Спасибо за оценку!")
    # Убираем кнопки после нажатия
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


async def _run_export_server() -> None:
    """HTTP‑сервер для /export — экспорт диалогов из БД."""
    port = int(os.getenv("PORT", "0"))
    if port <= 0 or not DATABASE_URL or not EXPORT_TOKEN:
        return

    from aiohttp import web

    async def export_handler(request: web.Request) -> web.Response:
        token = request.query.get("token", "")
        if token != EXPORT_TOKEN:
            return web.json_response({"error": "unauthorized"}, status=401)
        dialogs = export_dialogs_from_db()
        return web.json_response({"dialogs": dialogs, "count": len(dialogs)})

    async def health_handler(_: web.Request) -> web.Response:
        return web.json_response(_health_payload())

    app = web.Application()
    app.router.add_get("/export", export_handler)
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Export server: PORT={port} /export?token=...")


async def _daily_backup_task() -> None:
    """Ежедневное сохранение логов (если BACKUP_DAILY=1)."""
    import subprocess
    backup_script = PROJECT_ROOT / "scripts" / "backup_logs_daily.py"
    while True:
        await asyncio.sleep(86400)  # 24 ч
        if backup_script.exists():
            try:
                subprocess.run(
                    [sys.executable, str(backup_script)],
                    cwd=str(PROJECT_ROOT),
                    capture_output=True,
                    timeout=60,
                )
            except Exception as e:
                if DEBUG:
                    print(f"[Phi] backup error: {e}")


async def main() -> None:
    """Запуск бота."""
    print(f"LLM model: {OPENAI_MODEL}")
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    print(f"Подключено к Telegram: @{me.username}")

    if DATABASE_URL:
        conn = _get_db_conn()
        print(f"[DB] PostgreSQL: {'OK' if conn else 'FAIL (см. лог выше)'}")

    port = int(os.getenv("PORT", "0"))
    if port > 0 and DATABASE_URL and EXPORT_TOKEN:
        asyncio.create_task(_run_export_server())

    # Ежедневный бэкап логов (BACKUP_DAILY=1, локальный запуск)
    if os.getenv("BACKUP_DAILY", "").strip() == "1":
        asyncio.create_task(_daily_backup_task())
        print("[Phi] Daily backup enabled (exports/dialogs_YYYY-MM-DD.json)")
    elif port > 0:
        # Railway web требует listen на PORT — заглушка если нет DB
        from aiohttp import web
        app = web.Application()
        app.router.add_get("/", lambda r: web.Response(text="Phi Bot"))
        app.router.add_get("/health", lambda r: web.json_response(_health_payload()))
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", port).start()

    print("Бот запущен. Ожидание сообщений...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Ошибка запуска: {e}")
        raise
