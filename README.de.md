# Trainer für Immobilien-Kaltakquise (Telegram-Sprachbot)

**[English](README.md) · Deutsch · [Українська](README.uk.md)**

Ein sprachbasierter Telegram-Bot, der die **Rolle eines Immobilieneigentümers** spielt,
damit Callcenter-Mitarbeiter Kaltakquise-Telefonate üben können. Der Mitarbeiter ruft per
Sprachnachricht an; der Bot antwortet als zurückhaltender Eigentümer per Sprachnachricht — bringt
realistische Einwände vor, leistet Widerstand und stimmt (manchmal) einem Termin zu. Nach dem
Gespräch erstellt er einen **bewerteten Coaching-Bericht**.

> Als Probeaufgabe entwickelt. Dialog und Bot-Oberfläche sind auf Russisch (Sprache des
> Ziel-Callcenters); die Doku liegt auf Englisch, Ukrainisch und Deutsch vor.

## Funktionen

- **13 Einwand-Szenarien** (will nicht mit einer Agentur arbeiten, verkauft selbst, Provision
  zu hoch, schlechte Erfahrung, kein Vertrauen, „erst mit der Familie besprechen“ usw.).
- **4 Schwierigkeitsstufen** — von einem freundlichen Eigentümer, der nach einem Einwand
  nachgibt, bis zu einem kalten, abweisenden Eigentümer, der sich kaum einlässt. Der
  Schwierigkeitsverlauf ist **empirisch validiert** (hält auch gegen einen adaptiven
  LLM-„Manager“, nicht nur gegen ein festes Skript).
- **Sprache-zu-Sprache** über Telegram-Sprachnachrichten: Sprache → Text → Dialog → Sprache.
- **Bewerteter Bericht** nach jedem Gespräch: 7 Kriterien (0–100), gewichtete Gesamtnote (%),
  Kommentare je Kriterium, Stärken und konkrete Empfehlungen *mit Beispielformulierungen*.
- **Gesprächsspeicherung** (Transkripte, Audio, Berichte) + ein **STT-Prüftool**, um zu
  kontrollieren, was die Spracherkennung tatsächlich gehört hat.
- **Bleibt in der Rolle** — gehärtet gegen Jailbreak / „bist du ein Bot?“ / themenfremde
  Aufforderungen (mit 48 Angriffen getestet).

## Funktionsweise

```
Mitarbeiter (Telegram-Sprache) ─► STT (Groq Whisper API) ─► LLM-Dialog (gpt-4o-mini)
                                                            │  Persona = Szenario × Stufe
        Telegram-Sprache ◄── TTS (Silero → OGG/Opus) ◄──────┘
   bei /finish: vollständiges Transkript ─► LLM-Bewerter ─► bewerteter Bericht
```

Ablauf: `/start` → Szenario wählen → Stufe wählen → Bot sagt *„Алло?“* → per Sprache reden →
`/finish` → Bericht erhalten. Gesamte Antwortzeit: **~3–7 s**.

## Technologie-Stack

| Schicht | Wahl | Warum |
|---------|------|-------|
| Bot | `aiogram` (Python 3.12) | asynchrones Telegram-Framework |
| STT | **Groq Whisper API** (Cloud), lokales `faster-whisper` als Fallback | ~1 s und genauer; lokal auf schwacher CPU waren es ~10 s |
| Dialog- & Bewertungs-LLM | `openai/gpt-4o-mini` via **OpenRouter** | aus 6 Modellen nach Qualität × Kosten × Zuverlässigkeit gewählt (~$1 / 1000 Gespräche) |
| TTS | `Silero` (lokal) → `ffmpeg` zu OGG/Opus | kostenlos; für den Produktivbetrieb gegen OpenAI TTS / ElevenLabs austauschbar |
| Speicher | SQLite + lokale Audiodateien | Null-Setup für eine Demo |

Jeder externe Anbieter (STT / LLM / TTS) liegt hinter einem schlanken Modul — ein Wechsel ist
eine Änderung in einer Datei. Bewiesen durch zwei Wechsel: das LLM von lokalem Ollama zu
OpenRouter und die Spracherkennung von lokalem faster-whisper zu Groq.

## Einrichtung

**Voraussetzungen:** Python 3.12, `ffmpeg`, ein Telegram-Bot-Token ([@BotFather](https://t.me/BotFather))
und ein API-Schlüssel von [OpenRouter](https://openrouter.ai/keys). Optional ein API-Schlüssel
von [Groq](https://console.groq.com/keys) für schnelle Cloud-Spracherkennung — ohne ihn läuft
die Spracherkennung lokal über `faster-whisper`.

```bash
# 1. ffmpeg (macOS)
brew install ffmpeg

# 2. virtuelle Umgebung + Abhängigkeiten
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. konfigurieren
cp .env.example .env
#   dann BOT_TOKEN und OPENROUTER_API_KEY eintragen (GROQ_API_KEY optional)

# 4. starten
.venv/bin/python -m bot.main
```

Beim ersten Start werden das Silero-TTS-Modell und — ohne Groq-Schlüssel — auch das lokale
Whisper-Modell geladen (danach zwischengespeichert).

## Deployment

Der Bot läuft als einzelner Long-Polling-Prozess und lässt sich auf einem kleinen VPS per
`systemd` dauerhaft betreiben — ein eingeschalteter Entwicklerrechner ist nicht nötig. Weil die
Spracherkennung in die Cloud (Groq) ausgelagert ist, reicht ein kleiner Server;
nennenswerten Arbeitsspeicher braucht nur die lokale Sprachsynthese (Silero).

## Tests

```bash
.venv/bin/python -m pytest tests/
```

17 Unit-Tests für Berichtslogik, Speicherung und Persona-/Prompt-Aufbau (ohne Netzwerk).

## Projektstruktur

```
bot/        Produktcode (Telegram, STT, LLM, TTS, Persona, Analyzer, Speicher)
tests/      Pytest-Unit-Tests
research/    Explorationsskripte zur Validierung von Modellen, Stufen, Bewerter und Guardrail
tools/       stt_review.py — erzeugt eine HTML-Ansicht „Audio ↔ Transkription“
docs/        Aufgabenstellung + Architektur & Entscheidungen
```

## Bekannte Einschränkungen

- **Roboterhafte Stimme** — Silero ist ein kostenloser Platzhalter; für den Produktivbetrieb
  empfehlen wir OpenAI TTS (ein Modulwechsel). Die Stimme ist der größte Kostenhebel — Details
  in der Architektur-Doku.
- **Bewertungen sind konsistent, aber nicht von Experten kalibriert** — nützlich als
  Trainings-Feedback, keine zertifizierte Bewertung.
- **Ein Prozess** — gleichzeitige Nutzer werden serialisiert; im Produktivbetrieb bräuchte es
  einen Worker-Pool und eine Warteschlange.
- **Aufnahmen werden unbegrenzt aufbewahrt** (bewusst, zur Archivierung) — im Produktivbetrieb
  braucht es eine Einwilligung und eine Aufbewahrungsrichtlinie (DSGVO).

Siehe [`docs/02-architecture.de.md`](docs/02-architecture.de.md) für das vollständige Design,
Entscheidungen, Kosten, Skalierung und Validierungsergebnisse.
