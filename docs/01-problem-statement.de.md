# Aufgabenstellung

**[English](01-problem-statement.md) · Deutsch · [Українська](01-problem-statement.uk.md)**

> In eigenen Worten aus einer Probeaufgabe paraphrasiert. Der ursprüngliche Wortlaut und alle
> identifizierenden Angaben sind bewusst weggelassen.

Eine Immobilienagentur möchte ihre Callcenter-Mitarbeiter für Kaltakquise-Anrufe bei
Immobilieneigentümern schulen. Ziel ist ein Sprachbot (in Telegram), der die Rolle eines
Eigentümers spielt und ein realistisches Gespräch mit einem Mitarbeiter führt — mit den
Einwänden, Zweifeln und Absagen, die auf dem Immobilienmarkt üblich sind.

## Ziel

Mitarbeiter sollen den gesamten Anruf üben: Kontakt herstellen, Bedarf ermitteln, Einwände
behandeln, den Mehrwert der Agentur darstellen, Vertrauen aufbauen, einen Termin vereinbaren,
verhandeln und das Gespräch abschließen.

## Szenarien

Der Bot soll die häufigsten Situationen abbilden — z. B. einen Eigentümer, der: nicht mit
einer Agentur arbeiten will; selbst verkaufen möchte; die Provision zu hoch findet; schlechte
Erfahrungen mit Maklern hatte; sicher ist, ohne Vermittler verkaufen zu können; auf einen
besseren Zeitpunkt warten will; sich erst mit der Familie beraten möchte; keinen Termin
vereinbaren will; Agenturen nicht vertraut; den Nutzen eines Maklers nicht sieht; mehrere
Agenturen vergleichen will; Zusatzkosten und Verpflichtungen fürchtet — sowie weitere typische
Einwände.

## Schwierigkeitsstufen

- **Stufe 1 — Anfänger:** freundlicher Eigentümer, wenige Einwände, Termin leicht zu vereinbaren.
- **Stufe 2 — Mittel:** vorsichtiger, mehrere Einwände, Rückfragen.
- **Stufe 3 — Fortgeschritten:** skeptisch, viele Einwände, sichere Einwandbehandlung nötig.
- **Stufe 4 — Experte:** sehr schwierig, aktiver Widerstand und Misstrauen, mehrere Absagen in Folge.

## Anforderungen

- Telegram-Bot als erste Version; Sprache-zu-Sprache-Interaktion.
- Kostenlose / günstige Werkzeuge während der Entwicklung.
- Möglichst realistischer Dialog.
- Gespräche aufzeichnen und für spätere Analysen speichern.

## Bericht pro Anruf

Nach jedem Anruf soll der Bot einen Bericht erstellen zu: Qualität des Einstiegs,
Bedarfsermittlung, Fragenqualität, Einwandbehandlung, aufgebautem Vertrauen, Terminversuch,
Verhandlungsgeschick, einer Gesamtnote (%), Stärken und Verbesserungsempfehlungen.

## Angeforderte Dokumentation

Welche KI-Modelle verwendet werden; die nötigen Dienste und Integrationen; ein
Architekturdiagramm; ungefähre Betriebskosten; Skalierungsmöglichkeiten; und wie sich die
Lösung in die bestehenden Schulungs- und Vertriebsabläufe des Unternehmens integrieren ließe.
