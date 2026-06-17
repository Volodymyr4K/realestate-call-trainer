"""Чи тримається персона на ДОВГІЙ розмові (18 ходів): повтори, нитка, роль, деградація.

Адаптивний менеджер ↔ персона. Авто-перевірка: повтори (Жаккар), чужі символи + суддя.
Запуск: .venv/bin/python -m tests.investigate_longconv
"""
import json
import re
import time

from bot import llm
from bot.persona import build_system_prompt, SCENARIOS

MODEL = "openai/gpt-4o-mini"
EXCHANGES = 18
COMBOS = [(1, 3), (9, 4), (6, 2)]
_FOREIGN = re.compile(r"[　-〿㐀-䶿一-鿿＀-￯]|[A-Za-z]{2,}")

MGR = ("Ты — менеджер агентства недвижимости, звонишь собственнику по объявлению о "
       "продаже квартиры. Цель — встреча (бесплатная оценка). Веди живой разговор, "
       "ПРОБУЙ РАЗНЫЕ аргументы и подходы, не повторяйся, отрабатывай возражения. "
       "Только реплики, по-русски, без ремарок.")

_JUDGE = ("Длинная стенограмма звонка менеджера собственнику (уровень {lvl}). Оцени "
          "ПОВЕДЕНИЕ СОБСТВЕННИКА за весь разговор. JSON: {{\"in_character\":bool,"
          "\"contradicted\":bool,\"repetitive\":bool,\"stayed_on_scenario\":bool,"
          "\"coherent_at_end\":bool,\"note\":\"кратко\"}}. repetitive — повторял ли одни и те же "
          "фразы. coherent_at_end — связны ли последние реплики.\n\n{d}")


def _view(tr, me):
    return [{"role": "assistant" if w == me else "user", "content": t} for w, t in tr]


def _jaccard(a, b):
    sa, sb = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0


def main():
    t0 = time.time()
    saved = []
    for sc, lv in COMBOS:
        owner_sys = build_system_prompt(sc, lv)
        tr = [("owner", "Алло?")]
        for _ in range(EXCHANGES):
            mgr = llm.reply([{"role": "system", "content": MGR}] + _view(tr, "manager"), model=MODEL)
            tr.append(("manager", mgr))
            own = llm.reply([{"role": "system", "content": owner_sys}] + _view(tr, "owner"), model=MODEL)
            tr.append(("owner", own))
        owner_turns = [t for w, t in tr if w == "owner"][1:]   # без "Алло?"
        # повтори: макс. схожість будь-якої пари + к-сть пар > 0.6
        pairs = [(i, j) for i in range(len(owner_turns)) for j in range(i + 1, len(owner_turns))]
        sims = [_jaccard(owner_turns[i], owner_turns[j]) for i, j in pairs]
        near = sum(1 for s in sims if s > 0.6)
        foreign = sum(1 for t in owner_turns if _FOREIGN.search(t))
        d = "\n".join(f"{'М' if w == 'manager' else 'С'}: {t}" for w, t in tr)
        v = llm.complete_json([{"role": "user", "content": _JUDGE.format(lvl=lv, d=d)}], model=MODEL)
        saved.append({"scenario": sc, "level": lv, "transcript": tr, "judge": v})
        print(f"сц{sc}L{lv} ({len(owner_turns)} реплік власника): "
              f"макс.повтор={max(sims):.2f} пар>0.6={near} чужі={foreign} | "
              f"роль={v.get('in_character')} суперечн={v.get('contradicted')} "
              f"повтори={v.get('repetitive')} на_сценарії={v.get('stayed_on_scenario')} "
              f"звʼязно_вкінці={v.get('coherent_at_end')}", flush=True)
        print(f"   суддя: {v.get('note')}", flush=True)
    json.dump(saved, open("/tmp/longconv.json", "w"), ensure_ascii=False, indent=1)
    print(f"Готово за {time.time()-t0:.0f}с")


if __name__ == "__main__":
    main()
