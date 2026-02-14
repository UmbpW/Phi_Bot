"""Постобработка ответа: ограничение числа вопросов."""

import re


def postprocess_response(text: str, stage: str) -> str:
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
        return text

    # Обрезаем: оставляем содержимое до и включая max_q-й знак вопроса
    last_q_idx = q_positions[max_q - 1]
    end_slice = last_q_idx + 1  # include the ? at parts[last_q_idx]
    truncated = "".join(parts[:end_slice]).rstrip()
    # Убираем висящие союзы/частицы в конце
    truncated = re.sub(r"\s+[иИ\sаА\s]+$", "", truncated)
    return truncated.strip()
