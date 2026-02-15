"""OpenAI client для Phi Bot. Общий для bot и eval."""

import os
from typing import Optional
from dotenv import load_dotenv
from pathlib import Path
from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = (os.getenv("OPENAI_MODEL") or "gpt-5.2").strip()
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def _extract_response_text(response) -> str:
    if hasattr(response, "output_text") and response.output_text:
        return str(response.output_text).strip()
    text_parts = []
    if hasattr(response, "output") and response.output:
        for item in response.output:
            content = getattr(item, "content", None) or []
            for block in content:
                text = getattr(block, "text", None)
                if text:
                    text_parts.append(str(text))
    result = "\n".join(text_parts).strip() if text_parts else ""
    return result or "Не удалось получить ответ."


def call_openai(
    system_prompt: str,
    user_text: str,
    force_short: bool = False,
    context_block: str = "",
    model_override: Optional[str] = None,
) -> str:
    """Вызывает OpenAI Responses API."""
    model_name = model_override or OPENAI_MODEL
    inst = system_prompt
    if force_short:
        inst += "\n\nОтветь короче и разговорнее. Без лекций."
    input_text = user_text
    if context_block:
        input_text = f"[Контекст диалога]\n{context_block}\n\n[Текущее сообщение]\n{user_text}"
    if not openai_client:
        return "[LLM не настроен]"
    try:
        response = openai_client.responses.create(model=model_name, instructions=inst, input=input_text)
        return _extract_response_text(response)
    except Exception as e:
        try:
            response = openai_client.responses.create(model="gpt-4.1-mini", instructions=inst, input=input_text)
            return _extract_response_text(response)
        except Exception as e2:
            return f"Ошибка API: {str(e2)}"
