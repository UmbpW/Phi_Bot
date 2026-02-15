"""Постобработка ответа: ограничение числа вопросов, style guards."""

import logging
import re

_logger = logging.getLogger("phi.telemetry")


def _split_to_sentences(text: str) -> list:
    """Разбить текст на предложения (по . ! ?)."""
    if not text or not text.strip():
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _clamp_max_one_question(text: str) -> str:
    """v20.2: max 1 question — оставить первое предложение с '?', отбросить все последующие."""
    sentences = _split_to_sentences(text)
    if not sentences:
        return text
    for i, s in enumerate(sentences):
        if "?" in s or "？" in s:
            return " ".join(sentences[: i + 1])
    return text


def _apply_style_guards(text: str, ban_empathy_openers: bool = False, answer_first: bool = False) -> str:
    """v17: удаление BAN_PHRASES и directive/meta-фраз.
    v20.2: ban_empathy_openers для finance/philosophy.
    v21: answer_first — extended meta tail ban, empathy opener ban."""
    from philosophy.style_guards import apply_style_guards as _guard
    return _guard(text, ban_empathy_openers=ban_empathy_openers, answer_first=answer_first)


def postprocess_response(
    text: str,
    stage: str,
    philosophy_pipeline: bool = False,
    mode_tag: str | None = None,
    answer_first_required: bool = False,
    explain_mode: bool = False,
) -> str:
    """Ограничивает количество вопросов в ответе.

    v20.2: max 1 вопрос (sentence-level clamp), ban empathy openers для finance/philosophy.
    v21: answer_first — practice clamp, meta tail ban, empathy opener ban.
    """
    if not text or not text.strip():
        return text

    # v21: practice clamp — только первая практика (PATCH 5: + explain_mode)
    if answer_first_required or explain_mode:
        from philosophy.practice_cooldown import clamp_to_first_practice_only
        text = clamp_to_first_practice_only(text)

    # v20.2: max 1 question — keep first sentence with '?', drop all later
    # PATCH 5: explain_mode uses finalize_reply max_questions=0; здесь оставляем clamp
    text = _clamp_max_one_question(text)

    ban_empathy = (
        mode_tag == "financial_rhythm"
        or philosophy_pipeline
        or answer_first_required
        or explain_mode
    )
    result = _apply_style_guards(text, ban_empathy_openers=ban_empathy, answer_first=answer_first_required)

    if philosophy_pipeline:
        from philosophy.multi_school_blocker import apply_multi_school_blocker
        result = apply_multi_school_blocker(result)

    _logger.info(f"[telemetry] questions={result.count('?')}")
    return result
