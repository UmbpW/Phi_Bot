"""Unified send pipeline: single point for all user-facing messages."""

import re
from typing import Optional, Any, TYPE_CHECKING, List

from utils.output_sanitizer import sanitize_output

if TYPE_CHECKING:
    from aiogram.types import Message

# v21.2: Telegram limit 4096, safe split threshold
TELEGRAM_SAFE_SPLIT_THRESHOLD = 3500

# v21.5: meta-openers — удалять из начала частей 2+ при split (чтобы второе сообщение не начиналось с «Когда X...»)
META_OPENER_STARTS = (
    "когда ответов много", "когда внутри нет ясности", "когда нет ясности",
    "когда внутри много", "когда легко утонуть", "когда легко запутаться",
)


def _strip_meta_opener_from_start(text: str) -> str:
    """Удалить первое предложение, если начинается с meta-opener."""
    if not text or not text.strip():
        return text
    parts = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)
    first = parts[0].strip().lower()
    if any(first.startswith(p) for p in META_OPENER_STARTS):
        return parts[1].strip() if len(parts) > 1 else ""
    return text.strip()


def _split_by_paragraphs(text: str, max_chars: int = TELEGRAM_SAFE_SPLIT_THRESHOLD) -> List[str]:
    """Разбить текст на части по абзацам, каждая не больше max_chars."""
    if not text or len(text) <= max_chars:
        return [text] if text else []
    paragraphs = text.split("\n\n")
    parts = []
    current = []
    current_len = 0
    for para in paragraphs:
        para_len = len(para) + 2  # +2 for \n\n
        if current_len + para_len > max_chars and current:
            parts.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += para_len
    if current:
        parts.append("\n\n".join(current))
    return parts


async def send_text(
    bot,
    chat_id: int,
    text: str,
    *,
    stage: Optional[str] = None,
    parse_mode: Optional[str] = None,
    reply_markup: Optional[Any] = None,
) -> Optional["Message"]:
    """Отправка текста пользователю. sanitize_output — последний шаг перед отправкой.
    v21.2: если текст > 3500 символов — разбить на 2 сообщения по абзацам."""
    if not text:
        return None
    clean_text = sanitize_output(text)
    if not clean_text:
        return None

    parts = _split_by_paragraphs(clean_text)
    # v21.5: у частей 2+ убрать meta-opener в начале (иначе второе сообщение начинается с «Когда X...»)
    for i in range(1, len(parts)):
        stripped = _strip_meta_opener_from_start(parts[i])
        if stripped:
            parts[i] = stripped
    parts = [p for p in parts if p.strip()]
    last_msg = None
    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        last_msg = await bot.send_message(
            chat_id=chat_id,
            text=part,
            parse_mode=parse_mode,
            reply_markup=reply_markup if is_last else None,  # keyboard только на последнем
        )
    return last_msg
