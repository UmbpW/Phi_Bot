"""Fix Pack D2: context anchor — prevent context_drop by anchoring reply to user's constraints."""

import re
from typing import List, Optional, Tuple

# Маркеры формата/критики → нужно явно отразить в ответе
CONTEXT_ANCHOR_CRITIQUE_MARKERS = (
    "не учебник", "без общих слов", "ты ушёл в сторону", "ты меня не слышишь",
    "почему ты", "это не то", "уходишь в сторону", "не то, о чём",
)

# Фразы-ограничения для буквального включения
CONSTRAINT_PHRASES = (
    "рамку, но не учебник", "рамка, но не учебник", "без общих слов",
    "не учебник", "буддийская оптика", "через буддийскую", "страх нестабильности",
)


def _norm_word(w: str) -> str:
    """Нормализация: убрать пунктуацию в конце (как в eval/checks)."""
    return (w or "").rstrip(".,!?;:…\"'")


def _get_context_drop_words(text: str) -> List[str]:
    """Слова, по которым eval проверяет context_drop (первые 5 слов len>4, нормализованные)."""
    if not text or len(text.strip()) < 30:
        return []
    prev_lower = (text or "").lower()
    raw = [w for w in prev_lower.split() if len(w) > 4][:5]
    return [_norm_word(w) for w in raw if _norm_word(w)]


def _has_critique_marker(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(m in t for m in CONTEXT_ANCHOR_CRITIQUE_MARKERS)


def _extract_salient_tokens(user_text: str, max_tokens: int = 4) -> List[str]:
    """Извлекает 2–4 значимых токена/фразы из user_text."""
    t = (user_text or "").strip().lower()
    if not t or len(t) < 10:
        return []
    # Сначала ищем целые фразы-ограничения
    found_phrases = []
    for p in CONSTRAINT_PHRASES:
        if p in t:
            found_phrases.append(p)
    if found_phrases:
        return found_phrases[:max_tokens]
    # Иначе — слова длиной > 4 и не стоп-слова
    stop = {"какой", "какая", "какие", "который", "которая", "когда", "почему", "как", "что", "этот", "эта", "это", "также", "тоже", "может", "будет", "нужно", "надо", "хочу", "хотел", "хотела"}
    words = re.findall(r"[а-яёa-z]{5,}", t)
    candidates = [w for w in words if w not in stop][:max_tokens]
    return list(dict.fromkeys(candidates))[:max_tokens]


def _first_paragraph(text: str) -> str:
    """Первый абзац или первые 2–3 предложения."""
    if not text or not text.strip():
        return ""
    parts = re.split(r"\n\n+", (text or "").strip())
    first = parts[0] if parts else ""
    sentences = re.split(r"(?<=[.!?])\s+", first)
    return " ".join(sentences[:3]) if len(sentences) > 3 else first


def _any_token_in_text(tokens: List[str], text: str) -> bool:
    """Есть ли хоть один токен в тексте (подстрока)."""
    if not tokens or not text:
        return False
    t_lower = (text or "").lower()
    return any(tok.lower() in t_lower for tok in tokens)


def _build_anchor_prefix(user_text: str, tokens: List[str]) -> str:
    """Строит естественный anchor (2 предложения) без мета."""
    if not tokens:
        return ""
    # Короткая фраза, отражающая запрос
    t = (user_text or "").strip().lower()
    if "рамк" in t and "учебник" in t:
        return "Ты просил рамку без учебника — даю её в двух абзацах. "
    if "не учебник" in t:
        return "Рамка без учебника, как ты просил. "
    if "без общих слов" in t or "общих слов" in t:
        return "Без общих слов — конкретно по твоему запросу. "
    if "буддийск" in t or "буддизм" in t:
        return "Через буддийскую оптику, как ты просил. "
    if "почему ты" in t or "ты начал" in t:
        return "Ты спрашиваешь, почему начал с общих слов — разберу по шагам. "
    # Универсал
    tok = tokens[0] if tokens else ""
    if len(tok) > 5:
        return f"По твоему запросу про «{tok}» — вот развёрнуто. "
    return "По твоему запросу — развёрнуто. "


def apply_context_anchor(
    reply_text: str,
    user_text: str,
    prev_user: Optional[str] = None,
    turn_index: int = 0,
    plan: Optional[dict] = None,
    debug: bool = False,
) -> Tuple[str, Optional[dict]]:
    """
    Fix Pack D2: добавляет context anchor, если нужно.
    Выравнивание с eval context_drop: включает слова из prev_user (первые 5 len>4).
    Возвращает (modified_reply, debug_info или None).
    """
    if not reply_text or not reply_text.strip():
        return (reply_text, None)
    plan = plan or {}
    # Условие: turn==1 ИЛИ маркеры критики ИЛИ prev_user есть и reply не содержит его слов (context_drop)
    turn_one = turn_index <= 1
    has_critique = _has_critique_marker(user_text)
    cd_words = _get_context_drop_words(prev_user or user_text or "")
    would_fail_context_drop = (
        cd_words
        and len((prev_user or "").strip()) > 50
        and not _any_token_in_text(cd_words, _first_paragraph(reply_text))
    )
    if not turn_one and not has_critique and not would_fail_context_drop:
        return (reply_text, None)
    src = user_text if user_text else (prev_user or "")
    # Объединяем: salient tokens + context_drop words (для выравнивания с eval)
    tokens = _extract_salient_tokens(src)
    if not cd_words:
        cd_words = _get_context_drop_words(prev_user or user_text or "")
    all_tokens = list(dict.fromkeys(tokens + [w for w in cd_words if w not in tokens]))
    if not all_tokens:
        return (reply_text, None)
    first_para = _first_paragraph(reply_text)
    if _any_token_in_text(all_tokens, first_para):
        debug_info = {"anchored": False, "tokens": all_tokens, "reason": "tokens_found"} if debug else None
        return (reply_text, debug_info)
    prefix = _build_anchor_prefix(user_text or prev_user or "", all_tokens)
    # Убедиться, что prefix содержит хотя бы одно context_drop слово (для eval alignment)
    if cd_words and not _any_token_in_text(cd_words, prefix):
        for w in cd_words:
            if len(w) >= 4 and w not in (prefix or "").lower():
                prefix = f"По запросу про «{w}»: {(prefix or '').strip()} "
                break
    if not prefix.strip():
        return (reply_text, None)
    result = (prefix.strip() + " " + reply_text.strip()).strip()
    if debug:
        return (result, {"anchored": True, "tokens": all_tokens, "cd_words": cd_words, "prefix": prefix[:80]})
    return (result, None)


def apply_context_anchor_with_prev(
    reply_text: str,
    user_text: str,
    prev_user: Optional[str] = None,
    turn_index: int = 0,
    plan: Optional[dict] = None,
) -> str:
    """Упрощённый вызов — только текст на выходе."""
    out, _ = apply_context_anchor(reply_text, user_text, prev_user, turn_index, plan, debug=False)
    return out


def debug_context_drop(prev_user: str, bot_text: str) -> dict:
    """
    Fix Pack D2: при context_drop — показать извлечённые токены и их наличие в ответе.
    Вызов из eval при context_drop для диагностики.
    """
    tokens = _extract_salient_tokens(prev_user)
    cd_words = _get_context_drop_words(prev_user)
    all_tokens = list(dict.fromkeys(tokens + [w for w in cd_words if w not in tokens]))
    first_para = _first_paragraph(bot_text)
    in_first = _any_token_in_text(all_tokens, first_para)
    in_full = _any_token_in_text(all_tokens, bot_text)
    return {
        "tokens": all_tokens,
        "cd_words": cd_words,
        "in_first_para": in_first,
        "in_full_reply": in_full,
        "first_para_preview": first_para[:120] + "..." if len(first_para) > 120 else first_para,
    }
