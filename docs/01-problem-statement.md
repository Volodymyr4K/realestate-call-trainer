# Problem statement

**English · [Deutsch](01-problem-statement.de.md) · [Українська](01-problem-statement.uk.md)**

> Paraphrased in my own words from a take-home brief. The original verbatim text and any
> identifying details are intentionally omitted.

A real-estate agency wants to train its call-center agents on cold calls to property owners.
The goal is a voice bot (in Telegram) that plays the role of a property owner and holds a
realistic conversation with an agent, reproducing the objections, doubts, and refusals that
are common on the real-estate market.

## Goal

Let agents rehearse the full call: establishing contact, uncovering needs, handling
objections, presenting the agency's value, building trust, booking a meeting, negotiating,
and closing the call.

## Scenarios

The bot should reproduce the most common situations — for example, an owner who: doesn't want
to work with an agency; plans to sell on their own; thinks the commission is too high; had a
bad experience with realtors; is sure they can sell without intermediaries; wants to wait for
a better moment; wants to consult their family; isn't ready to book a meeting; doesn't trust
agencies; doesn't see the value of a realtor; wants to compare several agencies; fears extra
costs and obligations — plus other typical objections.

## Difficulty levels

- **L1 — Beginner:** friendly owner, few objections, easy to book a meeting.
- **L2 — Intermediate:** more cautious, several objections, follow-up questions.
- **L3 — Advanced:** skeptical, many objections, needs confident objection handling.
- **L4 — Expert:** very difficult, active resistance and distrust, several refusals in a row.

## Requirements

- Telegram bot as the first version; voice-to-voice interaction.
- Free / inexpensive tooling during development.
- Dialogue as realistic as possible.
- Record and store conversations for later analysis.

## Per-call report

After each call the bot should produce a report covering: quality of the opening, needs
discovery, question quality, objection handling, trust built, the meeting attempt,
negotiation skills, an overall score (%), strengths, and recommendations for improvement.

## Documentation requested

Which AI models are used; the required services and integrations; an architecture diagram;
rough operating cost; scaling options; and how the solution could integrate into the
company's existing training and sales workflow.
