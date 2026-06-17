# Architektur und festgelegte Entscheidungen

**[Українська](02-architecture.md) · Deutsch · [English](02-architecture.en.md)**

> Dies ist **unser** Dokument: wie wir das Produkt zu bauen beschlossen haben, warum genau so,
> wo die Risiken liegen.
> Aufgabenstellung (paraphrasiert) — [01-problem-statement.md](01-problem-statement.md).
> Das Dokument ist lebendig. Version vom 2026-06-17 (nach dem 2. kritischen Review + Hardware-Prüfung).

---

## 1. Was ist dieses Produkt (in einem Satz)

Ein Telegram-Bot, der per Stimme die Rolle eines Immobilieneigentümers spielt, mit dem Mitarbeiter
einen Trainingsdialog führt (Einwände / Zweifel / Absagen), das Gespräch aufzeichnet und danach
einen Bericht mit Kompetenz-Bewertung liefert.

---

## 2. Was wir genau abliefern (Deliverables) — NICHT vergessen

Der Auftraggeber fordert im Lastenheft **ausdrücklich Dokumentation**, nicht nur den Bot. Daher: ZWEI Ergebnisse:

1. **Vorschlagsdokument für den Eigentümer** (Russisch/Ukrainisch, in einfacher Sprache) zu seinen 6 Punkten:
   welche AI-Modelle, welche Dienste/Integrationen, Architekturschema, ungefähre Betriebskosten,
   Skalierung, Integration ins bestehende System. ← **Pflicht, er hat das explizit genannt**
2. **Funktionierender Demo-Bot** — starkes Bonus, das die Leistungsfähigkeit beweist.

⚠️ Dieses Dokument (`02-architecture.md`) ist technisch, für UNS. Die Reinversion für den Eigentümer
wird separat erstellt (Phase 3–4), nicht verwechseln.

---

## 3. Zwei Fragen an den Eigentümer — ✅ BESTÄTIGT

1. **Sprachformat:** Austausch per Sprachnachrichten (async) — **vom Eigentümer bestätigt**
   («soll wie Sprachnachrichten sein»). Echtzeit nicht nötig.
2. **Bot-Sprache:** **Russisch** — vom Eigentümer bestätigt. `BOT_LANG=ru`.

Beide Arbeitsannahmen stimmten mit der Antwort überein — es musste nichts überarbeitet werden.
Die übrigen technischen Entscheidungen haben wir selbst getroffen (das ist eine Testaufgabe).

---

## 4. Zentrale technische Einschränkung

**Ein Telegram-Bot kann keine Live-Telefonanrufe führen.** Die Bot-API erlaubt nur den Austausch
von Sprach*nachrichten*. Live-Anrufe sind für Telegram-Bots offiziell nicht verfügbar.

- **A. Austausch per Sprachnachrichten** — einfach, günstig, schnell. Ohne Unterbrechungen und Echtzeit-Druck.
- **B. Echtzeit-Anruf** — Telegram Mini App + WebRTC oder Telefonschicht (LiveKit/Twilio
  + OpenAI Realtime API). Teurer und deutlich aufwendiger.

**MVP-Entscheidung:** wir bauen **A**, die Architektur bleibt modular für zukünftiges B.

⚠️ **Ehrliche Einschränkung von A:** die Fähigkeit, unter Echtzeit-Druck zu arbeiten (Reaktionsgeschwindigkeit,
kein «Einfrieren»), wird in Variante A **nicht trainiert** — der Mitarbeiter kann so lange wie nötig
nachdenken und neu aufnehmen. Das ist die Realismus-Obergrenze von A; wir teilen das dem Eigentümer offen mit.

---

## 5. Gesprächslogik und «Erfolgsbedingung» (Kern des Simulators)

**Wer beginnt:** Kaltanruf — der **Mitarbeiter** initiiert, der Bot-Eigentümer «nimmt ab»
mit einem kurzen «Hallo?». Der erste inhaltliche Zug liegt beim Mitarbeiter (Kriterium «Kontaktaufnahme»).

**«Erfolgsbedingung» — Umsetzung per PROMPT, nicht Zustandsmaschine.** Im Code gibt es KEINE separate
Variable «Vertrauenslevel» mit Schwellenwert — das wäre verfrühte Komplexität. Die Persona entscheidet
selbst, wann sie nachgibt, gesteuert durch die Anweisung des Schwierigkeitsgrads (Achse — wie viele
Einwände bis zur Zustimmung bearbeitet werden müssen):
- Grad 1 — gibt nach ~1 leichtem Zweifel nach (einfach);
- Grad 2 — erst nach 2–3 bearbeiteten Einwänden;
- Grad 3 (Skeptiker, Misstrauen) — selten, nur bei sicherer Gesprächsführung;
- Grad 4 (kalt, abweisend) — fast nie.

Das Verhalten wurde **empirisch geprüft** (QA auf gpt-4o-mini, 104 Gespräche): Zustimmung sinkt
L1→L4 (88/12/0/0 %), Widerstand steigt (4,6/6,2/6,7/7,9 auf Skala 1–10). Falls später eine präzisere
Steuerung nötig ist — extrahieren wir «Vertrauen» als zukünftige Verbesserung in den Code.

**Persona-Schutz (guardrail) — mit Jailbreak geprüft (48 Angriffe).** Der Bot bleibt IMMER
Eigentümer: gesteht nicht, dass er eine KI ist, führt kein «vergiss deine Rolle / du bist ChatGPT» aus,
beantwortet keine Meta-Fragen, **und führt keine Fremdaufgaben aus** (Gleichungen/Code — er winkt ab wie ein
echter Mensch). Legt nicht beim ersten «Nein» auf — er widersteht, hält aber das Gespräch am Laufen.

**Sitzung:** der Zustand jedes Gesprächs ist separat per `user_id` (mehrere Mitarbeiter gleichzeitig
werden nicht vermischt). Zyklus `/start` (Schwierigkeitswahl) → Dialog → `/finish`. Falls `/finish`
vergessen wurde — läuft die Sitzung nach `SESSION_TIMEOUT_MIN` Minuten Inaktivität ab und wird beim
nächsten Aufruf zurückgesetzt (Lazy-Timeout, ohne Hintergrundprozesse; Standard 30 Min). Implementiert in
`get_active_session()`.

---

## 6. Lösungsarchitektur (Schema)

```
Mitarbeiter (Telegram)
        │  Sprachnachricht (voice, ogg/opus)
        ▼
  ┌─────────────────────────┐
  │  Telegram Bot (aiogram) │   ← Eingang, Orchestrierung, Sitzungszustand
  └─────────────────────────┘
        │ audio → ffmpeg dekodiert
        ▼
  ┌─────────────────────────┐
  │  STT  (faster-whisper)  │   Sprache → Text
  └─────────────────────────┘
        │ Text des Mitarbeiters
        ▼
  ┌─────────────────────────────────────────────┐
  │  Dialog-Engine (LLM, Anbieter AUSTAUSCHBAR)  │
  │   • Persona + Szenario (1 von 13)             │
  │   • Schwierigkeitsgrad (1–4) steuert Nachgiebigkeit │
  │   • Dialoggedächtnis (Gesprächsverlauf)       │
  └─────────────────────────────────────────────┘
        │ Text-Antwort des Eigentümers
        ▼
  ┌─────────────────────────┐
  │  TTS (Silero) → WAV     │
  │  → ffmpeg → OGG/OPUS    │   damit es als Sprach-«Kreis» ankommt
  └─────────────────────────┘
        │ sendVoice
        ▼
  Telegram (Sprachantwort)

   ── während des Gesprächs: Transkript + Audio → SQLite + Dateien ──
   ── nach /finish: Analyzer (LLM-judge) → Bericht nach 8 Kriterien ──
```

---

## 7. Technologie-Stack (MVP-Final)

| Schicht | MVP / Demo (unsere Wahl) | Produktion / Qualität |
|-----|------------------------|-------------------|
| Bot | `aiogram` (Python 3.12) | dasselbe |
| STT | `faster-whisper`, `small`/`medium` (lokal) | Whisper API / Deepgram |
| Dialog LLM | **`openai/gpt-4o-mini` über OpenRouter** — gewählt durch Vergleich von 6 Modellen (Qualität×Preis×Zuverlässigkeit, $1/1000 Gespräche). Anbieter AUSTAUSCHBAR | beliebiges Modell OpenRouter (Claude/Gemini/…) |
| Richter (Bewertung) | dasselbe gpt-4o-mini (bewertet den MENSCHEN, nicht sich selbst) | stärkeres Modell bei Bedarf |
| TTS | `Silero` (kostenlos, CPU) → Konvertierung in OGG/OPUS über ffmpeg | ElevenLabs / OpenAI TTS |
| Speicher | **SQLite** + lokale Audiodateien + STT-Log (`stt_log`) | Postgres + S3/MinIO |
| Echtzeit (opt.) | — | OpenAI Realtime API + LiveKit/WebRTC |

**Weg:** wir starteten lokal (Ollama, qwen/llama — null Kosten), aber lokale 8B-Modelle
widersprachen sich bei schwierigen Graden → Wechsel zu **OpenRouter / gpt-4o-mini**. Der Tausch kostete
**eine Datei** (`bot/llm.py`) — Beweis, dass die Anbieterschicht wirklich austauschbar ist.
**Prinzip:** STT / LLM / TTS — hinter einer Abstraktion, der Anbieter wird punktuell gewechselt, ohne Umschreiben.

---

## 8. Schwierigkeitsgrade

Keine verschiedenen Modelle/Bots — Parameter einer Persona, die **Nachgiebigkeit** steuern (Abschnitt 5):

| Parameter | Grad 1 | Grad 2 | Grad 3 | Grad 4 |
|---|---|---|---|---|
| Anzahl Einwände | minimal | einige | viele | sehr viele |
| Zustimmungsschwelle zum Treffen | niedrig | mittel | hoch | sehr hoch |
| Vertrauen am Anfang | hoch | moderat | niedrig | fast keines |
| Verhalten | freundlich | vorsichtig | skeptisch | aktiver Widerstand |

13 Szenarien × 4 Grade = Kombination über gemeinsamen Code, keine 52 separaten Programme.

---

## 9. Analyse und Bewertung (wie wir % berechnen)

**LLM-as-judge:** ein separater Aufruf erhält das Transkript + **Rubrik** und gibt
einen strukturierten Bericht zurück. 8 Kriterien aus dem Lastenheft:
1. Qualität des Einstiegs 2. Bedarfsermittlung 3. Qualität der Fragen 4. Einwandbehandlung
5. Vertrauensniveau 6. Terminierungsversuch 7. Verhandlungskompetenzen
8. Gesamtergebnis in % + Stärken + Empfehlungen.

**Gesamtergebnis %:** jedes Kriterium 0–100, zusammen — **gewichteter Durchschnitt** (Gewichte in der Konfiguration;
Einwände und Bedarf werden stärker gewichtet).

**Ehrliche Einschränkungen der Bewertung:**
- Ohne feste Rubrik schwanken die Punkte → Ausgabeformat ist fest/strukturiert.
- **STT-Genauigkeit → Bewertungsgerechtigkeit:** Erkennungsfehler = verzerrte Bewertung.
- **Lokaler Richter ist unzuverlässig** (schwaches RU). Bewertung im Demo ist «plausibel», nicht
  kalibriert (keine Referenzbeispiele). Daher ein Kandidat, den Richter auf API auszulagern.
- **Richter sieht nur Text** — Intonation/Pausen/Sicherheit gehen verloren, dabei sind «Vertrauen» und
  «Verhandlung» zur Hälfte Tonangelegenheit. Textbasierte Bewertung ist verlustbehaftet.

---

## 10. Speicherung

Transkript (Text + Sprecher + Zeit) → SQLite. Audio → lokale Dateien (S3 in Produktion). Bericht → SQLite.
⚠️ Bei `git init`: `.gitignore` für `.env`, Audiodateien und `*.sqlite` (Token und Daten nicht committen).
⚠️ Aufzeichnung von Mitarbeiterstimmen — in Produktion ist Einwilligung/Aufbewahrungsrichtlinie erforderlich
(für Demo ok, aber im Dokument für den Eigentümer erwähnen, um professionell zu wirken).

---

## 11. Umgebungsvoraussetzungen (geprüft 2026-06-17, M1 Pro, 16 GB) ✅

| Was | Status |
|---|---|
| Python | **3.12.13** ✅ (war 3.9.6) |
| ffmpeg | **8.1.1** ✅ (installiert) |
| STT/TTS | lokal (`faster-whisper`, `Silero`) — werden beim Bot-Start geladen |
| LLM | **OpenRouter `gpt-4o-mini`** (Schlüssel `OPENROUTER_API_KEY` in `.env`) — nicht lokal, belastet den Rechner nicht |

Einrichtung: `cp .env.example .env`, `BOT_TOKEN` (von @BotFather) und
`OPENROUTER_API_KEY` (von openrouter.ai) eintragen. Start: `.venv/bin/python -m bot.main`.

---

## 12. Ungefähre Kosten (≈1 Gespräch, ~5 Min)

| Schicht | Kosten |
|---|---|
| LLM (gpt-4o-mini: Dialog + Bewertungsbericht) | **~$1 pro 1000 Gespräche** (gemessen an echten Token) |
| STT (faster-whisper lokal) | ~0 |
| TTS (Silero lokal) | ~0 |

Das Demo kostet also **Cent-Beträge**. Der Hauptkostenfaktor bei großem Volumen — LLM (noch günstiger
möglich — mistral, gemini-flash). Falls Stimme auf ElevenLabs/OpenAI TTS gehoben wird — kommt
Vertonungskosten hinzu (ebenfalls Kleinstbeträge pro Gespräch).

---

## 13. Skalierung

Jedes Gespräch ist unabhängig → horizontal skalierbar (mehr Worker). Engpass — Latenz/Kosten
von STT/TTS/LLM. Lokaler Stack trägt viele Nutzer nicht (eine Hardware) → für Produktion API + Queue
(Redis/Celery).

---

## 14. Hauptrisiken (ehrlich)

1. **«Maximaler Realismus» × «lokal/kostenlos»** — widersprechen sich. Kleine lokale Modelle
   halten Rolle/RU schlechter. Absicherung — austauschbarer Anbieter.
2. **Pipeline-Latenz** — STT (lokal ~1–2 s) + LLM (OpenRouter ~2–5 s) + TTS (lokal ~1–2 s)
   ≈ 5–10 s/Antwort. Für Sprachnachrichten-Austausch akzeptabel.
3. **Gesprächsrealismus — Tuning, kein Code.** Nicht «zu 100 % fertig».
4. **Bewertung** hängt von Rubrik, STT-Genauigkeit und Richter-Stärke ab; aus Text — verlustbehaftet.
5. **Echtzeit** (falls gewünscht) — Komplexitätssprung von Wochen.
6. **Obergrenze Variante A** — Druck/Reaktionsgeschwindigkeit werden nicht trainiert (async).

---

## 15. Phasenplan

| Phase | Was | Status / Orientierung |
|---|---|---|
| 0 | Dokumentation + Regeln + Umgebungsprüfung und -einrichtung | ✅ abgeschlossen |
| 1 | Bot-Skelett: Sprache→STT→LLM→TTS→Sprache, 1 Szenario, Zyklus /start–/finish, Schwierigkeitsgrade | 3–5 Tage |
| 2 | Mehrere Szenarien + Grade + Persona-guardrail | + einige Tage |
| 3 | Speicherung (SQLite) + Analysebericht (Richter + Rubrik) | +2–3 Tage |
| 4 | Realismus-Politur + **Vorschlagsdokument für den Eigentümer** (Deliverable Nr. 1) | iterativ |
| 5 | (Opt.) Echtzeit über Mini App / WebRTC | Wochen |

**Ziel der Testaufgabe:** solides Demo der Phasen 1–3 (1–2 Szenarien, 2 Grade, vollständiger Zyklus
Sprache→Dialog→Bericht) + Vorschlagsdokument für den Eigentümer.

---

## 16. Empirisch geprüft (auf gpt-4o-mini)

- **Grade funktionieren** — Schwierigkeitsgradient ist robust, auch gegen adaptiven
  LLM-Mitarbeiter (Widerstand steigt L1→L4: 5,5/6,5/7,7/8,8). Kein Artefakt eines einzelnen Skripts.
- **13 Szenarien** — jedes bringt seinen Einwand vor (52/52), 0 Widersprüche.
- **Guardrail** — hat 48 Jailbreak-Angriffe überstanden (u. a. «du bist ein Bot», reveal-prompt,
  Fremdaufgaben); nach Härtung 0 Durchbrüche.
- **Modellwahl** — Vergleich von 6 Modellen; gpt-4o-mini = Balance Qualität×Preis×Zuverlässigkeit.
- **STT-Beobachtbarkeit** — Log `stt_log` (Audio ↔ was Whisper gehört hat, einschließlich Fehlern)
  + HTML-Viewer (`tools/stt_review.py`) zur Genauigkeitsprüfung.
- **Tests** — `pytest tests/` (17 Logiktests). Validierungsforschung — in `research/`.

## 17. Bekannte Grenzen / Zukunft (ehrlich)

- **Stimme** — Silero klingt roboterhaft; Wechsel auf ElevenLabs/OpenAI TTS = Austausch eines Moduls.
- **Bewertungskalibrierung** — Richter sind unter sich konsistent, aber nicht mit echtem Trainer abgeglichen.
- **Lange Sprachnachrichten (>20 MB)** — Telegram liefert diese nicht aus; wird sicher behandelt (try/except),
  tritt bei normalen Trainingsrepliken nicht auf.
- **`recordings/` ohne Auto-Bereinigung** — bewusst (Aufzeichnungsarchiv). Für Produktion: Retention N Tage
  / S3 + Einwilligung zur Aufzeichnung von Mitarbeitergesprächen.
- **Einzelprozess** — parallele Nutzer werden in die Warteschlange eingereiht (Sperren). Für Produktion — Worker-Pool.
