# Real Estate Cold-Call Trainer (Telegram voice bot)

**English · [Deutsch](README.de.md) · [Українська](README.uk.md)**

A voice-based Telegram bot that **role-plays a property owner** so call-center agents can
practice real-estate cold calls. The agent calls in with voice messages; the bot answers
in voice as a reluctant owner — raising realistic objections, resisting, and (sometimes)
agreeing to a meeting. After the call it produces a **scored coaching report**.

> Built as a take-home project. Dialogue is in Russian (the target call-center's language);
> the bot UI is in Ukrainian; docs are available in English, Ukrainian, and German.

## What it does

- **13 objection scenarios** (won't work with an agency, selling solo, commission too high,
  bad past experience, no trust, "let me consult my family", etc.).
- **4 difficulty levels** — from a warm owner who caves after one objection to a cold,
  dismissive one who barely engages. The difficulty gradient is **empirically validated**
  (holds even against an adaptive LLM "manager", not just a fixed script).
- **Voice-to-voice** over Telegram voice messages: speech → text → dialogue → speech.
- **Scored report** after each call: 7 criteria (0–100), weighted overall %, per-criterion
  comments, strengths, and concrete recommendations *with example phrasing*.
- **Conversation storage** (transcripts, audio, reports) + an **STT review tool** to verify
  what the recognizer actually heard.
- **Stays in character** — hardened against jailbreak / "are you a bot?" / off-topic prompts
  (tested with 48 adversarial attacks).

## How it works

```
Agent (Telegram voice) ──► STT (faster-whisper) ──► LLM dialogue (gpt-4o-mini)
                                                          │  persona = scenario × level
       Telegram voice ◄── TTS (Silero → OGG/Opus) ◄──────┘
   on /finish: full transcript ──► LLM judge ──► scored report
```

Flow: `/start` → pick scenario → pick level → bot says *"Алло?"* → talk via voice →
`/finish` → get the report.

## Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| Bot | `aiogram` (Python 3.12) | async Telegram framework |
| STT | `faster-whisper` (local) | fast on CPU, no per-call cost |
| Dialogue + scoring LLM | `openai/gpt-4o-mini` via **OpenRouter** | chosen by comparing 6 models on quality × cost × reliability (~$1 / 1000 conversations) |
| TTS | `Silero` (local) → `ffmpeg` to OGG/Opus | free; swappable for ElevenLabs/OpenAI TTS |
| Storage | SQLite + local audio files | zero-setup for a demo |

Every external provider (STT / LLM / TTS) sits behind a thin module, so swapping it is a
one-file change — proven during development by moving the LLM from local Ollama to OpenRouter.

## Setup

**Prerequisites:** Python 3.12, `ffmpeg`, a Telegram bot token ([@BotFather](https://t.me/BotFather)),
and an [OpenRouter](https://openrouter.ai/keys) API key.

```bash
# 1. ffmpeg (macOS)
brew install ffmpeg

# 2. virtualenv + deps
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. configure
cp .env.example .env
#   then fill in BOT_TOKEN and OPENROUTER_API_KEY

# 4. run
.venv/bin/python -m bot.main
```

First run downloads the Whisper and Silero models (cached afterwards).

## Tests

```bash
.venv/bin/python -m pytest tests/
```

17 unit tests covering the report logic, storage, and persona/prompt building (no network).

## Project structure

```
bot/        product code (telegram, stt, llm, tts, persona, analyzer, storage)
tests/      pytest unit tests
research/    exploratory scripts used to validate models, levels, judge, guardrail
tools/       stt_review.py — generates an HTML "audio ↔ transcription" review
docs/        problem statement + architecture & decisions
```

## Known limitations

- **Robotic voice** — Silero is a free placeholder; ElevenLabs/OpenAI TTS is a one-module swap.
- **Scores are consistent but not expert-calibrated** — useful for training feedback, not a
  certified assessment.
- **Single process** — concurrent users are serialized; production would use a worker pool + queue.
- **Recordings are kept indefinitely** (by design, for archival) — production needs a retention policy.

See [`docs/02-architecture.en.md`](docs/02-architecture.en.md) for the full design, decisions,
cost, scaling, and validation results.
