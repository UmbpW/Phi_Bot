"""Постобработка ответа: ограничение числа вопросов, style guards."""

import re


def _apply_style_guards(text: str) -> str:
    """v17: удаление BAN_PHRASES и directive/meta-фраз."""
    from philosophy.style_guards import apply_style_guards as _guard
    return _guard(text)


def postprocess_response(
    text: str,
    stage: str,
    philosophy_pipeline: bool = False,
) -> str:
    """Ограничивает количество вопросов в ответе по stage.

    - warmup: максимум 1 вопрос
    - guidance: максимум 2 вопроса
    - safety: максимум 1 вопрос (но safety отвечает отдельно, сюда не доходит)
    """
    if not text or not text.strip():
        return text

    # Считаем вопросительные предложения (?, ？)
    parts = re.split(r"([?？])", text)
    # parts чередуются: ['before1', '?', 'before2', '?', 'rest']
    q_positions = [i for i, p in enumerate(parts) if p in ("?", "？")]
    q_count = len(q_positions)

    max_q = 1 if stage == "warmup" else 2
    if q_count <= max_q:
        result = _apply_style_guards(text)
        if philosophy_pipeline:
            from philosophy.multi_school_blocker import apply_multi_school_blocker
            result = apply_multi_school_blocker(result)
        return result

    # Обрезаем: оставляем содержимое до и включая max_q-й знак вопроса
    last_q_idx = q_positions[max_q - 1]
    end_slice = last_q_idx + 1  # include the ? at parts[last_q_idx]
    truncated = "".join(parts[:end_slice]).rstrip()
    # Убираем висящие союзы/частицы в конце
    truncated = re.sub(r"\s+[иИ\sаА\s]+$", "", truncated)
    result = truncated.strip()
    result = _apply_style_guards(result)
    if philosophy_pipeline:
        from philosophy.multi_school_blocker import apply_multi_school_blocker
        result = apply_multi_school_blocker(result)
    return result
