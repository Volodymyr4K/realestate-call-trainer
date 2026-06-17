"""
Investigate whether the difficulty-level gradient is robust across manager styles.

Runs three manager variants:
  1. ADAPTIVE  — GPT-4o-mini playing a competent real-estate salesperson (Russian)
  2. PUSHY     — short fixed aggressive script
  3. SOFT      — short fixed consultative script

Test matrix: 5 scenarios × 4 levels × 3 reps = 60 dialogues per manager variant
                                                = 180 dialogues total

Judge: GPT-4o-mini JSON {"agreed_meeting": bool, "resistance": int 1-10}

Baseline from original scripted QA (supplied externally):
  L1=88% agree / 4.6 resistance
  L2=12% agree / 6.2 resistance
  L3= 0% agree / 6.7 resistance
  L4= 0% agree / 7.9 resistance
"""

import json
import sys
import time
from pathlib import Path

from bot import llm
from bot.persona import build_system_prompt, SCENARIOS, LEVELS

# ──────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────
TEST_SCENARIOS = [1, 3, 6, 9, 12]
TEST_LEVELS    = [1, 2, 3, 4]
REPS           = 3          # repetitions per (scenario, level) cell
MAX_TURNS      = 8          # max manager turns per dialogue
MODEL          = "openai/gpt-4o-mini"

OUT_PATH = Path("/tmp/investigate_manager_results.json")

# ──────────────────────────────────────────────────────────────
# MANAGER SYSTEM PROMPT (adaptive LLM manager)
# ──────────────────────────────────────────────────────────────
ADAPTIVE_MANAGER_SYSTEM = """Ты — опытный менеджер по продажам риелторского агентства «ДомПро».
Твоя единственная цель в этом звонке — назначить личную встречу (очный визит) с собственником квартиры.
Ты звонишь по объявлению о продаже квартиры.

ПРАВИЛА:
- Говори коротко и по-деловому: обычно 1-2 предложения за реплику.
- Будь живым, убедительным, настойчивым, но не грубым.
- Отрабатывай возражения конкретно и профессионально.
- Используй технику «АВС» (Always Be Closing): каждая реплика ведёт к встрече.
- Предлагай конкретную пользу (бесплатная оценка, база покупателей, защита сделки).
- Если собственник категорически отказывается после 3+ попыток — вежливо прощайся.
- Пиши ТОЛЬКО свою реплику, без скобок и ремарок.
- Отвечай ТОЛЬКО на русском языке.
- Ты не ИИ и не бот — ты живой менеджер Андрей."""

# ──────────────────────────────────────────────────────────────
# FIXED PUSHY MANAGER (aggressive / high-pressure)
# ──────────────────────────────────────────────────────────────
PUSHY_TURNS = [
    "Здравствуйте, агентство «ДомПро», Андрей. Ваша квартира в продаже — я уже знаю покупателей, давайте встретимся сегодня же!",
    "Слушайте, вы серьёзно думаете, что сами продадите быстро? У нас клиенты с деньгами прямо сейчас, вы теряете время и деньги!",
    "Вы вообще понимаете, что каждый день промедления — это минус в цене? Встреча займёт 20 минут, назначайте прямо сейчас.",
    "Ладно, давайте честно: все, кто отказывался от агентства, потом жалели. Не повторяйте их ошибку — когда вам удобно встретиться?",
    "Последний раз предлагаю: бесплатная оценка, конкретные покупатели, без предоплаты. Завтра утром или вечером?",
    "Хорошо, ваш выбор. Только потом не говорите, что не предупреждали. До свидания.",
]

# ──────────────────────────────────────────────────────────────
# FIXED SOFT / CONSULTATIVE MANAGER
# ──────────────────────────────────────────────────────────────
SOFT_TURNS = [
    "Добрый день, меня зовут Андрей, агентство «ДомПро». Увидел ваше объявление — у вас сейчас актуально продажа?",
    "Понятно. Интересно, как у вас пока идёт процесс? Много ли обращений от покупателей?",
    "Знаете, мы как раз специализируемся на таких ситуациях. Могу рассказать, чем конкретно отличаемся — если интересно.",
    "Я вас понимаю, у многих схожие опасения. Давайте так: просто встретимся на 15 минут, я расскажу про наш подход — и вы сами решите, нужно это вам или нет.",
    "Совсем ни к чему вас не обязываю. Просто живая беседа, без давления. Когда вам было бы комфортно — может, в любое удобное время на этой неделе?",
    "Ладно, не хочу настаивать. Оставлю номер — если вдруг передумаете, буду рад помочь. Удачи с продажей!",
]

# ──────────────────────────────────────────────────────────────
# JUDGE
# ──────────────────────────────────────────────────────────────
JUDGE_SYSTEM = """Ты — эксперт-оценщик телефонных переговоров по продаже недвижимости.
Проанализируй диалог между менеджером агентства и собственником квартиры.
Верни ответ СТРОГО в формате JSON без пояснений:
{"agreed_meeting": <true или false>, "resistance": <целое число от 1 до 10>}

agreed_meeting = true, если в диалоге собственник явно согласился на личную встречу или визит.
resistance = уровень сопротивления собственника в среднем по всему диалогу:
  1-3 = минимальное (тёплый, почти без возражений)
  4-5 = умеренное (несколько возражений, но сговорчивый)
  6-7 = высокое (много возражений, скептичен)
  8-10 = очень высокое (холодный, раздражён, категорически отказывается)"""


def judge_dialogue(transcript_text: str) -> dict:
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": f"Диалог:\n{transcript_text}"},
    ]
    result = llm.complete_json(messages, model=MODEL)
    return {
        "agreed_meeting": bool(result.get("agreed_meeting", False)),
        "resistance": int(result.get("resistance", 5)),
    }


# ──────────────────────────────────────────────────────────────
# DIALOGUE RUNNERS
# ──────────────────────────────────────────────────────────────

def run_adaptive_dialogue(scenario_id: int, level: int) -> dict:
    """Run a dialogue where the manager is an LLM-driven adaptive agent."""
    owner_system = build_system_prompt(scenario_id, level)
    owner_history = [
        {"role": "system", "content": owner_system},
        {"role": "assistant", "content": "Алло?"},
    ]
    manager_history = [
        {"role": "system", "content": ADAPTIVE_MANAGER_SYSTEM},
    ]

    transcript_lines = ["Собственник: Алло?"]

    for turn_idx in range(MAX_TURNS):
        # Manager generates next line
        # Give manager the full conversation context
        manager_history_for_call = manager_history + [
            {
                "role": "user",
                "content": (
                    "Текущий диалог с собственником:\n" +
                    "\n".join(transcript_lines) +
                    "\n\nТвоя следующая реплика менеджера (только текст, без меток):"
                ),
            }
        ]
        manager_reply = llm.reply(manager_history_for_call, model=MODEL)

        transcript_lines.append(f"Менеджер: {manager_reply}")
        manager_history.append({"role": "assistant", "content": manager_reply})

        # Feed manager reply as user input to owner
        owner_history.append({"role": "user", "content": manager_reply})
        owner_reply = llm.reply(owner_history, model=MODEL)
        owner_history.append({"role": "assistant", "content": owner_reply})

        transcript_lines.append(f"Собственник: {owner_reply}")

        # Check for early termination signals (manager gave up or meeting agreed)
        lower_manager = manager_reply.lower()
        lower_owner   = owner_reply.lower()
        gave_up = any(p in lower_manager for p in ["до свидания", "прощайте", "всего доброго", "удачи"])
        # Continue even if meeting agreed, to capture the full exchange
        if gave_up and turn_idx >= 3:
            break

    transcript_text = "\n".join(transcript_lines)
    verdict = judge_dialogue(transcript_text)
    return {
        "manager_type": "adaptive",
        "scenario_id": scenario_id,
        "level": level,
        "transcript": transcript_text,
        **verdict,
    }


def run_fixed_dialogue(scenario_id: int, level: int, turns: list[str], manager_type: str) -> dict:
    """Run a dialogue with a fixed scripted manager."""
    owner_system = build_system_prompt(scenario_id, level)
    owner_history = [
        {"role": "system", "content": owner_system},
        {"role": "assistant", "content": "Алло?"},
    ]
    transcript_lines = ["Собственник: Алло?"]

    for manager_line in turns:
        transcript_lines.append(f"Менеджер: {manager_line}")
        owner_history.append({"role": "user", "content": manager_line})
        owner_reply = llm.reply(owner_history, model=MODEL)
        owner_history.append({"role": "assistant", "content": owner_reply})
        transcript_lines.append(f"Собственник: {owner_reply}")

    transcript_text = "\n".join(transcript_lines)
    verdict = judge_dialogue(transcript_text)
    return {
        "manager_type": manager_type,
        "scenario_id": scenario_id,
        "level": level,
        "transcript": transcript_text,
        **verdict,
    }


# ──────────────────────────────────────────────────────────────
# AGGREGATE & PRINT
# ──────────────────────────────────────────────────────────────

def aggregate(results: list[dict], manager_type: str) -> dict:
    """Return per-level stats for a given manager type."""
    filtered = [r for r in results if r["manager_type"] == manager_type]
    stats = {}
    for level in TEST_LEVELS:
        subset = [r for r in filtered if r["level"] == level]
        if not subset:
            stats[level] = {"agree_pct": None, "avg_resistance": None, "n": 0}
            continue
        n = len(subset)
        agreed = sum(1 for r in subset if r["agreed_meeting"])
        avg_res = sum(r["resistance"] for r in subset) / n
        stats[level] = {
            "agree_pct": round(agreed / n * 100),
            "avg_resistance": round(avg_res, 1),
            "n": n,
        }
    return stats


def print_table(stats: dict, label: str):
    print(f"\n{'='*55}")
    print(f"  {label}")
    print(f"{'='*55}")
    print(f"  {'Level':<8} {'Name':<14} {'Agree%':>7} {'Avg Resist':>11} {'N':>4}")
    print(f"  {'-'*50}")
    for level in TEST_LEVELS:
        s = stats[level]
        name = LEVELS[level]["name"]
        agree = f"{s['agree_pct']}%" if s['agree_pct'] is not None else "—"
        res   = str(s['avg_resistance']) if s['avg_resistance'] is not None else "—"
        print(f"  L{level}      {name:<14} {agree:>7} {res:>11} {s['n']:>4}")


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    all_results = []
    total_cells = len(TEST_SCENARIOS) * len(TEST_LEVELS) * REPS
    manager_variants = [
        ("adaptive", None),
        ("pushy",    PUSHY_TURNS),
        ("soft",     SOFT_TURNS),
    ]

    print(f"Investigate manager robustness")
    print(f"Scenarios: {TEST_SCENARIOS}  Levels: {TEST_LEVELS}  Reps: {REPS}")
    print(f"Cells per manager: {total_cells}  Manager variants: {len(manager_variants)}")
    print(f"Total dialogues: {total_cells * len(manager_variants)}")
    print(f"Model: {MODEL}\n")

    for mtype, turns in manager_variants:
        print(f"\n>>> Running manager variant: {mtype.upper()}")
        variant_done = 0
        for scenario_id in TEST_SCENARIOS:
            for level in TEST_LEVELS:
                for rep in range(REPS):
                    variant_done += 1
                    tag = f"[{mtype}] sc={scenario_id} L{level} rep{rep+1}"
                    try:
                        if mtype == "adaptive":
                            r = run_adaptive_dialogue(scenario_id, level)
                        else:
                            r = run_fixed_dialogue(scenario_id, level, turns, mtype)
                        r["rep"] = rep
                        all_results.append(r)
                        verdict_str = "AGREE" if r["agreed_meeting"] else "no-meet"
                        print(f"  {tag}: {verdict_str}, resistance={r['resistance']}")
                    except Exception as e:
                        print(f"  {tag}: ERROR — {e}")

        # Save checkpoint after each variant
        OUT_PATH.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [checkpoint saved → {OUT_PATH}]")

    # ── Final report ──────────────────────────────────────────
    print("\n\n" + "="*55)
    print("  BASELINE (original fixed 6-line script, scenario 1 only, N=10/level)")
    print("="*55)
    baseline = {
        1: {"agree_pct": 88, "avg_resistance": 4.6, "n": 10},
        2: {"agree_pct": 12, "avg_resistance": 6.2, "n": 10},
        3: {"agree_pct":  0, "avg_resistance": 6.7, "n": 10},
        4: {"agree_pct":  0, "avg_resistance": 7.9, "n": 10},
    }
    print(f"  {'Level':<8} {'Name':<14} {'Agree%':>7} {'Avg Resist':>11} {'N':>4}")
    print(f"  {'-'*50}")
    for level in TEST_LEVELS:
        s = baseline[level]
        name = LEVELS[level]["name"]
        print(f"  L{level}      {name:<14} {s['agree_pct']:>6}% {s['avg_resistance']:>11} {s['n']:>4}")

    for mtype, _ in manager_variants:
        stats = aggregate(all_results, mtype)
        print_table(stats, f"MANAGER: {mtype.upper()}")

    # ── Gradient check ────────────────────────────────────────
    print("\n\n" + "="*55)
    print("  GRADIENT COMPARISON (Agree% L1 → L4)")
    print("="*55)
    print(f"  {'Manager':<12} {'L1':>5} {'L2':>5} {'L3':>5} {'L4':>5}  Monotone?")
    print(f"  {'-'*50}")

    def row_agree(stats):
        return [stats[lvl]['agree_pct'] for lvl in TEST_LEVELS]

    rows = {"baseline": [88, 12, 0, 0]}
    for mtype, _ in manager_variants:
        rows[mtype] = row_agree(aggregate(all_results, mtype))

    for label, vals in rows.items():
        mono = all(vals[i] >= vals[i+1] for i in range(len(vals)-1) if vals[i] is not None and vals[i+1] is not None)
        v = "  ".join(f"{v:>5}" if v is not None else "   — " for v in vals)
        print(f"  {label:<12} {v}  {'YES' if mono else 'NO'}")

    elapsed = time.time() - t0
    print(f"\nTotal time: {elapsed:.0f}s")
    print(f"Full results → {OUT_PATH}")

    # Print a brief verdict
    print("\n" + "="*55)
    print("  VERDICT SUMMARY")
    print("="*55)
    all_mono = True
    for mtype, _ in manager_variants:
        vals = row_agree(aggregate(all_results, mtype))
        valid = [v for v in vals if v is not None]
        mono = all(valid[i] >= valid[i+1] for i in range(len(valid)-1))
        if not mono:
            all_mono = False
        print(f"  {mtype.upper():<12}: L1={vals[0]}%, L2={vals[1]}%, L3={vals[2]}%, L4={vals[3]}%  ({'monotone ✓' if mono else 'NOT monotone ✗'})")

    if all_mono:
        print("\n  GRADIENT IS ROBUST: monotone L1→L4 across all manager styles.")
    else:
        print("\n  GRADIENT IS NOT FULLY ROBUST: at least one manager style breaks monotonicity.")


if __name__ == "__main__":
    sys.exit(main())
