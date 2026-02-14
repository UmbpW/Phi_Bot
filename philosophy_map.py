"""Маппинг линз/режимов на философские оптики и scoring."""

from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent

PHILOSOPHY_MAP: dict[str, dict[str, Any]] = {
    "camus_absurd": {
        "weights": {
            "existential": 2.0,
            "narrative": 1.5,
            "mortality_focus": 1.0,
        },
        "card": "philosophy/camus_absurd.md",
    },
    "frankl_meaning": {
        "weights": {
            "existential": 1.5,
            "mortality_focus": 2.0,
            "control_scope": 1.0,
            "expectation_gap": 0.5,
        },
        "card": "philosophy/frankl_meaning.md",
    },
    "stoic_control": {
        "weights": {
            "control_scope": 2.0,
            "role_position": 1.5,
            "expectation_gap": 1.0,
        },
        "card": "philosophy/stoic_control.md",
    },
    "epicurean_simple": {
        "weights": {
            "psychology": 1.0,
            "micro_agency": 2.0,
            "boundary": 1.5,
            "control_scope": 0.5,
        },
        "card": "philosophy/epicurean_simple.md",
    },
    "narrative_identity": {
        "weights": {
            "narrative": 2.0,
            "expectation_gap": 1.0,
        },
        "card": "philosophy/narrative_identity.md",
    },
}

# Алиас: lens_id -> ключ для весов (без lens_)
LENS_TO_SIGNAL: dict[str, str] = {
    "control_scope": "control_scope",
    "micro_agency": "micro_agency",
    "boundary": "boundary",
    "expectation_gap": "expectation_gap",
    "role_position": "role_position",
    "narrative": "narrative",
    "mortality_focus": "mortality_focus",
    "psychology": "psychology",
    "existence": "existential",
}

# mode_tag -> сигнал
MODE_TO_SIGNAL: dict[str, str] = {
    "financial_pattern_confusion": "expectation_gap",
    "existential": "existential",
}


def _get_counts(profile: dict[str, Any]) -> dict[str, float]:
    """Собирает lens_counts + mode_counts в единый словарь сигналов."""
    counts: dict[str, float] = {}
    for key, val in profile.get("lens_counts", {}).items():
        signal = LENS_TO_SIGNAL.get(key, key)
        counts[signal] = counts.get(signal, 0) + val
    for key, val in profile.get("mode_counts", {}).items():
        signal = MODE_TO_SIGNAL.get(key, key)
        counts[signal] = counts.get(signal, 0) + val
    return counts


def pm_score_philosophies(profile: dict[str, Any]) -> tuple:
    """Считает баллы по философиям, возвращает (best_id, confidence 0..1)."""
    counts = _get_counts(profile)
    total_signals = sum(counts.values())
    if total_signals == 0:
        return None, 0.0

    best_id: Optional[str] = None
    best_score = 0.0

    for pid, data in PHILOSOPHY_MAP.items():
        weights = data.get("weights", {})
        score = 0.0
        for signal, weight in weights.items():
            score += (counts.get(signal, 0) or 0) * weight
        if score > best_score:
            best_score = score
            best_id = pid

    if not best_id or best_score <= 0:
        return None, 0.0

    all_scores = []
    for data in PHILOSOPHY_MAP.values():
        weights = data.get("weights", {})
        s = sum((counts.get(k, 0) or 0) * v for k, v in weights.items())
        all_scores.append(s)
    total_scores = sum(all_scores)
    confidence = best_score / total_scores if total_scores > 0 else 0.0

    return best_id, min(1.0, confidence)
