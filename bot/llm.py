"""LLM через OpenRouter (OpenAI-сумісний API).

Провайдер ЗМІННИЙ: уся робота з моделлю — тут. Локальний Ollama лишився в історії git.
Параметр model дозволяє порівнювати різні моделі (для QA), за замовчуванням — LLM_MODEL.
"""
import json
import re

from openai import OpenAI
from bot.config import LLM_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL

# Чужі символи: CJK/ієрогліфи + латиниця — на випадок, якщо модель «протече».
_FOREIGN = re.compile(r"[　-〿㐀-䶿一-鿿＀-￯]|[A-Za-z]{2,}")
_MAX_RETRIES = 2

_client = None


def _get_client() -> OpenAI:
    """Лінива ініціалізація: ключ потрібен лише на реальний виклик, не на імпорт."""
    global _client
    if _client is None:
        if not OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY порожній — встав ключ у .env")
        _client = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)
    return _client


def reply(history: list[dict], model: str | None = None) -> str:
    """Відповідь власника текстом. Гард на чужі символи з перегенерацією."""
    model = model or LLM_MODEL
    text = ""
    for _ in range(_MAX_RETRIES + 1):
        resp = _get_client().chat.completions.create(model=model, messages=history)
        text = (resp.choices[0].message.content or "").strip()
        if text and not _FOREIGN.search(text):
            return text
    cleaned = _FOREIGN.sub("", text).strip()
    return cleaned or "Алло, я вас плохо слышу, повторите?"


def complete_json(messages: list[dict], model: str | None = None) -> dict:
    """Виклик з вимогою JSON (для судді/аналізатора). Retry на невалідний JSON."""
    model = model or LLM_MODEL
    last = ""
    for _ in range(_MAX_RETRIES + 1):
        resp = _get_client().chat.completions.create(
            model=model, messages=messages, response_format={"type": "json_object"},
        )
        last = resp.choices[0].message.content or ""
        try:
            return json.loads(last)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"LLM не повернув валідний JSON: {last[:200]}")
