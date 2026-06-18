"""STT: голос -> текст.

Два провайдери за ОДНІЄЮ абстракцією transcribe() — решта бота не знає, що всередині:
- Groq Whisper API (хмара, ~1-2с, точніше) — якщо заданий GROQ_API_KEY;
- faster-whisper (локально, ~10с на слабкому CPU) — фолбек, коли ключа нема.

Чому так: на CPU локальний Whisper повільний (вузьке місце конвеєра). Groq ганяє
whisper-large на своєму залізі — і швидше, і точніше. Вибір зроблено перемикачем
у config, без if-ів по коду бота. Якщо завтра інший провайдер — правимо тільки тут.
"""
import threading

from bot.config import WHISPER_MODEL, BOT_LANG, GROQ_API_KEY, GROQ_STT_MODEL

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


if GROQ_API_KEY:
    # --- Хмарний шлях: Groq (OpenAI-сумісний audio API) ---
    from openai import OpenAI

    _client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)

    def transcribe(audio_path: str) -> str:
        """Розпізнає аудіофайл через Groq і повертає текст.

        Замок не потрібен: мережеві виклики природно паралельні (кілька тестерів
        одночасно не впираються в одну локальну модель).
        """
        with open(audio_path, "rb") as f:
            resp = _client.audio.transcriptions.create(
                model=GROQ_STT_MODEL, file=f, language=BOT_LANG,
            )
        return (resp.text or "").strip()

else:
    # --- Локальний фолбек: faster-whisper ---
    from faster_whisper import WhisperModel

    # Модель вантажиться один раз при старті (compute_type int8 — швидше на CPU).
    _model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

    # Замок: одна модель — один потік за раз (кілька юзерів одночасно не зіткнуться).
    _lock = threading.Lock()

    def transcribe(audio_path: str) -> str:
        """Розпізнає аудіофайл локально і повертає текст."""
        with _lock:
            # генератор споживаємо всередині замка, поки модель «зайнята»
            segments, _ = _model.transcribe(audio_path, language=BOT_LANG)
            return " ".join(seg.text for seg in segments).strip()
