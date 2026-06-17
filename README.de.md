# Trainer für Immobilien-Kaltakquise (Telegram-Sprachbot)

**[English](README.md) · Deutsch · [Українська](README.uk.md)**

Ein sprachbasierter Telegram-Bot, der die **Rolle eines Immobilieneigentümers** spielt,
damit Callcenter-Mitarbeiter Kaltakquise-Telefonate üben können. Der Mitarbeiter ruft per
Sprachnachricht an; der Bot antwortet als zurückhaltender Eigentümer per Sprachnachricht — bringt
realistische Einwände, leistet Widerstand und stimmt (manchmal) einem Termin zu. Nach dem
Gespräch erstellt er einen **bewerteten Coaching-Bericht**.

> Als Probeaufgabe entwickelt. Der Dialog läuft auf Russisch (Sprache des Ziel-Callcenters).
> Die Bot-Oberfläche ist auf Ukrainisch; die Doku liegt auf Englisch, Ukrainisch und Deutsch vor.

## Funktionen

- **13 Einwand-Szenarien** (will nicht mit einer Agentur arbeiten, verkauft selbst, Provision
  zu hoch, schlechte Erfahrung, kein Vertrauen, „erst mit der Familie besprechen" usw.).
- **4 Schwierigkeitsstufen** — von einem freundlichen Eigentümer, der nach einem Einwand
  nachgibt, bis zu einem kalten, abweisenden Eigentümer, der sich kaum einlässt. Der Schwierigkeits-
  verlauf ist **empirisch validiert** (hält auch gegen einen adaptiven LLM-„Manager", nicht
  nur gegen ein festes Skript).
- **Sprache-zu-Sprache** über Telegram-Sprachnachrichten: Sprache → Text → Dialog → Sprache.
- **Bewerteter Bericht** nach jedem Gespräch: 7 Kriterien (0–100), gewichtete Gesamtnote (%),
  Kommentare je Kriterium, Stärken und konkrete Empfehlungen *mit Beispielformulierungen*.
- **Gesprächsspeicherung** (Transkripte, Audio, Berichte) + ein **STT-Prüftool**, um zu
  kontrollieren, was die Spracherkennung tatsächlich gehört hat.
- **Bleibt in der Rolle** — gehärtet gegen Jailbreak / „bist du ein Bot?" / themenfremde
  Aufforderungen (mit 48 Angriffen getestet).

## Funktionsweise

```
Mitarbeiter (Telegram-Sprache) ─► STT (faster-whisper) ─► LLM-Dialog (gpt-4o-mini)
                                                              │  Persona = Szenario × Stufe
        Telegram-Sprache ◄── TTS (Silero → OGG/Opus) ◄───────┘
   bei /finish: vollständiges Transkript ─► LLM-Bewerter ─► bewerteter Bericht
```

Ablauf: `/start` → Szenario wählen → Stufe wählen → Bot sagt *„Алло?"* → per Sprache reden →
`/finish` → Bericht erhalten.

## Technologie-Stack

| Schicht | Wahl | Warum |
|---------|------|-------|
| Bot | `aiogram` (Python 3.12) | asynchrones Telegram-Framework |
| STT | `faster-whisper` (lokal) | schnell auf CPU, keine Kosten pro Anruf |
| Dialog- & Bewertungs-LLM | `openai/gpt-4o-mini` via **OpenRouter** | aus 6 Modellen nach Qualität × Kosten × Zuverlässigkeit gewählt (~$1 / 1000 Gespräche) |
| TTS | `Silero` (lokal) → `ffmpeg` zu OGG/Opus | kostenlos; austauschbar gegen ElevenLabs/OpenAI TTS |
| Speicher | SQLite + lokale Audiodateien | Null-Setup für eine Demo |

Jeder externe Anbieter (STT / LLM / TTS) liegt hinter einem schlanken Modul — ein Wechsel ist
eine Änderung in einer Datei. Bewiesen während der Entwicklung durch den Wechsel des LLM von
lokalem Ollama zu OpenRouter.

## Einrichtung

**Voraussetzungen:** Python 3.12, `ffmpeg`, ein Telegram-Bot-Token ([@BotFather](https://t.me/BotFather))
und ein [OpenRouter](https://openrouter.ai/keys) API-Schlüssel.

```bash
# 1. ffmpeg (macOS)
brew install ffmpeg

# 2. virtuelle Umgebung + Abhängigkeiten
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. konfigurieren
cp .env.example .env
#   dann BOT_TOKEN und OPENROUTER_API_KEY eintragen

# 4. starten
.venv/bin/python -m bot.main
```

Beim ersten Start werden die Whisper- und Silero-Modelle geladen (danach zwischengespeichert).

## Tests

```bash
.venv/bin/python -m pytest tests/
```

17 Unit-Tests für Berichtslogik, Speicherung und Persona-/Prompt-Aufbau (ohne Netzwerk).

## Projektstruktur

```
bot/        Produktcode (Telegram, STT, LLM, TTS, Persona, Analyzer, Speicher)
tests/      Pytest-Unit-Tests
research/    Explorationsskripte zur Validierung von Modellen, Stufen, Bewerter, Guardrail
tools/       stt_review.py — erzeugt eine HTML-Ansicht „Audio ↔ Transkription"
docs/        Aufgabenstellung + Architektur & Entscheidungen
```

## Bekannte Einschränkungen

- **Roboterhafte Stimme** — Silero ist ein kostenloser Platzhalter; ElevenLabs/OpenAI TTS ist
  ein Modulwechsel.
- **Bewertungen sind konsistent, aber nicht experten-kalibriert** — nützlich als Trainings-
  Feedback, keine zertifizierte Bewertung.
- **Ein Prozess** — gleichzeitige Nutzer werden serialisiert; im Produktivbetrieb bräuchte es
  einen Worker-Pool + Warteschlange.
- **Aufnahmen werden unbegrenzt aufbewahrt** (bewusst, zur Archivierung) — im Produktivbetrieb
  braucht es eine Aufbewahrungsrichtlinie.

Siehe [`docs/02-architecture.de.md`](docs/02-architecture.de.md) für das vollständige Design,
Entscheidungen, Kosten, Skalierung und Validierungsergebnisse.
