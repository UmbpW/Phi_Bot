"""LLM-симулятор пользователя для eval. Модель gpt-4.1-mini."""

import os
from typing import Any, Optional

from dotenv import load_dotenv
from pathlib import Path
from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

_openai_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            raise ValueError("OPENAI_API_KEY не задан")
        _openai_client = OpenAI(api_key=key)
    return _openai_client


def _format_history(history: list[dict]) -> str:
    """Форматирует историю для промпта."""
    lines = []
    for h in history:
        role = h.get("role", "")
        content = (h.get("content", "") or "")[:500]
        label = "Ты (пользователь):" if role == "user" else "Бот:"
        lines.append(f"{label} {content}")
    return "\n\n".join(lines) if lines else ""


def synth_user_next(
    persona: dict,
    scenario: dict,
    history: list[dict],
) -> str:
    """Следующее сообщение синтетического пользователя.

    persona: из synth_personas.yaml
    scenario: из synth_scenarios.yaml
    history: [{"role":"user"|"assistant","content":...}]
    """
    client = _get_client()
    style = persona.get("speaking_style", {})
    triggers = persona.get("triggers", {})
    goals = persona.get("goals", [])
    adv = persona.get("adversarial_moves", [])
    bg = persona.get("background", "")

    system = f"""Ты не ассистент, ты живой пользователь. Персона: {bg}

Стиль: verbosity={style.get('verbosity','medium')}, tone={style.get('tone','calm')}

Триггеры: hates_warmup={triggers.get('hates_warmup')}, hates_short_answers={triggers.get('hates_short_answers')}

Цели: {', '.join(goals[:3])}

Правила:
- Говори коротко, естественно
- Не используй списки и структуру
- Иногда раздражайся, иногда проси объяснить шире
- Можешь задавать уточняющие вопросы
- НЕ помогай боту, НЕ анализируй стиль, НЕ будь идеальным
- Пиши как в мессенджере, 1-3 предложения"""

    hist_str = _format_history(history)
    scenario_title = scenario.get("title", "")
    seed = scenario.get("seed_message", "")

    if not hist_str:
        user_content = f"Сценарий: {scenario_title}. Первое сообщение: {seed}"
    else:
        user_content = f"Сценарий: {scenario_title}. Диалог:\n\n{hist_str}\n\nТвоё следующее сообщение (1-3 предложения, как живой пользователь):"

    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            instructions=system,
            input=user_content,
            temperature=0.6,
            max_output_tokens=180,
        )
        if hasattr(response, "output_text") and response.output_text:
            text = str(response.output_text).strip()
        else:
            text_parts = []
            if hasattr(response, "output") and response.output:
                for item in response.output:
                    content = getattr(item, "content", None) or []
                    for block in content:
                        t = getattr(block, "text", None)
                        if t:
                            text_parts.append(str(t))
            text = "\n".join(text_parts).strip() if text_parts else "[пусто]"
        return (text or "[пусто]")[:500]
    except Exception as e:
        return f"[Ошибка симулятора: {e}]"
