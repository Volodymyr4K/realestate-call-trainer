# Architecture and Recorded Decisions

**[Українська](02-architecture.md) · [Deutsch](02-architecture.de.md) · English**

> This is **our** document: how we decided to build the product, why that way, and where the risks are.
> Problem statement (paraphrased) — [01-problem-statement.md](01-problem-statement.md).
> This document is living. Version as of 2026-06-17 (after the 2nd critical review + hardware check).

---

## 1. What this product is (in one sentence)

A Telegram bot that plays the role of a property owner via voice, conducts a training
dialogue with the agent (objections / doubts / refusals), records the conversation, and
afterward delivers a report with a skill assessment.

---

## 2. What exactly we are delivering (Deliverables) — DO NOT forget

The client's spec **explicitly requests documentation**, not just a bot. Therefore the output = TWO things:

1. **A proposal document for the owner** (Russian/Ukrainian, plain language) covering his 6 points:
   which AI models, which services/integrations, architecture diagram, estimated operating cost,
   scaling, integration with the existing system. ← **mandatory — he named this explicitly**
2. **A working demo-bot** — a powerful bonus that proves capability.

⚠️ This file (`02-architecture.md`) is the technical document, for US. The clean version for the
owner is assembled separately (phases 3–4) — do not confuse them.

---

## 3. Two questions for the owner — ✅ CONFIRMED

1. **Voice format:** exchange of voice messages (async) — **confirmed by the owner**
   ("let it work like voice messages"). Realtime is not needed.
2. **Bot language:** **Russian** — confirmed by the owner. `BOT_LANG=ru`.

Both of our working assumptions matched the owner's answers — nothing needed to be redone.
The rest of the technical decisions were made by us (this is a test assignment).

---

## 4. Key technical constraint

**A Telegram bot cannot make a live phone call.** The Bot API only allows exchanging
voice *messages*. Live calls are officially unavailable to Telegram bots.

- **A. Voice message exchange** — simple, cheap, fast. No interruptions or real-time pressure.
- **B. Realtime call** — Telegram Mini App + WebRTC or a telephony layer (LiveKit/Twilio
  + OpenAI Realtime API). More expensive and significantly longer to build.

**MVP decision:** build **A**, keep the architecture modular for a future B.

⚠️ **Honest limitation of A:** the skill of working under real-time pressure (reaction speed,
not "freezing") is **not trained** in variant A — the agent can think as long as they want
and re-record. This is the realism ceiling of A; we state this directly to the owner.

---

## 5. Call logic and "win condition" (the simulator's core)

**Who goes first:** a cold call — the **agent** initiates it, the bot-owner "picks up" with
a brief "Hello?". The first meaningful move belongs to the employee (the "establishing contact"
criterion).

**"Win condition" — implemented via the PROMPT, not a state machine.** There is NO separate
"trust level" variable with a threshold in the code — that would be premature complexity.
The persona decides when to yield, guided by the difficulty-level instruction (the axis being
how many objections must be handled before agreement):
- level 1 — yields after ~1 light doubt (easy);
- level 2 — only after 2–3 handled objections;
- level 3 (skeptic, distrust) — rarely, only with confident handling;
- level 4 (cold, dismissive) — almost never.

Behavior **verified empirically** (QA on gpt-4o-mini, 104 conversations): agreement drops
L1→L4 (88/12/0/0%), resistance increases (4.6/6.2/6.7/7.9 on a 1–10 scale). If more precise
control is ever needed — we will move "trust" into code as a future improvement.

**Persona guard (guardrail) — verified via jailbreak (48 attacks).** The bot ALWAYS stays
in character as the owner: does not admit it is AI, does not comply with "forget your role /
you are ChatGPT", does not answer meta-questions, **and does not perform unrelated tasks**
(equations/code — it brushes them off like a real person). It does not hang up at the first
"no" — it resists, but keeps the conversation going.

**Session:** the state of each conversation is isolated per `user_id` (multiple agents
simultaneously do not mix). Cycle: `/start` (level selection) → dialogue → `/finish`.
If `/finish` is forgotten — the session expires after `SESSION_TIMEOUT_MIN` minutes of
inactivity and is reset on the next interaction (lazy expiry, no background tasks; default
30 min). Implemented in `get_active_session()`.

---

## 6. Solution architecture (diagram)

```
Agent (Telegram)
        │  voice message (voice, ogg/opus)
        ▼
  ┌─────────────────────────┐
  │  Telegram Bot (aiogram) │   ← entry, orchestration, session state
  └─────────────────────────┘
        │ audio → ffmpeg decodes
        ▼
  ┌─────────────────────────┐
  │  STT  (faster-whisper)  │   voice → text
  └─────────────────────────┘
        │ agent's text
        ▼
  ┌─────────────────────────────────────────────┐
  │  Dialogue engine (LLM, provider SWAPPABLE)   │
  │   • persona + scenario (1 of 13)              │
  │   • difficulty level (1–4) controls yielding  │
  │   • dialogue memory (conversation history)    │
  └─────────────────────────────────────────────┘
        │ owner's text response
        ▼
  ┌─────────────────────────┐
  │  TTS (Silero) → WAV     │
  │  → ffmpeg → OGG/OPUS    │   so it arrives as a voice "circle"
  └─────────────────────────┘
        │ sendVoice
        ▼
  Telegram (voice response)

   ── during the conversation: transcript + audio → SQLite + files ──
   ── after /finish: Analyzer (LLM-judge) → report on 8 criteria ──
```

---

## 7. Technology stack (final MVP)

| Layer | MVP / demo (our choice) | Production / quality |
|-------|-------------------------|----------------------|
| Bot | `aiogram` (Python 3.12) | same |
| STT | `faster-whisper`, `small`/`medium` (local) | Whisper API / Deepgram |
| Dialogue LLM | **`openai/gpt-4o-mini` via OpenRouter** — selected by comparing 6 models (quality×cost×reliability, $1/1000 conversations). Provider SWAPPABLE | any model on OpenRouter (Claude/Gemini/…) |
| Judge (scoring) | same gpt-4o-mini (judges the HUMAN, not itself) | stronger model if needed |
| TTS | `Silero` (free, CPU) → conversion to OGG/OPUS via ffmpeg | ElevenLabs / OpenAI TTS |
| Storage | **SQLite** + local audio files + STT log (`stt_log`) | Postgres + S3/MinIO |
| Realtime (opt.) | — | OpenAI Realtime API + LiveKit/WebRTC |

**Path:** started locally (Ollama, qwen/llama — zero cost), but local 8B models contradicted
themselves on hard levels → switched to **OpenRouter / gpt-4o-mini**. The swap cost **one file**
(`bot/llm.py`) — proof that the provider layer is genuinely swappable.
**Principle:** STT / LLM / TTS — behind abstractions; the provider is replaced in one place,
no rewriting needed.

---

## 8. Difficulty levels

Not different models/bots — parameters of a single persona that control **yielding** (section 5):

| Parameter | Level 1 | Level 2 | Level 3 | Level 4 |
|-----------|---------|---------|---------|---------|
| Number of objections | minimum | several | many | very many |
| Meeting-agreement threshold | low | moderate | high | very high |
| Initial trust | high | moderate | low | nearly none |
| Behavior | friendly | cautious | skeptical | active resistance |

13 scenarios × 4 levels = combinations over shared code, not 52 separate programs.

---

## 9. Analytics and scoring (how we calculate %)

**LLM-as-judge:** a separate call receives the transcript + **rubric** and returns a
structured report. 8 criteria from the spec:
1. Opening quality 2. Needs discovery 3. Question quality 4. Objection handling
5. Trust level 6. Meeting attempt 7. Negotiation skills
8. Summary in % + strengths + recommendations.

**Final %:** each criterion 0–100, combined as a **weighted average** (weights in config;
objections and needs weigh more).

**Honest limitations of the scoring:**
- Without a strict rubric, scores fluctuate → output format is fixed/structured.
- **STT accuracy → fairness:** a recognition error = skewed score.
- **Local judge is unreliable** (weak RU). Scores in the demo are "plausible", not
  calibrated (no gold-standard examples). Hence the candidate to move the judge to an API.
- **The judge sees text only** — intonation/pauses/confidence are lost, yet "trust" and
  "negotiation" are partly about tone. Text-based scoring is lossy.

---

## 10. Storage

Transcript (text + speaker + timestamp) → SQLite. Audio → local files (S3 in production).
Report → SQLite.
⚠️ On `git init`: `.gitignore` for `.env`, audio files, and `*.sqlite` (do not commit tokens or data).
⚠️ Recording employees' voices — in production, consent and a storage policy are required
(fine for a demo, but mention it in the owner's document to look professional).

---

## 11. Environment prerequisites (verified 2026-06-17, M1 Pro, 16 GB) ✅

| What | Status |
|------|--------|
| Python | **3.12.13** ✅ (was 3.9.6) |
| ffmpeg | **8.1.1** ✅ (installed) |
| STT/TTS | local (`faster-whisper`, `Silero`) — loaded at bot startup |
| LLM | **OpenRouter `gpt-4o-mini`** (key `OPENROUTER_API_KEY` in `.env`) — not local, no machine load |

Setup: `cp .env.example .env`, fill in `BOT_TOKEN` (from @BotFather) and
`OPENROUTER_API_KEY` (from openrouter.ai). Launch: `.venv/bin/python -m bot.main`.

---

## 12. Estimated cost (≈1 conversation, ~5 min)

| Layer | Cost |
|-------|------|
| LLM (gpt-4o-mini: dialogue + scoring report) | **~$1 per 1000 conversations** (measured on live tokens) |
| STT (faster-whisper, local) | ~0 |
| TTS (Silero, local) | ~0 |

So the demo costs **cents**. The main expense at scale — LLM (can go cheaper with mistral,
gemini-flash). If voice is upgraded to ElevenLabs/OpenAI TTS — voiceover cost is added
(still pennies per conversation).

---

## 13. Scaling

Each conversation is independent → horizontal scaling (more workers). Bottleneck — latency/cost
of STT/TTS/LLM. Local stack cannot handle many concurrent users (single machine) → for
production: API + queue (Redis/Celery).

---

## 14. Key risks (honestly)

1. **"Maximum realism" × "local/free"** — these conflict. Smaller local models struggle to
   hold character/RU. Insurance — swappable provider.
2. **Pipeline latency** — STT(local ~1–2 s) + LLM(OpenRouter ~2–5 s) + TTS(local ~1–2 s)
   ≈ 5–10 s/response. Acceptable for voice message exchange.
3. **Dialogue realism — tuning, not code.** Not "100% done".
4. **Scoring** depends on rubric, STT accuracy, and judge strength; from text — lossy.
5. **Realtime** (if they want it) — complexity jump measured in weeks.
6. **Ceiling of variant A** — real-time pressure/reaction speed are not trained (async).

---

## 15. Phase plan

| Phase | What | Status / estimate |
|-------|------|-------------------|
| 0 | Documentation + rules + environment verification and setup | ✅ done |
| 1 | Bot skeleton: voice→STT→LLM→TTS→voice, 1 scenario, /start–/finish cycle, difficulty levels | 3–5 days |
| 2 | Multiple scenarios + levels + persona guardrail | +a few days |
| 3 | Storage (SQLite) + analysis report (judge + rubric) | +2–3 days |
| 4 | Realism polish + **proposal document for the owner** (deliverable #1) | iterative |
| 5 | (Opt.) Realtime via Mini App / WebRTC | weeks |

**Test assignment goal:** solid demo of phases 1–3 (1–2 scenarios, 2 levels, full
voice→dialogue→report cycle) + proposal document for the owner.

---

## 16. Empirically verified (on gpt-4o-mini)

- **Levels work** — difficulty gradient is robust even against an adaptive LLM agent
  (resistance increases L1→L4: 5.5/6.5/7.7/8.8). Not an artifact of a single script.
- **13 scenarios** — each surfaces its own objection (52/52), 0 contradictions.
- **Guardrail** — withstood 48 jailbreak attacks (including "you're a bot", reveal-prompt,
  unrelated tasks); after hardening: 0 breaks.
- **Model selection** — compared 6 models; gpt-4o-mini = best balance of quality×cost×reliability.
- **STT observability** — `stt_log` log (audio ↔ what Whisper heard, including failures)
  + HTML review (`tools/stt_review.py`) for checking recognition accuracy.
- **Tests** — `pytest tests/` (17 logic tests). Validation research — in `research/`.

## 17. Known limitations / future work (honestly)

- **Voice** — Silero sounds robotic; switching to ElevenLabs/OpenAI TTS = replacing one module.
- **Score calibration** — judges are self-consistent but not benchmarked against a real trainer.
- **Long voice messages (>20 MB)** — Telegram won't deliver them; handled safely (try/except),
  does not occur in a normal training reply.
- **`recordings/` without auto-cleanup** — intentional (archive of recordings). For production:
  N-day retention / S3 + consent for recording employee conversations.
- **Single process** — concurrent users queue up (locks). For production — worker pool.
