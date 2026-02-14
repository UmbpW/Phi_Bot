"""
Phi Bot — Telegram-бот MVP на aiogram 3.x.
Запуск: python bot.py
"""

import asyncio
import os
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
)
from router import select_lenses, detect_financial_pattern
from safety import check_safety, get_safe_response

BOT_VERSION = "Phi_Bot v10-prod"
DEBUG = True

# Stage machine v8: warmup | guidance
USER_STAGE: dict[int, str] = {}
USER_MSG_COUNT: dict[int, int] = {}

META_LECTURE_PATTERNS = (
    "скажу честно", "по философии", "как учит", "правильный взгляд",
    "согласно учению", "в философии", "философы считают",
)

GUIDANCE_TRIGGERS = (
    "что делать", "как быть", "что делать дальше", "помоги решить",
    "что мне делать", "подскажи что", "посоветуй что",
)

# Загрузка .env из папки Phi_Bot
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

TELEGRAM_TOKEN = (os.getenv("TELEGRAM_TOKEN") or "").strip()
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = (os.getenv("OPENAI_MODEL") or "gpt-5.2-codex").strip()
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
EXPORT_TOKEN = (os.getenv("EXPORT_TOKEN") or "").strip()

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не задан в .env")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не задан в .env")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
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


def call_openai(system_prompt: str, user_text: str, force_short: bool = False) -> str:
    """Вызывает OpenAI Responses API и возвращает текст ответа."""
    inst = system_prompt
    if force_short:
        inst += "\n\nОтветь короче и разговорнее. Без лекций."
    try:
        response = openai_client.responses.create(
            model=OPENAI_MODEL,
            instructions=inst,
            input=user_text,
        )
        # Извлекаем текст: SDK может иметь output_text или output[].content[].text
        text_parts = []
        if hasattr(response, "output_text") and response.output_text:
            return str(response.output_text).strip()
        if hasattr(response, "output") and response.output:
            for item in response.output:
                content = getattr(item, "content", None) or []
                for block in content:
                    text = getattr(block, "text", None)
                    if text:
                        text_parts.append(str(text))
        result = "\n".join(text_parts).strip() if text_parts else ""
        return result or "Не удалось получить ответ."
    except Exception as e:
        return f"Ошибка API: {str(e)}"


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
    await message.answer(
        "Привет! Я Phi Bot — AI-помощник.\n"
        "Напишите или наговорите любой вопрос."
    )


@dp.message(Command("about"))
async def cmd_about(message: Message) -> None:
    """Дисклеймер и описание бота."""
    await message.answer(ABOUT_TEXT)


@dp.message(Command("version"))
async def cmd_version(message: Message) -> None:
    """Версия бота."""
    await message.answer(BOT_VERSION)


async def process_user_query(message: Message, user_text: str) -> None:
    """Обрабатывает текст пользователя (общая логика для текста и голоса)."""
    user_id = message.from_user.id if message.from_user else 0

    if not user_text:
        await message.answer("Не удалось распознать текст. Попробуйте написать или записать снова.")
        return

    # Safety-фильтр
    if check_safety(user_text):
        safe_text = get_safe_response()
        await message.answer(safe_text)
        log_safety_event(user_id, user_text)
        return

    # Stage machine v8
    USER_MSG_COUNT[user_id] = USER_MSG_COUNT.get(user_id, 0) + 1
    stage = _get_stage(user_id, user_text)
    USER_STAGE[user_id] = stage

    mode_tag = None
    if stage == "warmup":
        # Warmup: без линз, только зеркало
        system_prompt = load_warmup_prompt()
        selected_names = []
    else:
        # Guidance: system + линзы + existential limiter
        main_prompt = load_system_prompt()
        all_lenses = load_all_lenses()
        if detect_financial_pattern(user_text):
            selected_names = ["lens_expectation_gap", "lens_control_scope"]
            mode_tag = "financial_pattern_confusion"
        else:
            selected_names = select_lenses(user_text, all_lenses, max_lenses=3)
            # lens_general запрещён в guidance — заменяем на control_scope
            if "lens_general" in selected_names and "lens_control_scope" in all_lenses:
                selected_names = [
                    "lens_control_scope" if n == "lens_general" else n
                    for n in selected_names
                ]
                selected_names = list(dict.fromkeys(selected_names))  # dedup, order preserved
        lens_contents = [all_lenses.get(name, "") for name in selected_names]
        lens_contents = [c for c in lens_contents if c]
        system_prompt = build_system_prompt(main_prompt, lens_contents)
        # Existential limiter: max 2 рамки, ≤2 предложения каждая
        system_prompt += "\n\nExistential: макс. 2 рамки, каждая ≤2 предложения."

    # Вызов OpenAI
    reply_text = call_openai(system_prompt, user_text)

    # Voice guard: если мета-лекционный тон — перегенерировать
    if _is_meta_lecture(reply_text):
        reply_text = call_openai(system_prompt, user_text, force_short=True)

    # Existential limiter: если режим existential → обрезать до 2 рамок
    if stage == "guidance" and _is_existential(user_text):
        reply_text = _trim_existential(reply_text)

    # Debug-метка (только при DEBUG=True)
    detected_modes = ",".join(selected_names) if stage == "guidance" and selected_names else stage
    if mode_tag:
        detected_modes = f"{detected_modes}+{mode_tag}" if detected_modes != stage else mode_tag
    if DEBUG:
        reply_text = f"{reply_text}\n\n[mode: {detected_modes} | stage: {stage}]"

    # Логирование диалога
    log_dialog(user_id, user_text, selected_names if stage == "guidance" else [], reply_text)

    # Отправка ответа с кнопками фидбека
    await message.answer(reply_text, reply_markup=FEEDBACK_KEYBOARD)


@dp.message(F.voice)
async def handle_voice(message: Message) -> None:
    """Обработка голосовых сообщений."""
    status = await message.answer("Слушаю...")
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
        await status.delete()
        await process_user_query(message, user_text)
    except Exception as e:
        await status.edit_text(f"Не удалось обработать голос: {e}")


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


async def main() -> None:
    """Запуск бота."""
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    print(f"Подключено к Telegram: @{me.username}")

    if DATABASE_URL:
        conn = _get_db_conn()
        print(f"[DB] PostgreSQL: {'OK' if conn else 'FAIL (см. лог выше)'}")

    port = int(os.getenv("PORT", "0"))
    if port > 0 and DATABASE_URL and EXPORT_TOKEN:
        asyncio.create_task(_run_export_server())
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
