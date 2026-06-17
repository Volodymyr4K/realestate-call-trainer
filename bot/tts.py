"""TTS: текст -> голос через Silero, потім конвертація в OGG/OPUS для Telegram.

Чому конвертація: Silero видає WAV, а Telegram показує голосове «кружком» тільки
якщо слати OGG/OPUS через sendVoice (інакше прилетить файл). ffmpeg уже стоїть.
"""
import os
import subprocess
import threading
import torch
from bot.config import BOT_LANG, RECORDINGS_DIR, TTS_SPEAKER

# Silero: мова -> (пакет моделі, голос за замовчуванням, частота)
_VOICES = {
    "ru": ("v4_ru", "aidar"),
    "uk": ("v4_ua", "mykyta"),
}
_SAMPLE_RATE = 48000

_lang = BOT_LANG if BOT_LANG in _VOICES else "ru"
_package, _default_speaker = _VOICES[_lang]
# Голос можна перевизначити через .env (TTS_SPEAKER); порожньо -> дефолт під мову
_speaker = TTS_SPEAKER or _default_speaker
_silero_lang = "ua" if _lang == "uk" else _lang

# Модель вантажиться один раз при старті.
_model, _ = torch.hub.load(
    repo_or_dir="snakers4/silero-models",
    model="silero_tts",
    language=_silero_lang,
    speaker=_package,
    trust_repo=True,  # без інтерактивного запиту довіри (інакше падає у скрипті)
)
_model.to("cpu")

# Якщо в .env вказали неіснуючий голос — відкат на дефолт (а не падіння).
if _speaker not in _model.speakers:
    print(f"[tts] голос '{_speaker}' невідомий, відкат на '{_default_speaker}'. "
          f"Доступні: {_model.speakers}")
    _speaker = _default_speaker

# Замок: одна модель — один потік за раз (кілька юзерів одночасно не зіткнуться).
_lock = threading.Lock()


def synthesize(text: str, out_basename: str) -> str:
    """Озвучує текст і повертає шлях до .ogg (готового для sendVoice)."""
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    wav_path = os.path.join(RECORDINGS_DIR, f"{out_basename}.wav")
    ogg_path = os.path.join(RECORDINGS_DIR, f"{out_basename}.ogg")

    with _lock:
        _model.save_wav(text=text, speaker=_speaker, sample_rate=_SAMPLE_RATE, audio_path=wav_path)

    # WAV -> OGG/OPUS (формат голосових Telegram)
    subprocess.run(
        ["ffmpeg", "-y", "-i", wav_path, "-c:a", "libopus", "-b:a", "32k", ogg_path],
        check=True, capture_output=True,
    )
    os.remove(wav_path)  # проміжний WAV більше не потрібен
    return ogg_path
