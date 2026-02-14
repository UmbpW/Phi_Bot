"""
Phi Bot — Telegram-бот MVP на aiogram 3.x.
Запуск: python bot.py
"""

import asyncio
import os
import sys
from typing import Optional
import re
import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.filters import CommandStart, Command
from dotenv import load_dotenv
from openai import OpenAI

from logger import (
    _get_db_conn,
    export_dialogs_from_db,
    log_dialog,
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
from utils.output_sanitizer import sanitize_output
from utils.send_pipeline import send_text
from utils.telegram_idempotency import IdempotencyMiddleware
from utils.state_store import load_state, save_state
from utils.short_ack import is_short_ack
from utils.context_pack import pack_context, append_history
from utils.intent_gate import should_skip_warmup_first_turn
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
)
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
from philosophy.practice_cooldown import (
    strip_practice_content,
    contains_practice,
    tick_practice_cooldown,
    COOLDOWN_AFTER_PRACTICE,
)

BOT_VERSION = "Phi_Bot v17-philosophy-guided"
DEBUG = True

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

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не задан в .env")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не задан в .env")

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


def call_openai(
    system_prompt: str,
    user_text: str,
    force_short: bool = False,
    context_block: str = "",
) -> str:
    """Вызывает OpenAI Responses API. context_block — упакованный контекст диалога."""
    model_name = OPENAI_MODEL
    inst = system_prompt
    if force_short:
        inst += "\n\nОтветь короче и разговорнее. Без лекций."
    input_text = user_text
    if context_block:
        input_text = f"[Контекст диалога]\n{context_block}\n\n[Текущее сообщение]\n{user_text}"
    try:
        response = openai_client.responses.create(
            model=model_name,
            instructions=inst,
            input=input_text,
        )
        return _extract_response_text(response)
    except Exception as e:
        if DEBUG:
            print(f"[Phi] model {model_name} failed, fallback to gpt-5.2-mini: {e}")
        try:
            response = openai_client.responses.create(
                model="gpt-5.2-mini",
                instructions=inst,
                input=input_text,
            )
            return _extract_response_text(response)
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


def _state_to_persist() -> dict:
    """Собрать state для сохранения на диск."""
    import time
    out = {}
    for uid, state in USER_STATE.items():
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
        }


ABOUT_TEXT = (
    "Этот бот — секулярный философский агент поддержки.\n"
    "Он помогает размышлять и находить опору через философские рамки и вопросы.\n\n"
    "Это не психотерапия и не медицинская помощь.\n"
    "Если у вас кризисное состояние или риск причинить себе вред — важно обратиться к живому специалисту или в местные службы помощи.\n\n"
    "Бот работает в тестовом режиме."
)


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Приветствие по /start."""
    uid = message.from_user.id if message.from_user else 0
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
    }
    save_state(_state_to_persist())
    await send_text(bot, message.chat.id, "Привет! Я Phi Bot — AI-помощник.\nНапишите или наговорите любой вопрос.")


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


async def process_user_query(message: Message, user_text: str) -> None:
    """Обрабатывает текст пользователя (общая логика для текста и голоса)."""
    user_id = message.from_user.id if message.from_user else 0

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
        }
        state = USER_STATE[user_id]
        if _lang_code:
            from philosophy.source_rule import get_user_language
            state["user_language"] = get_user_language(_lang_code)

    # Pending follow-through: short_ack продолжает предыдущий контекст
    if state and is_short_ack(user_text) and state.get("pending"):
        reply_text = _execute_pending_follow_through(user_id, user_text, state)
        if reply_text:
            append_history(HISTORY_STORE, user_id, "user", user_text)
            state["last_user_text"] = user_text
            state["last_bot_text"] = reply_text
            append_history(HISTORY_STORE, user_id, "assistant", reply_text)
            save_state(_state_to_persist())
            await send_text(bot, message.chat.id, reply_text, reply_markup=FEEDBACK_KEYBOARD)
            return

    # Safety-фильтр
    if check_safety(user_text):
        safe_text = get_safe_response()
        await send_text(bot, message.chat.id, safe_text)
        log_safety_event(user_id, user_text)
        return

    # First Turn Philosophy Gate v15: философский intent → answer-first, без generic warmup
    history_count = len(HISTORY_STORE.get(user_id, []))
    current_stage = USER_STAGE.get(user_id)
    if should_skip_warmup_first_turn(state, user_text, history_count, current_stage):
        gate_text, intent_label = render_first_turn_philosophy(user_text)
        gate_text = enforce_constraints(
            gate_text, "guidance", load_patterns().get("global_constraints", {})
        )
        USER_STAGE[user_id] = "guidance"
        USER_MSG_COUNT[user_id] = USER_MSG_COUNT.get(user_id, 0) + 1
        state["turn_index"] = state.get("turn_index", 0) + 1
        state["guidance_turns_count"] = state.get("guidance_turns_count", 0) + 1
        append_history(HISTORY_STORE, user_id, "user", user_text)
        append_history(HISTORY_STORE, user_id, "assistant", gate_text)
        state["last_user_text"] = user_text
        state["last_bot_text"] = gate_text
        log_dialog(user_id, user_text, [], gate_text)
        save_state(_state_to_persist())
        if DEBUG:
            print(f"[Phi DEBUG] first_turn_gate=ON intent={intent_label}")
        await send_text(bot, message.chat.id, gate_text, reply_markup=FEEDBACK_KEYBOARD)
        return

    # Stage machine v8
    USER_MSG_COUNT[user_id] = USER_MSG_COUNT.get(user_id, 0) + 1
    stage = _get_stage(user_id, user_text)
    USER_STAGE[user_id] = stage

    # Governor state v12 + v17 schema
    if user_id not in USER_STATE:
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
        }
    state = USER_STATE[user_id]
    state["turn_index"] = state.get("turn_index", 0) + 1
    turn_index = state["turn_index"]

    mode_tag = None
    selected_names = []
    pattern_id = None
    forbid_practice = False
    injection_this_turn = False

    text_lower = (user_text or "").lower()
    is_resistance = any(tr in text_lower for tr in RESISTANCE_TRIGGERS)
    is_confusion = any(tr in text_lower for tr in CONFUSION_TRIGGERS)
    want_fork = detect_financial_pattern(user_text)
    want_option_close = (
        ENABLE_SESSION_CLOSE_CHOICE
        and stage == "guidance"
        and not (user_text or "").rstrip().endswith("?")
    )
    context = {
        "stage": stage,
        "is_safety": False,
        "is_resistance": is_resistance,
        "is_confusion": is_confusion,
        "want_fork": want_fork,
        "want_option_close": want_option_close,
        "enable_philosophy_match": ENABLE_PHILOSOPHY_MATCH,
    }
    context = resolve_pattern_collisions(context)
    plan = governor_plan(user_id, stage, user_text, context, state)
    if DEBUG:
        print(f"[Phi DEBUG] plan={plan} turn={turn_index}")

    # v17 Lens choice: после lens preview пользователь выбрал линию → lock
    last_preview = state.get("last_lens_preview_turn")
    if (
        last_preview is not None
        and turn_index - 1 == last_preview
        and stage == "guidance"
    ):
        chosen = detect_lens_choice(user_text)
        if chosen:
            set_active_lens(state, chosen)
            state["last_lens_preview_turn"] = None
            plan["force_philosophy_mode"] = False  # идём в guidance с одной линзой
            if DEBUG:
                print(f"[Phi DEBUG] guided_path=on lens_lock={chosen}")

    # Короткий ответ "оба"/"да"/"нет" + есть last_options: повторить варианты
    if plan.get("force_repeat_options") and state.get("last_options"):
        selected_names = []
        opts = state["last_options"]
        if isinstance(opts, list) and len(opts) >= 2:
            reply_text = "Ок, начнём с (1), потом перейдём к (2). С какого?"
        elif opts:
            line = opts[0] if isinstance(opts, list) else opts
            reply_text = f"Ок. {line} — с какого начнём?"
        else:
            reply_text = "Уточни, пожалуйста — с чего начать?"
        want_option_close = False
    # v17 Philosophy mode: guided_path (lens preview) вместо картечи A/B/C
    elif plan.get("force_philosophy_mode") and not get_active_lens(state):
        selected_names = []
        theme = "default"
        if detect_lens_preview_need(user_text):
            theme = "guidance"
        reply_text = render_lens_preview(theme) + "\n\n" + render_lens_soft_question()
        reply_text = enforce_constraints(
            reply_text, "guidance", load_patterns().get("global_constraints", {})
        )
        state["last_lens_preview_turn"] = turn_index
        want_option_close = False
        if DEBUG:
            print("[Phi DEBUG] guided_path=on")
    elif stage == "warmup":
        selected_names = []
        if ENABLE_PATTERN_ENGINE and not plan.get("disable_pattern_engine"):
            data = load_patterns()
            pattern = choose_pattern("warmup", context)
            if pattern:
                pattern_id = pattern.get("id", "")
                reply_text = render_pattern(pattern)
                constraints = data.get("global_constraints", {})
                reply_text = enforce_constraints(reply_text, "warmup", constraints)
                state["last_bridge_turn"] = turn_index
            else:
                system_prompt = load_warmup_prompt()
                ctx = pack_context(user_id, state, HISTORY_STORE, user_language=_lang_code)
                reply_text = call_openai(system_prompt, user_text, context_block=ctx)
                reply_text = postprocess_response(reply_text, stage)
        else:
            system_prompt = load_warmup_prompt()
            ctx = pack_context(user_id, state, HISTORY_STORE, user_language=_lang_code)
            reply_text = call_openai(system_prompt, user_text, context_block=ctx)
            reply_text = postprocess_response(reply_text, stage)
    else:
        # Guidance: system + линзы
        state["guidance_turns_count"] = state.get("guidance_turns_count", 0) + 1

        # Agency v13: term question — сразу пример, без LLM/fork
        term = is_term_question(user_text)
        if term:
            user_context = {"user_text": user_text}
            reply_text = term_example_first(term, user_context)
            reply_text = enforce_constraints(
                reply_text, "guidance", load_patterns().get("global_constraints", {})
            )
            want_option_close = False
        else:
            main_prompt = load_system_prompt()
            all_lenses = load_all_lenses()
            active_lens = get_active_lens(state)
            if active_lens and active_lens in LENS_TO_SYSTEM_ID:
                selected_names = [LENS_TO_SYSTEM_ID[active_lens]]
            elif detect_financial_pattern(user_text):
                selected_names = ["lens_expectation_gap", "lens_control_scope"]
                mode_tag = "financial_pattern_confusion"
            else:
                selected_names = select_lenses(user_text, all_lenses, max_lenses=3)
                if "lens_general" in selected_names and "lens_control_scope" in all_lenses:
                    selected_names = [
                        "lens_control_scope" if n == "lens_general" else n
                        for n in selected_names
                    ]
                    selected_names = list(dict.fromkeys(selected_names))
            lens_contents = [all_lenses.get(name, "") for name in selected_names]
            lens_contents = [c for c in lens_contents if c]
            system_prompt = build_system_prompt(main_prompt, lens_contents)
            system_prompt += "\n\nExistential: макс. 2 рамки, каждая ≤2 предложения."
            phi_style = load_philosophy_style()
            if phi_style:
                system_prompt += "\n\n---\n" + phi_style

            ctx = pack_context(user_id, state, HISTORY_STORE, user_language=_lang_code)
            reply_text = call_openai(system_prompt, user_text, context_block=ctx)
            if _is_meta_lecture(reply_text):
                reply_text = call_openai(system_prompt, user_text, force_short=True, context_block=ctx)
            # v17: запрещено summary-trimming при stage == guidance
            if _is_existential(user_text) and stage != "guidance":
                reply_text = _trim_existential(reply_text)
            reply_text = postprocess_response(reply_text, stage)

            # v17 Natural injection: после первого абзаца, при устойчивом паттерне
            injection_this_turn = False
            stable_match = detect_stable_pattern(user_text)
            if should_inject(state, stage, stable_match, is_safety=False):
                line_id = choose_philosophy_line(stable_match, user_text)
                injection = render_injection(line_id)
                reply_text = insert_injection_after_first_paragraph(reply_text, injection)
                mark_injection_done(state)
                state["active_philosophy_line"] = line_id
                injection_this_turn = True
                if DEBUG:
                    print(f"[Phi DEBUG] natural_injection={line_id}")

            # v17 Practice cooldown: strip если cooldown или injection turn
            forbid_practice = (
                state.get("practice_cooldown_turns", 0) > 0 or injection_this_turn
            )
            if forbid_practice:
                reply_text = strip_practice_content(reply_text)

            # Agency v13: handle "не понимаю" и answer>ask (guidance only)
            if handle_i_dont_understand(user_text):
                reply_text = replace_clarifying_with_example(reply_text)
            if not should_ask_question(user_id, state):
                reply_text = remove_questions(reply_text)

            # Pattern engine: UX prefix + echo stripping (только guidance)
            fork_allowed = fork_density_guard(user_id, state)
            if ENABLE_PATTERN_ENGINE and not plan.get("disable_pattern_engine"):
                data = load_patterns()
                constraints = data.get("global_constraints", {})
                prefix, bridge_cat = build_ux_prefix("guidance", context, state) if plan.get("add_bridge") else (None, None)
                if bridge_cat:
                    state["last_bridge_category"] = bridge_cat
                    state["last_bridge_turn"] = turn_index
                stripped = strip_echo_first_line(reply_text)
                if prefix and stripped != reply_text:
                    reply_text = prefix + "\n\n" + stripped
                elif stripped != reply_text:
                    reply_text = stripped
                if want_option_close and not plan.get("disable_option_close") and fork_allowed:
                    opt_line = get_option_close_line()
                    reply_text = reply_text.rstrip() + "\n\n" + opt_line
                    state["last_options"] = [opt_line]
                    state["last_fork_turn"] = state["guidance_turns_count"]
                    state["pending"] = {
                        "kind": "fork",
                        "options": ["1", "2"],
                        "default": "1",
                        "prompt": opt_line,
                        "created_turn": turn_index,
                    }
                reply_text = enforce_constraints(reply_text, "guidance", constraints)
            else:
                if want_option_close and not plan.get("disable_option_close") and fork_allowed:
                    opt_line = get_option_close_line()
                    reply_text = reply_text.rstrip() + "\n\n" + opt_line
                    state["last_options"] = [opt_line]
                    state["last_fork_turn"] = state["guidance_turns_count"]
                    state["pending"] = {
                        "kind": "fork",
                        "options": ["1", "2"],
                        "default": "1",
                        "prompt": opt_line,
                        "created_turn": turn_index,
                    }

            # Agency debug (guidance only)
            if DEBUG:
                questions_removed = not should_ask_question(user_id, state)
                print(f"[Phi DEBUG] agency: fork_allowed={fork_allowed} questions_removed={questions_removed}")

    # Сохраняем линзы для /lens
    if stage == "guidance" and selected_names:
        LAST_LENS_BY_USER[user_id] = selected_names

    # Philosophy Match: запись сигналов
    if stage == "guidance":
        mode_id = mode_tag or ("existential" if _is_existential(user_text) else None)
        pm_record_signal(user_id, lens_ids=selected_names, mode_id=mode_id)

    # Philosophy Match: мягкая подсказка (пропуск при force_philosophy_mode)
    if not plan.get("force_philosophy_mode"):
        pm_suggestion = _maybe_suggest_philosophy_match(user_id, stage, is_safety=False)
        if pm_suggestion:
            reply_text = reply_text.rstrip() + "\n\n" + pm_suggestion

    # Session close choice (уже добавлен в pattern engine для guidance при ENABLE_PATTERN_ENGINE)
    if (
        want_option_close
        and not (ENABLE_PATTERN_ENGINE and stage == "guidance")
    ):
        reply_text = reply_text.rstrip() + "\n\nХочешь продолжить: (1) про причины или (2) про следующий шаг?"

    # Agency v13: strip meta format questions (warmup/guidance only, not safety)
    meta_stripped = 0
    if stage in ("warmup", "guidance"):
        reply_text, meta_stripped = strip_meta_format_questions(reply_text)
    if DEBUG and stage in ("warmup", "guidance"):
        print(f"[Phi DEBUG] agency: meta_questions_stripped={meta_stripped}")

    # DEBUG: только в логах, НЕ в тексте ответа
    if DEBUG:
        detected_modes = ",".join(selected_names) if stage == "guidance" and selected_names else stage
        if mode_tag:
            detected_modes = f"{detected_modes}+{mode_tag}" if detected_modes != stage else mode_tag
        print(f"[Phi DEBUG] mode={detected_modes} stage={stage}" + (f" pattern={pattern_id}" if pattern_id else ""))

    # v17: practice cooldown при выводе практики; tick lens_lock и cooldown
    if stage == "guidance":
        if contains_practice(reply_text) and not forbid_practice:
            state["practice_cooldown_turns"] = COOLDOWN_AFTER_PRACTICE
        tick_practice_cooldown(state)
        tick_lens_lock(state)

    # История и last texts для context
    append_history(HISTORY_STORE, user_id, "user", user_text)
    append_history(HISTORY_STORE, user_id, "assistant", reply_text)
    state["last_user_text"] = user_text
    state["last_bot_text"] = reply_text

    # Логирование диалога
    log_dialog(user_id, user_text, selected_names if stage == "guidance" else [], reply_text)
    if DEBUG and pattern_id:
        print(f"[Phi DEBUG] pattern_id={pattern_id}")

    # Unified send pipeline (sanitize внутри send_text)
    save_state(_state_to_persist())
    await send_text(bot, message.chat.id, reply_text, reply_markup=FEEDBACK_KEYBOARD)


@dp.message(F.voice)
async def handle_voice(message: Message) -> None:
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
        await process_user_query(message, user_text)
    except Exception as e:
        if status_msg:
            await status_msg.edit_text(f"Не удалось обработать голос: {e}")


@dp.message(F.text)
async def handle_message(message: Message) -> None:
    """Обработка текстовых сообщений."""
    await process_user_query(message, message.text or "")


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
        return web.Response(text="ok")

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
        app.router.add_get("/health", lambda r: web.Response(text="ok"))
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
