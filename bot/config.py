"""Конфіг: читає налаштування з .env в одному місці.

Чому окремий файл: усі налаштування й секрети — в одному місці, решта коду
бере їх звідси, а не розкидані по проєкту магічні значення.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # підтягує змінні з .env

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")

# OpenRouter (OpenAI-сумісний API). Ключ — у .env, не комітимо.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")

# STT-провайдер: якщо заданий GROQ_API_KEY — розпізнаємо через Groq Whisper API
# (хмара, ~1-2с, точніше за локальну small). Інакше — локальний faster-whisper.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
# BOT_LANG, а не LANG — щоб не конфліктувати з системною змінною локалі LANG
BOT_LANG = os.getenv("BOT_LANG", "ru")

# Голос TTS (Silero). Порожньо = дефолт під мову. Для ru: aidar|eugene|baya|kseniya|xenia
TTS_SPEAKER = os.getenv("TTS_SPEAKER", "")

# Куди складаємо тимчасові аудіофайли розмов
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", "recordings")

# Файл бази даних (історія розмов + звіти)
DB_PATH = os.getenv("DB_PATH", "data/conversations.sqlite")

# Через скільки хвилин неактивності сесія вважається застарілою
SESSION_TIMEOUT_MIN = int(os.getenv("SESSION_TIMEOUT_MIN", "30"))


def require_bot_token() -> str:
    """Повертає токен; кидає ясну помилку, якщо він порожній.

    Перевірку винесено у функцію (а не на імпорт), щоб STT/TTS/LLM можна було
    імпортувати й тестувати без токена — їм Telegram не потрібен.
    """
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN порожній. Скопіюй .env.example у .env і встав токен від @BotFather."
        )
    return BOT_TOKEN
