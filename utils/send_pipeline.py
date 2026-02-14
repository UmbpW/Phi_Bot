"""Unified send pipeline: single point for all user-facing messages."""

from typing import Optional, Any, TYPE_CHECKING

from utils.output_sanitizer import sanitize_output

if TYPE_CHECKING:
    from aiogram.types import Message


async def send_text(
    bot,
    chat_id: int,
    text: str,
    *,
    stage: Optional[str] = None,
    parse_mode: Optional[str] = None,
    reply_markup: Optional[Any] = None,
) -> Optional["Message"]:
    """Отправка текста пользователю. sanitize_output — последний шаг перед отправкой."""
    if not text:
        return None
    clean_text = sanitize_output(text)
    if not clean_text:
        return None
    return await bot.send_message(
        chat_id=chat_id,
        text=clean_text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )
