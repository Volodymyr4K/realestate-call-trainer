"""Порівняння моделей OpenRouter: якість × вартість.

Діалог жене кандидат, оцінює один фіксований суддя (чесно). Міряємо суперечності,
градієнт згоди по рівнях, тон, чужі символи + реальні токени → орієнтовна вартість.
Запуск: .venv/bin/python -m tests.compare_models
"""
import json
import re
import time

from bot import llm
from bot.persona import build_system_prompt, SCENARIOS
from research.qa_run import MANAGER_TURNS

# модель -> (ціна вхід, ціна вихід) за 1M токенів
CANDIDATES = {
    "openai/gpt-4o-mini":                          (0.15, 0.60),
    "anthropic/claude-haiku-4.5":                  (1.00, 5.00),
    "anthropic/claude-3-haiku":                    (0.25, 1.25),
    "deepseek/deepseek-chat":                      (0.20, 0.80),
    "mistralai/mistral-small-3.2-24b-instruct":    (0.07, 0.20),
    "google/gemini-2.5-flash":                     (0.30, 2.50),
}
JUDGE = "openai/gpt-4o-mini"           # один суддя для всіх
SCENARIOS_USED = [1, 3, 6, 9, 12]      # різні типи заперечень
REPS_PER_LEVEL = 4                     # 4 діалоги на рівень -> 16 на модель

_FOREIGN = re.compile(r"[　-〿㐀-䶿一-鿿＀-￯]|[A-Za-z]{2,}")

_JUDGE_PROMPT = (
    "Стенограмма тренировочного звонка: менеджер агентства недвижимости звонит "
    "собственнику (его играет бот). Уровень сложности {level} (1=лёгкий,4=очень сложный). "
    "Ситуация: {ctx}\nОцени ПОВЕДЕНИЕ СОБСТВЕННИКА. Ответь СТРОГО JSON: "
    "{{\"agreed_meeting\":bool,\"contradicted\":bool,\"broke_character\":bool,\"tone_ok\":bool}}. "
    "agreed_meeting — согласился на встречу/оценку. contradicted — противоречил сам себе. "
    "broke_character — признал, что он ИИ/вышел из роли. tone_ok — тон соответствует уровню.\n\n"
    "СТЕНОГРАММА:\n{dialog}"
)


def _gen(model, history):
    r = llm._get_client().chat.completions.create(model=model, messages=history)
    txt = (r.choices[0].message.content or "").strip()
    return txt, r.usage.prompt_tokens, r.usage.completion_tokens


def _run_dialog(model, scenario, level):
    h = [{"role": "system", "content": build_system_prompt(scenario, level)},
         {"role": "assistant", "content": "Алло?"}]
    tr = [("owner", "Алло?")]
    intok = outok = foreign = 0
    for m in MANAGER_TURNS:
        h.append({"role": "user", "content": m}); tr.append(("manager", m))
        txt, pt, ct = _gen(model, h)
        intok += pt; outok += ct
        if _FOREIGN.search(txt):
            foreign += 1
        h.append({"role": "assistant", "content": txt}); tr.append(("owner", txt))
    return tr, intok, outok, foreign


def _judge(transcript, level, scenario):
    dialog = "\n".join(f"{'Менеджер' if w == 'manager' else 'Собственник'}: {x}"
                       for w, x in transcript)
    return llm.complete_json([{"role": "user", "content": _JUDGE_PROMPT.format(
        level=level, ctx=SCENARIOS[scenario]["context"], dialog=dialog)}], model=JUDGE)


def main():
    results = {}
    for model, (pin, pout) in CANDIDATES.items():
        t0 = time.time()
        agree = {1: 0, 2: 0, 3: 0, 4: 0}
        contra = tone = broke = foreign = intok = outok = n = 0
        transcripts = []
        for level in (1, 2, 3, 4):
            for rep in range(REPS_PER_LEVEL):
                scen = SCENARIOS_USED[(level + rep) % len(SCENARIOS_USED)]
                tr, it, ot, fr = _run_dialog(model, scen, level)
                v = _judge(tr, level, scen)
                n += 1; intok += it; outok += ot; foreign += fr
                agree[level] += int(bool(v.get("agreed_meeting")))
                contra += int(bool(v.get("contradicted")))
                tone += int(bool(v.get("tone_ok")))
                broke += int(bool(v.get("broke_character")))
                transcripts.append({"scenario": scen, "level": level, "transcript": tr})
        cost = (intok * pin + outok * pout) / 1e6
        results[model] = {
            "agree": agree, "contra": contra, "tone": tone, "broke": broke,
            "foreign": foreign, "n": n, "cost_total": cost, "cost_per": cost / n,
            "tok_per": (intok + outok) / n, "secs": time.time() - t0,
        }
        safe = model.replace("/", "_")
        json.dump(transcripts, open(f"/tmp/cmp_{safe}.json", "w"), ensure_ascii=False, indent=1)
        r = results[model]
        print(f"[{model}] згода {r['agree']} | суперечн {contra}/{n} | тон {tone}/{n} | "
              f"роль {broke}/{n} | чужі {foreign} | ${r['cost_per']*1000:.3f}/1000 розмов")
    print("\n=== ПІДСУМОК (відсортовано: менше суперечностей -> дешевше) ===")
    rank = sorted(results.items(), key=lambda kv: (kv[1]["contra"], kv[1]["cost_per"]))
    print(f"{'модель':38} {'сперечн':>8} {'тон':>6} {'чужі':>6} {'$/1000розм':>11}")
    for model, r in rank:
        print(f"{model:38} {r['contra']:>4}/{r['n']:<3} {r['tone']:>3}/{r['n']:<2} "
              f"{r['foreign']:>5} {r['cost_per']*1000:>10.3f}")
    json.dump({m: {k: v for k, v in r.items()} for m, r in results.items()},
              open("/tmp/cmp_summary.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
