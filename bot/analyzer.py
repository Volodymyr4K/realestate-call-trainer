"""Аналізатор розмови: LLM-суддя оцінює менеджера за 8 критеріями ТЗ.

LLM оцінює кожен критерій (0-100) + сильні сторони + рекомендації.
Підсумковий % рахує КОД (зважене середнє) — детермінізм, без арифметики LLM.
"""
from bot import llm

# Критерії ТЗ: ключ, назва, вага (сума ваг = 1.0). Вага = важливість у підсумку.
CRITERIA = [
    ("contact",     "Качество начала разговора",      0.10),
    ("needs",       "Выявление потребностей клиента",  0.15),
    ("questions",   "Качество задаваемых вопросов",    0.10),
    ("objections",  "Работа с возражениями",           0.25),
    ("trust",       "Уровень созданного доверия",      0.15),
    ("meeting",     "Попытка назначения встречи",      0.10),
    ("negotiation", "Навыки ведения переговоров",      0.15),
]

_RUBRIC = """Ты — опытный тренер по продажам недвижимости. Оцени работу МЕНЕДЖЕРА
(не собственника) по стенограмме тренировочного звонка. Менеджер агентства звонил
собственнику недвижимости (ситуация собственника указана ниже).

По КАЖДОМУ критерию поставь оценку 0-100 И дай короткий комментарий (1 предложение:
что именно сделал хорошо или упустил, по возможности с опорой на конкретную реплику):
- contact (начало): поздоровался, представился, обозначил цель, зацепил внимание.
- needs (потребности): выяснил ситуацию и мотивацию собственника, открытые вопросы.
- questions (вопросы): вопросы уместные, открытые, ведущие к цели, а не допрос.
- objections (возражения): услышал возражение, не спорил в лоб, привёл аргумент.
- trust (доверие): держался уверенно и доброжелательно, без давления.
- meeting (встреча): предложил конкретную встречу/оценку, работал с отказом.
- negotiation (переговоры): вёл разговор, удерживал инициативу, двигал к результату.

0-30 — плохо/не сделано, 40-60 — средне, 70-100 — хорошо.
Рекомендации делай КОНКРЕТНЫМИ: что и как сказать в следующий раз, по возможности с
примером фразы.

Ответь СТРОГО в JSON и ТОЛЬКО на русском языке:
{
 "scores": {"contact": int, "needs": int, "questions": int, "objections": int,
            "trust": int, "meeting": int, "negotiation": int},
 "comments": {"contact": "...", "needs": "...", "questions": "...", "objections": "...",
              "trust": "...", "meeting": "...", "negotiation": "..."},
 "strengths": ["короткая сильная сторона", ...],
 "recommendations": ["конкретный совет с примером фразы", ...]
}"""


def _clamp(v) -> int:
    try:
        return max(0, min(100, int(v)))
    except (TypeError, ValueError):
        return 0


def _as_list(v) -> list[str]:
    """LLM може повернути рядок замість списку — нормалізуємо, щоб формат не ламався."""
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def analyze(transcript: list, level: int, scenario_context: str = "") -> dict:
    """Повертає звіт: бали по критеріях, підсумковий %, сильні сторони, рекомендації.

    scenario_context — опис ситуації власника (зі SCENARIOS), щоб суддя оцінював
    у правильному контексті. level — рівень складності клієнта.
    """
    dialog = "\n".join(
        f"{'Менеджер' if who == 'manager' else 'Собственник'}: {text}"
        for who, text in transcript
    )
    context = ""
    if scenario_context:
        context += f"СИТУАЦИЯ СОБСТВЕННИКА: {scenario_context}\n"
    context += f"УРОВЕНЬ СЛОЖНОСТИ КЛИЕНТА: {level} (1=лёгкий, 4=очень сложный)\n\n"
    raw = llm.complete_json([
        {"role": "system", "content": _RUBRIC},
        {"role": "user", "content": f"{context}СТЕНОГРАММА:\n{dialog}"},
    ])
    return build_report(raw)


def build_report(raw: dict) -> dict:
    """Збирає фінальний звіт із сирої відповіді LLM (рахує підсумковий %)."""
    raw = raw if isinstance(raw, dict) else {}
    raw_scores = raw.get("scores") if isinstance(raw.get("scores"), dict) else {}
    raw_comments = raw.get("comments") if isinstance(raw.get("comments"), dict) else {}
    scores = {key: _clamp(raw_scores.get(key)) for key, _, _ in CRITERIA}
    comments = {key: str(raw_comments.get(key, "")).strip() for key, _, _ in CRITERIA}
    overall = round(sum(scores[key] * w for key, _, w in CRITERIA))
    return {
        "scores": scores,
        "comments": comments,
        "overall": overall,
        "strengths": _as_list(raw.get("strengths")),
        "recommendations": _as_list(raw.get("recommendations")),
    }


def format_report(report: dict) -> str:
    """Текст звіту для Telegram (plain-text, без Markdown — щоб не падало на спецсимволах)."""
    lines = [f"📊 ИТОГОВАЯ ОЦЕНКА: {report['overall']}%", "", "По критериям:"]
    comments = report.get("comments", {})
    for key, label, _ in CRITERIA:
        line = f"• {label}: {report['scores'][key]}/100"
        c = comments.get(key, "")
        if c:
            line += f" — {c}"
        lines.append(line)
    if report.get("strengths"):
        lines += ["", "Сильные стороны:"] + [f"✅ {s}" for s in report["strengths"]]
    if report.get("recommendations"):
        lines += ["", "Рекомендации:"] + [f"🔸 {r}" for r in report["recommendations"]]
    return "\n".join(lines)
