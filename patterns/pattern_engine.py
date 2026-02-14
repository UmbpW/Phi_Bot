"""Pattern engine для UX-ответов: bridge lines, fork-questions, constraints."""

import re
import random
from pathlib import Path
from typing import Any, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PATTERNS_CACHE: Optional[dict] = None


def load_patterns(path: str = "dialogue_patterns.yaml") -> dict:
    """Загружает YAML с паттернами. Кеширует результат."""
    global _PATTERNS_CACHE
    if _PATTERNS_CACHE is not None:
        return _PATTERNS_CACHE

    try:
        import yaml
    except ImportError:
        return {}

    for base in (_PROJECT_ROOT, _PROJECT_ROOT / "patterns"):
        filepath = base / path if "/" not in path else base / Path(path).name
        if filepath.exists():
            with open(filepath, encoding="utf-8") as f:
                _PATTERNS_CACHE = yaml.safe_load(f) or {}
            return _PATTERNS_CACHE

    _PATTERNS_CACHE = {}
    return _PATTERNS_CACHE


def choose_pattern(stage: str, context: dict) -> Optional[dict]:
    """Выбирает pattern по stage и context flags."""
    data = load_patterns()
    patterns = data.get("patterns", [])
    if not patterns:
        return None

    is_safety = context.get("is_safety", False)
    is_resistance = context.get("is_resistance", False)
    is_confusion = context.get("is_confusion", False)
    want_fork = context.get("want_fork", False)

    if is_safety:
        for p in patterns:
            if p.get("id") == "S1_soft_safety_bridge":
                return p
        return None

    if is_resistance and stage == "guidance":
        for p in patterns:
            if p.get("id") == "R1_gentle_deflection_accept":
                return p
        return None

    if is_confusion:
        if stage == "warmup":
            for p in patterns:
                if p.get("id") == "C2_uncertainty_soft_frame":
                    return p
        else:
            for p in patterns:
                if p.get("id") == "C1_reduce_scope":
                    return p
        return None

    if stage == "warmup":
        for p in patterns:
            if p.get("id") == "W1_human_bridge_opening":
                return p
        return None

    if stage == "guidance":
        if want_fork:
            for p in patterns:
                if p.get("id") == "G2_fork_question":
                    return p
        for p in patterns:
            if p.get("id") == "G1_one_frame_only":
                return p
        return None

    return None


def render_pattern(pattern: dict) -> str:
    """Собирает текст из structure и случайных template строк."""
    if not pattern:
        return ""
    structure = pattern.get("structure", [])
    templates = pattern.get("templates", {})
    parts = []
    for key in structure:
        opts = templates.get(key)
        if not opts:
            continue
        if isinstance(opts, list):
            if key == "bullets":
                n = min(3, max(2, len(opts)))
                chosen = random.sample(opts, n) if len(opts) >= n else opts
                parts.extend(chosen)
            else:
                parts.append(random.choice(opts))
        else:
            parts.append(str(opts))
    return "\n".join(p for p in parts if p.strip())


def enforce_constraints(
    text: str,
    stage: str,
    constraints: dict,
) -> str:
    """Применяет global_constraints: лимит вопросов, forbid_phrases, max_lines, first_line_max_words."""
    if not text or not text.strip():
        return text

    q_limits = constraints.get("question_limits", {})
    forbid = constraints.get("forbid_phrases", [])
    # v17 RESPONSE_LENGTH_POLICY: guidance max_lines=18, min 8; no summary-trimming
    max_lines = constraints.get("max_lines", 10)
    if stage == "guidance":
        max_lines = 18
    first_line_words = constraints.get("first_line_max_words", 12)

    # 1) forbid_phrases: удалить строки, содержащие их
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    filtered_lines = []
    for ln in lines:
        ln_lower = ln.lower()
        if any(phrase.lower() in ln_lower for phrase in forbid):
            continue
        filtered_lines.append(ln)
    text = "\n".join(filtered_lines)

    # 2) question limits (строго: warmup=1, guidance=2, safety=1)
    max_q = 1 if stage == "warmup" else (1 if stage == "safety" else min(2, q_limits.get(stage, 2)))
    parts = re.split(r"([?？])", text)
    q_positions = [i for i, p in enumerate(parts) if p in ("?", "？")]
    if len(q_positions) > max_q:
        last_idx = q_positions[max_q - 1]
        text = "".join(parts[: last_idx + 1]).rstrip()

    # 3) max_lines
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        text = "\n".join(lines)

    # 4) first_line_max_words
    lines = text.split("\n")
    if lines and first_line_words:
        first = lines[0]
        words = first.split()
        if len(words) > first_line_words:
            lines[0] = " ".join(words[:first_line_words])
            text = "\n".join(lines)

    return text.strip()


ECHO_OPENING_STARTS = ("слышу", "похоже", "ты хочешь", "тебя беспокоит", "тебя тревожит")

# Bridge variety pool по категориям (избегаем повторения)
BRIDGE_BY_CATEGORY = {
    "load": [
        "С таким фоном тяжело долго держаться.",
        "Такой груз непросто носить одному.",
        "С таким давлением трудно оставаться спокойным.",
    ],
    "fatigue": [
        "Когда сил мало — каждое решение даётся тяжело.",
        "Когда внутри много напряжения — это выматывает.",
        "Такой фон может сильно изматывать.",
    ],
    "irritation": [
        "С таким раздражением непросто сосредоточиться.",
        "С этим трудно оставаться собранным.",
    ],
    "uncertainty": [
        "Когда нет ясности — опора теряется.",
        "В таком состоянии легко накрутиться.",
    ],
}
BRIDGE_CATEGORIES = list(BRIDGE_BY_CATEGORY.keys())


def _starts_with_echo(text: str) -> bool:
    """Проверяет, начинается ли первая строка с echo-opening."""
    first_line = (text.split("\n")[0] if text else "").strip().lower()
    return any(first_line.startswith(phrase) for phrase in ECHO_OPENING_STARTS)


def build_ux_prefix(stage: str, context: dict, state: Optional[dict] = None):
    """Возвращает (bridge_line, chosen_category). Не повторяет last_bridge_category."""
    state = state or {}
    last_cat = state.get("last_bridge_category")
    available = [c for c in BRIDGE_CATEGORIES if c != last_cat] or BRIDGE_CATEGORIES
    cat = random.choice(available)
    opts = BRIDGE_BY_CATEGORY.get(cat, [])
    if opts:
        return random.choice(opts), cat
    # fallback to YAML
    data = load_patterns()
    patterns = data.get("patterns", [])
    for p in patterns:
        if p.get("id") in ("W3_non_clinical_empathy", "W1_human_bridge_opening"):
            templates = p.get("templates", {}).get("bridge_line", [])
            if templates:
                return random.choice(templates), cat
    return None, None


def strip_echo_first_line(text: str) -> str:
    """Удаляет первую строку, если она echo-opening."""
    if not text or not _starts_with_echo(text):
        return text
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if len(lines) <= 1:
        return text
    return "\n".join(lines[1:]).strip()


def get_option_close_line() -> str:
    """Возвращает одну случайную строку развилки из G4_option_close."""
    data = load_patterns()
    patterns = data.get("patterns", [])
    for p in patterns:
        if p.get("id") == "G4_option_close":
            opts = p.get("templates", {}).get("choice", [])
            if opts:
                return random.choice(opts)
    return "Хочешь продолжить: (1) про причины или (2) про следующий шаг?"
