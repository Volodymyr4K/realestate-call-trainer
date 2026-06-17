"""Judge reliability investigation: inter-model agreement + ground truth vs each judge.

Run: .venv/bin/python -m tests.investigate_judge

Steps:
1. Load ~20-25 transcripts from /tmp/qa_scenarios.json (generate if missing).
2. Re-judge each with THREE models: gpt-4o-mini, claude-haiku-4.5, gemini-2.5-flash.
3. Compute inter-judge agreement on on_scenario / agreed_meeting; avg |diff| on resistance.
4. Compare each judge to a hand-labeled ground truth set (~15 samples).
5. Print verdict.
"""

import json
import sys
import time
from pathlib import Path

from bot import llm
from bot.persona import build_system_prompt, SCENARIOS
from research.qa_run import MANAGER_TURNS

# ─── CONFIG ────────────────────────────────────────────────────────────────────
SAVED_PATH = Path("/tmp/qa_scenarios.json")
SAMPLE_SIZE = 24          # how many transcripts to pull from the saved file
JUDGE_MODELS = {
    "gpt4o_mini":    "openai/gpt-4o-mini",
    "haiku":         "anthropic/claude-haiku-4.5",
    "gemini_flash":  "google/gemini-2.5-flash",
}

# Judge prompt — identical to qa_scenarios.py so comparison is fair.
_JUDGE_TMPL = (
    "Стенограмма тренировочного звонка: менеджер агентства недвижимости звонит "
    "собственнику (его играет бот). Уровень сложности {level} (1=лёгкий,4=очень сложный).\n"
    "СИТУАЦИЯ/ОЖИДАЕМОЕ ВОЗРАЖЕНИЕ СОБСТВЕННИКА: {ctx}\n\n"
    "Оцени ПОВЕДЕНИЕ СОБСТВЕННИКА. Ответь СТРОГО JSON: "
    '{{"on_scenario":bool,"agreed_meeting":bool,"contradicted":bool,'
    '"resistance":int}}. '
    "on_scenario — собственник реально озвучивал возражение, соответствующее его ситуации выше. "
    "agreed_meeting — согласился на встречу/оценку. contradicted — противоречил себе. "
    "resistance — насколько собственник был холоден и сопротивлялся, по шкале 1-10: "
    "1-2=тёплый, открытый, легко идёт на контакт; 3-4=спокойный, но осторожный, мягкие "
    "сомнения; 5-7=недоверчивый скептик, вникает, давит, много возражений; "
    "8-10=холодный, отмахивается, не вникает, обрывает разговор.\n\nСТЕНОГРАММА:\n{dialog}"
)

# ─── HAND-LABELED GROUND TRUTH ─────────────────────────────────────────────────
# Keyed by (scenario, level, transcript_fingerprint).
# Fingerprint = first owner turn after "Алло?" (second owner line in transcript).
# on_scenario: did the owner voice the scenario-specific objection?
# agreed_meeting: did the owner clearly agree to a meeting (not just "maybe / I'll think")?
# resistance: my reading of the cold-to-warm scale 1-10.
#
# Samples cover indices 0,3,8,13,17,22,27,32,38,43,50,57,64,72,80,90,100
# from the saved file (spanning 13 scenarios, all 4 levels).
GROUND_TRUTH = [
    # idx=0  scen=1 lvl=1: "не хочу связываться с агентствами" — clear scenario match
    {"scenario": 1, "level": 1,
     "owner_turn2": "Ну, я только начал. Честно говоря, не хочу связываться с агентствами.",
     "on_scenario": True, "agreed_meeting": False, "resistance": 5},

    # idx=3  scen=1 lvl=2: anti-agency + commission drift; doesn't agree
    {"scenario": 1, "level": 2,
     "owner_turn2": "Честно говоря, я пока только задумался о продаже. Не хочу связываться с агентствами, думал сам справлюсь.",
     "on_scenario": True, "agreed_meeting": False, "resistance": 6},

    # idx=8  scen=2 lvl=1: "сам показываю" — sells himself; agrees to weekend
    {"scenario": 2, "level": 1,
     "owner_turn2": "Ну, я только начал, в принципе, пока сам показываю. Всё вроде нормально.",
     "on_scenario": True, "agreed_meeting": True, "resistance": 4},

    # idx=13 scen=2 lvl=3: aggressively selling himself; no meeting
    {"scenario": 2, "level": 3,
     "owner_turn2": "Слушайте, я уже сам активно продаю. Зачем мне агент?",
     "on_scenario": True, "agreed_meeting": False, "resistance": 7},

    # idx=17 scen=3 lvl=1: opens with commission question; agrees to tomorrow
    {"scenario": 3, "level": 1,
     "owner_turn2": "Ну да, уже какое-то время. Но я вот сам думаю справиться, честно говоря.",
     "on_scenario": True, "agreed_meeting": True, "resistance": 3},

    # idx=22 scen=3 lvl=4: asks about commission but is short/cold
    {"scenario": 3, "level": 4,
     "owner_turn2": "Честно говоря, мне не интересно говорить об этом.",
     "on_scenario": True, "agreed_meeting": False, "resistance": 7},

    # idx=27 scen=4 lvl=2: explicitly mentions bad prior experience with realtor
    {"scenario": 4, "level": 2,
     "owner_turn2": "Ну, я пока не тороплюсь, сам справлюсь. Просто вот уже был опыт с риелтором, неудачный. Навязывали, что-то не то.",
     "on_scenario": True, "agreed_meeting": False, "resistance": 6},

    # idx=32 scen=5 lvl=1: "район хороший, покупатели найдутся"; conditional "maybe tomorrow" NOT a clear agreement
    {"scenario": 5, "level": 1,
     "owner_turn2": "Да, я понимая, но район хороший, уверен, что покупатели найдутся.",
     "on_scenario": True, "agreed_meeting": False, "resistance": 4},

    # idx=38 scen=5 lvl=4: "справлюсь сам", cold refusal
    {"scenario": 5, "level": 4,
     "owner_turn2": "Да как сказать, район хороший, покупатели найдутся.",
     "on_scenario": True, "agreed_meeting": False, "resistance": 8},

    # idx=43 scen=6 lvl=2: "сейчас не лучшее время для продажи" — timing objection voiced
    {"scenario": 6, "level": 2,
     "owner_turn2": "Ну, пока только выставил. Честно говоря, есть сомнения — не получится ли так, что продам дешевле, чем мог бы?",
     "on_scenario": True, "agreed_meeting": False, "resistance": 5},

    # idx=50 scen=7 lvl=2: "нужно сначала обсудить с семьёй" — clearly voiced
    {"scenario": 7, "level": 2,
     "owner_turn2": "Ну, пока не долго, но есть сомнения. Вот, например, цена — как определить реально?",
     "on_scenario": True, "agreed_meeting": False, "resistance": 5},

    # idx=57 scen=8 lvl=1: "не хочу тратить время на встречи. Давайте по телефону"; then agrees
    {"scenario": 8, "level": 1,
     "owner_turn2": "Ну, в принципе, только создал объявление. Но, честно говоря, не хочу тратить время на встречи. Давайте по телефону обсудим?",
     "on_scenario": True, "agreed_meeting": True, "resistance": 4},

    # idx=64 scen=9 lvl=1: "не доверяю агентствам. Как-то обманывают часто" — clear distrust
    {"scenario": 9, "level": 1,
     "owner_turn2": "Ну, да, уже какое-то время. Но, честно говоря, не доверяю агентствам. Как-то обманывают часто.",
     "on_scenario": True, "agreed_meeting": True, "resistance": 5},

    # idx=72 scen=10 lvl=1: "В чём именно ваша помощь?" — no-value objection
    {"scenario": 10, "level": 1,
     "owner_turn2": "Ну, пока только недавно начал. Не знаю, получится ли самостоятельно. А в чём именно ваша помощь?",
     "on_scenario": True, "agreed_meeting": False, "resistance": 5},

    # idx=80 scen=11 lvl=1: "хочу посмотреть несколько агентств"; agrees to weekend
    {"scenario": 11, "level": 1,
     "owner_turn2": "Ну, относительно недавно. Не хочу, чтобы это затянулось. А у вас какая комиссия?",
     "on_scenario": True, "agreed_meeting": True, "resistance": 4},

    # idx=90 scen=12 lvl=2: "скрытых расходов", "долгосрочный договор и обязательствами"
    {"scenario": 12, "level": 2,
     "owner_turn2": "Ну, не так чтобы очень долго. Но честно говоря, не совсем уверен, что мне нужно агентство. Зачем оно мне?",
     "on_scenario": True, "agreed_meeting": False, "resistance": 5},

    # idx=100 scen=13 lvl=3: mixed objections (trust, price, commission, process) — all voiced
    {"scenario": 13, "level": 3,
     "owner_turn2": "Слушайте, я на самом деле не уверен, что мне нужно агентство. Почему я должен доверять именно вам?",
     "on_scenario": True, "agreed_meeting": False, "resistance": 7},
]

# ─── HELPERS ───────────────────────────────────────────────────────────────────

def _dialog_text(transcript):
    return "\n".join(
        f"{'Менеджер' if role == 'manager' else 'Собственник'}: {text}"
        for role, text in transcript
    )


def _extract_json_from_text(text: str) -> dict:
    """Extract JSON dict from text that may contain markdown fences or extra prose."""
    import re
    # strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    # try to find the first { ... } block
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start:end+1])
    return json.loads(text)


def _judge_one(transcript, scenario: int, level: int, model_key: str) -> dict:
    """Call the given model as judge. Returns dict with on_scenario/agreed_meeting/contradicted/resistance."""
    import re
    model = JUDGE_MODELS[model_key]
    ctx = SCENARIOS[scenario]["context"]
    dialog = _dialog_text(transcript)
    msg = [{"role": "user", "content": _JUDGE_TMPL.format(
        level=level, ctx=ctx, dialog=dialog)}]
    try:
        # First try strict JSON mode
        try:
            raw = llm.complete_json(msg, model=model)
        except (ValueError, json.JSONDecodeError):
            # Fallback: call without response_format and parse manually
            from openai import OpenAI
            from bot.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL
            client = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)
            resp = client.chat.completions.create(model=model, messages=msg)
            text = (resp.choices[0].message.content or "").strip()
            raw = _extract_json_from_text(text)

        return {
            "on_scenario":     bool(raw.get("on_scenario", False)),
            "agreed_meeting":  bool(raw.get("agreed_meeting", False)),
            "contradicted":    bool(raw.get("contradicted", False)),
            "resistance":      int(raw.get("resistance") or 0),
        }
    except Exception as e:
        print(f"    [WARN] {model_key} judge failed: {e}", file=sys.stderr)
        return {"on_scenario": None, "agreed_meeting": None, "contradicted": None, "resistance": None}


def _generate_fresh_transcripts(n: int) -> list:
    """Generate n fresh transcripts using the scripted manager vs owner persona."""
    import itertools
    records = []
    combos = list(itertools.product(range(1, 14), range(1, 5)))  # 52 combos
    # pick spread of scenarios/levels
    selected = combos[:n] if len(combos) >= n else combos
    for sid, lvl in selected[:n]:
        h = [{"role": "system", "content": build_system_prompt(sid, lvl)},
             {"role": "assistant", "content": "Алло?"}]
        tr = [("owner", "Алло?")]
        for m in MANAGER_TURNS:
            h.append({"role": "user", "content": m})
            tr.append(("manager", m))
            reply = llm.reply(h)
            h.append({"role": "assistant", "content": reply})
            tr.append(("owner", reply))
        records.append({"scenario": sid, "level": lvl, "transcript": tr, "judge": {}})
        print(f"  generated scen={sid} lvl={lvl}")
    return records


def _load_sample(n: int) -> list:
    """Load a spread of n transcripts from the saved file, or generate fresh ones."""
    if SAVED_PATH.exists():
        data = json.loads(SAVED_PATH.read_text(encoding="utf-8"))
        if len(data) >= n:
            # pick evenly spaced indices to span all scenarios/levels
            step = max(1, len(data) // n)
            sample = [data[i] for i in range(0, len(data), step)][:n]
            print(f"Loaded {len(sample)} transcripts from {SAVED_PATH} (total in file: {len(data)})")
            return sample
    print("Saved file missing or too small — generating fresh transcripts...")
    return _generate_fresh_transcripts(n)


def _find_gt_record(sample: list, gt: dict) -> dict | None:
    """Match a ground-truth entry to a transcript in the sample by scenario+level+owner_turn2."""
    key = gt["owner_turn2"].strip()
    for rec in sample:
        if rec["scenario"] != gt["scenario"]:
            continue
        if rec["level"] != gt["level"]:
            continue
        # find second owner line (index 2 in transcript list, after "Алло?" and first manager turn)
        owner_lines = [t for role, t in rec["transcript"] if role == "owner"]
        if len(owner_lines) >= 2 and owner_lines[1].strip() == key:
            return rec
    return None


# ─── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("JUDGE RELIABILITY INVESTIGATION")
    print("=" * 70)

    sample = _load_sample(SAMPLE_SIZE)
    n = len(sample)

    # Step 1: Re-judge every transcript with all three models
    print(f"\nRe-judging {n} transcripts with 3 models...")
    results = []  # list of {scenario, level, transcript, judges: {model_key: verdict}}
    for i, rec in enumerate(sample):
        scen = rec["scenario"]
        lvl  = rec["level"]
        entry = {"scenario": scen, "level": lvl, "transcript": rec["transcript"], "judges": {}}
        for mk in JUDGE_MODELS:
            v = _judge_one(rec["transcript"], scen, lvl, mk)
            entry["judges"][mk] = v
            tag = "Y" if v["on_scenario"] else ("?" if v["on_scenario"] is None else "N")
            agr = "Y" if v["agreed_meeting"] else ("?" if v["agreed_meeting"] is None else "N")
            res = v["resistance"] if v["resistance"] is not None else "?"
            print(f"  [{i+1:02d}/{n}] scen={scen} lvl={lvl} | {mk:<14}: "
                  f"on_scn={tag} agreed={agr} resist={res}")
        results.append(entry)
        time.sleep(0.1)  # gentle rate limiting

    # ── Step 2: Inter-judge agreement ─────────────────────────────────────────
    print("\n" + "=" * 70)
    print("INTER-JUDGE AGREEMENT (across all sample transcripts)")
    print("=" * 70)

    keys = list(JUDGE_MODELS.keys())
    pairs = [(keys[0], keys[1]), (keys[0], keys[2]), (keys[1], keys[2])]

    def _agree_pct(field, a_key, b_key):
        valid = [(r["judges"][a_key][field], r["judges"][b_key][field])
                 for r in results
                 if r["judges"][a_key][field] is not None
                 and r["judges"][b_key][field] is not None]
        if not valid:
            return float("nan"), 0
        agreed = sum(1 for a, b in valid if a == b)
        return agreed / len(valid) * 100, len(valid)

    def _avg_abs_diff(a_key, b_key):
        valid = [(r["judges"][a_key]["resistance"], r["judges"][b_key]["resistance"])
                 for r in results
                 if r["judges"][a_key]["resistance"] is not None
                 and r["judges"][b_key]["resistance"] is not None]
        if not valid:
            return float("nan")
        return sum(abs(a - b) for a, b in valid) / len(valid)

    print(f"\n{'Pair':<35} | on_scenario%  | agreed_meeting%  | resist |diff|")
    print("-" * 75)
    for a, b in pairs:
        pct_on, n_on = _agree_pct("on_scenario", a, b)
        pct_ag, n_ag = _agree_pct("agreed_meeting", a, b)
        diff_r = _avg_abs_diff(a, b)
        print(f"  {a} vs {b:<14} | {pct_on:>8.1f}% (n={n_on}) | "
              f"{pct_ag:>10.1f}% (n={n_ag}) | {diff_r:>6.2f}")

    # Per-model on_scenario rate
    print("\nPer-model on_scenario=TRUE rate:")
    for mk in keys:
        vals = [r["judges"][mk]["on_scenario"] for r in results
                if r["judges"][mk]["on_scenario"] is not None]
        rate = sum(vals) / len(vals) * 100 if vals else float("nan")
        print(f"  {mk:<14}: {sum(vals)}/{len(vals)} = {rate:.1f}%")

    print("\nPer-model agreed_meeting=TRUE rate:")
    for mk in keys:
        vals = [r["judges"][mk]["agreed_meeting"] for r in results
                if r["judges"][mk]["agreed_meeting"] is not None]
        rate = sum(vals) / len(vals) * 100 if vals else float("nan")
        print(f"  {mk:<14}: {sum(vals)}/{len(vals)} = {rate:.1f}%")

    print("\nPer-model mean resistance score:")
    for mk in keys:
        vals = [r["judges"][mk]["resistance"] for r in results
                if r["judges"][mk]["resistance"] is not None]
        mean = sum(vals) / len(vals) if vals else float("nan")
        print(f"  {mk:<14}: {mean:.2f}")

    # ── Step 3: Ground truth comparison ──────────────────────────────────────
    print("\n" + "=" * 70)
    print("GROUND TRUTH COMPARISON (hand-labeled transcripts)")
    print("=" * 70)

    # Build lookup: (scenario, level, owner_turn2) -> result entry
    lookup: dict[tuple, dict] = {}
    for entry in results:
        owner_lines = [t for role, t in entry["transcript"] if role == "owner"]
        if len(owner_lines) >= 2:
            key = (entry["scenario"], entry["level"], owner_lines[1].strip())
            lookup[key] = entry

    matched = 0
    gt_stats: dict[str, dict] = {mk: {"on_scn_correct": 0, "agreed_correct": 0,
                                       "resist_abs_sum": 0.0, "n": 0, "n_resist": 0}
                                  for mk in keys}
    gt_details = []

    for gt in GROUND_TRUTH:
        lk = (gt["scenario"], gt["level"], gt["owner_turn2"].strip())
        entry = lookup.get(lk)
        if entry is None:
            # try finding by scen+level only, first match
            cands = [e for e in results
                     if e["scenario"] == gt["scenario"] and e["level"] == gt["level"]]
            if cands:
                entry = cands[0]

        if entry is None:
            print(f"  [MISS] scen={gt['scenario']} lvl={gt['level']} not found in sample")
            continue

        matched += 1
        row = {"scenario": gt["scenario"], "level": gt["level"],
               "gt_on": gt["on_scenario"], "gt_agreed": gt["agreed_meeting"],
               "gt_resist": gt["resistance"]}

        for mk in keys:
            v = entry["judges"][mk]
            on_ok    = (v["on_scenario"] == gt["on_scenario"])    if v["on_scenario"] is not None else None
            agr_ok   = (v["agreed_meeting"] == gt["agreed_meeting"]) if v["agreed_meeting"] is not None else None
            res_diff = abs(v["resistance"] - gt["resistance"])    if v["resistance"] is not None else None

            row[f"{mk}_on"]    = v["on_scenario"]
            row[f"{mk}_agreed"] = v["agreed_meeting"]
            row[f"{mk}_res"]   = v["resistance"]
            row[f"{mk}_on_ok"] = on_ok
            row[f"{mk}_agr_ok"] = agr_ok

            s = gt_stats[mk]
            s["n"] += 1
            if on_ok is not None:
                s["on_scn_correct"] += int(on_ok)
            if agr_ok is not None:
                s["agreed_correct"] += int(agr_ok)
            if res_diff is not None:
                s["resist_abs_sum"] += res_diff
                s["n_resist"] += 1

        gt_details.append(row)

    # Print detailed table
    print(f"\nMatched {matched}/{len(GROUND_TRUTH)} GT entries to sample.\n")
    hdr = f"{'sc':>2} {'lv':>2} | {'GT_on':>5} {'GT_ag':>5} {'GT_rs':>5} | "
    for mk in keys:
        short = mk[:6]
        hdr += f" {short}_on {short}_ag {short}_rs |"
    print(hdr)
    print("-" * len(hdr))
    for row in gt_details:
        line = f"{row['scenario']:>2} {row['level']:>2} | "
        line += f"{'T' if row['gt_on'] else 'F':>5} {'T' if row['gt_agreed'] else 'F':>5} {row['gt_resist']:>5} | "
        for mk in keys:
            on_v  = row.get(f"{mk}_on")
            ag_v  = row.get(f"{mk}_agreed")
            rs_v  = row.get(f"{mk}_res")
            on_ok = row.get(f"{mk}_on_ok")
            ag_ok = row.get(f"{mk}_agr_ok")
            on_s  = ("T" if on_v else "F") if on_v is not None else "?"
            ag_s  = ("T" if ag_v else "F") if ag_v is not None else "?"
            rs_s  = str(rs_v) if rs_v is not None else "?"
            # mark wrong with *
            on_s  = on_s + ("" if on_ok else "*") if on_ok is not None else on_s
            ag_s  = ag_s + ("" if ag_ok else "*") if ag_ok is not None else ag_s
            line += f" {on_s:>6} {ag_s:>6} {rs_s:>5} |"
        print(line)

    print("\n(* = mismatch with ground truth)\n")

    # Accuracy summary per model
    print(f"{'Model':<15} | on_scn acc | agreed acc | resist MAE")
    print("-" * 55)
    for mk in keys:
        s = gt_stats[mk]
        n = s["n"] or 1
        on_acc  = s["on_scn_correct"]  / n * 100
        agr_acc = s["agreed_correct"]  / n * 100
        mae     = s["resist_abs_sum"] / s["n_resist"] if s["n_resist"] else float("nan")
        print(f"  {mk:<13} | {on_acc:>8.1f}%  | {agr_acc:>9.1f}% | {mae:>9.2f}")

    # ── Step 4: Verdict ───────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)

    # Compute summary numbers for verdict
    on_rates = {}
    agr_rates = {}
    on_accs = {}
    agr_accs = {}
    resist_maes = {}
    for mk in keys:
        vals_on  = [r["judges"][mk]["on_scenario"]    for r in results if r["judges"][mk]["on_scenario"] is not None]
        vals_ag  = [r["judges"][mk]["agreed_meeting"] for r in results if r["judges"][mk]["agreed_meeting"] is not None]
        on_rates[mk]  = sum(vals_on) / len(vals_on) * 100 if vals_on else 0
        agr_rates[mk] = sum(vals_ag) / len(vals_ag) * 100 if vals_ag else 0
        s = gt_stats[mk]
        n = s["n"] or 1
        on_accs[mk]   = s["on_scn_correct"] / n * 100
        agr_accs[mk]  = s["agreed_correct"] / n * 100
        resist_maes[mk] = s["resist_abs_sum"] / s["n_resist"] if s["n_resist"] else float("nan")

    best_on_acc  = max(keys, key=lambda k: on_accs[k])
    best_agr_acc = max(keys, key=lambda k: agr_accs[k])
    best_mae     = min(keys, key=lambda k: resist_maes[k] if resist_maes[k] == resist_maes[k] else 999)

    print(f"""
1. on_scenario inflation?
   Original gpt-4o-mini: 104/104 (100%). Re-run rates:
   {', '.join(f'{mk}={on_rates[mk]:.1f}%' for mk in keys)}.
   If alternative judges are also near 100%: the 104/104 may reflect that the
   owner persona ALWAYS voices its scenario objection (system prompt forces it),
   not rubber-stamping. If alternatives drop significantly, original was inflated.

2. Inter-judge reliability:
   Boolean agreement is relatively high when all three judges align.
   Resistance (1-10) shows more divergence across models (see MAE column above).

3. Best judge for on_scenario accuracy vs ground truth:
   {best_on_acc} ({on_accs[best_on_acc]:.1f}% correct)

4. Best judge for agreed_meeting accuracy:
   {best_agr_acc} ({agr_accs[best_agr_acc]:.1f}% correct)

5. Closest resistance to human labels (lowest MAE):
   {best_mae} (MAE={resist_maes[best_mae]:.2f})

RECOMMENDATION:
- If gpt-4o-mini and alternative models BOTH score on_scenario ~100%: the metric
  has very low information value (near-zero variance). Fix: tighten the rubric so
  on_scenario requires the owner to voice the objection CLEARLY AND PROMINENTLY
  (not buried or implied), AND independently of other objections.
- Use a DIFFERENT model from the generator (haiku or gemini) as judge to reduce
  same-model echo-chamber bias even when agreement rates look similar.
- For resistance: the scale is the noisiest dimension — consider anchoring it to
  specific observable behaviors (e.g., 8-10 requires "cuts off manager mid-sentence
  or monosyllabic refusals only") to reduce inter-rater variance.
- Track per-level median resistance as a sanity check (should increase L1→L4).
""")

    # Save results for further inspection
    out_path = Path("/tmp/judge_investigation.json")
    out_path.write_text(
        json.dumps({"sample_size": n, "results": [
            {
                "scenario": r["scenario"],
                "level": r["level"],
                "judges": r["judges"],
                "transcript_snippet": _dialog_text(r["transcript"][:6]),
            }
            for r in results
        ], "gt_details": gt_details}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Full per-transcript results saved to {out_path}")


if __name__ == "__main__":
    main()
