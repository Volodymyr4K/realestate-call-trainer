"""STT: голос -> текст через faster-whisper.

Один шар = одна відповідальність. Якщо завтра міняємо на хмарний Whisper API —
правимо тільки цей файл, решта бота не знає, що всередині.
"""
import threading

from faster_whisper import WhisperModel
from bot.config import WHISPER_MODEL, BOT_LANG

# Модель вантажиться один раз при старті (compute_type int8 — швидше на CPU).
_model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

# Замок: одна модель — один потік за раз (кілька юзерів одночасно не зіткнуться).
_lock = threading.Lock()


def transcribe(audio_path: str) -> str:
    """Розпізнає аудіофайл і повертає текст."""
    with _lock:
        # генератор споживаємо всередині замка, поки модель «зайнята»
        segments, _ = _model.transcribe(audio_path, language=BOT_LANG)
        return " ".join(seg.text for seg in segments).strip()
