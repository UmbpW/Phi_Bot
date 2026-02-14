"""Unified send pipeline: single point for all user-facing messages."""

from typing import Optional, Any, TYPE_CHECKING, List

from utils.output_sanitizer import sanitize_output

if TYPE_CHECKING:
    from aiogram.types import Message

# v21.2: Telegram limit 4096, safe split threshold
TELEGRAM_SAFE_SPLIT_THRESHOLD = 3500


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
