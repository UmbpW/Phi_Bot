"""v17.2 Multi-school blocker: при >1 философских блоков — оставить только первый."""

import re

# Маркеры философских школ/имён (для детекции блоков)
PHILOSOPHER_MARKERS = (
    "стоик", "сенека", "эпиктет", "марк аврелий",
    "камю", "франкл", "экзистенциал", "экзистенциалист",
    "даос", "будд", "эпикур", "конфуци",
    "ницше", "киркегор", "camus", "frank",
)


def _count_philosopher_blocks(text: str) -> int:
    """Считает параграфы, содержащие упоминания философов."""
    if not text:
        return 0
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    count = 0
    for block in blocks:
        t = block.lower()
        if any(m in t for m in PHILOSOPHER_MARKERS):
            count += 1
    return count


def apply_multi_school_blocker(text: str) -> str:
    """Если >1 блок с философами — оставить первый, остальные философские блоки удалить."""
    if not text or not text.strip():
        return text
    if _count_philosopher_blocks(text) <= 1:
        return text
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    result = []
    seen_philosopher_block = False
    for block in blocks:
        t = block.lower()
        has_philosopher = any(m in t for m in PHILOSOPHER_MARKERS)
        if has_philosopher:
            if not seen_philosopher_block:
                result.append(block)
                seen_philosopher_block = True
        else:
            result.append(block)
    return "\n\n".join(result) if result else text
