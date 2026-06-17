"""Поведінкова QA всіх 13 сценаріїв на бойовій моделі (gpt-4o-mini через OpenRouter).

Для кожного сценарію × рівня: діалог (скриптований менеджер + власник) -> суддя.
Головне питання: чи власник озвучує ЗАПЕРЕЧЕННЯ СВОГО сценарію (on_scenario),
плюс градієнт згоди, суперечності, чужі символи, вихід з ролі.
Запуск: .venv/bin/python -m tests.qa_scenarios
"""
import json
import re
import time

from bot import llm
from bot.persona import build_system_prompt, SCENARIOS
from research.qa_run import MANAGER_TURNS

JUDGE = "openai/gpt-4o-mini"
REPS_PER_LEVEL = 2   # прогонів на (сценарій, рівень) — більша вибірка, менше шуму
_FOREIGN = re.compile(r"[　-〿㐀-䶿一-鿿＀-￯]|[A-Za-z]{2,}")

_JUDGE = (
    "Стенограмма тренировочного звонка: менеджер агентства недвижимости звонит "
    "собственнику (его играет бот). Уровень сложности {level} (1=лёгкий,4=очень сложный).\n"
    "СИТУАЦИЯ/ОЖИДАЕМОЕ ВОЗРАЖЕНИЕ СОБСТВЕННИКА: {ctx}\n\n"
    "Оцени ПОВЕДЕНИЕ СОБСТВЕННИКА. Ответь СТРОГО JSON: "
    "{{\"on_scenario\":bool,\"agreed_meeting\":bool,\"contradicted\":bool,"
    "\"broke_character\":bool,\"resistance\":int,\"objections_raised\":int}}. "
    "on_scenario — собственник реально озвучивал возражение, соответствующее его ситуации выше. "
    "agreed_meeting — согласился на встречу/оценку. contradicted — противоречил себе. "
    "broke_character — признал, что он ИИ/вышел из роли. "
    "objections_raised — сколько РАЗНЫХ возражений/сомнений озвучил собственник за разговор (число). "
    "resistance — насколько собственник был холоден и сопротивлялся, по шкале 1-10: "
    "1-2=тёплый, открытый, легко идёт на контакт; 3-4=спокойный, но осторожный, мягкие "
    "сомнения; 5-7=недоверчивый скептик, вникает, давит, много возражений; "
    "8-10=холодный, отмахивается, не вникает, обрывает разговор.\n\nСТЕНОГРАММА:\n{dialog}"
)


def _dialog(scenario, level):
    h = [{"role": "system", "content": build_system_prompt(scenario, level)},
         {"role": "assistant", "content": "Алло?"}]
    tr = [("owner", "Алло?")]
    foreign = 0
    for m in MANAGER_TURNS:
        h.append({"role": "user", "content": m}); tr.append(("manager", m))
        txt = llm.reply(h)
        if _FOREIGN.search(txt):
            foreign += 1
        h.append({"role": "assistant", "content": txt}); tr.append(("owner", txt))
    return tr, foreign


def _judge(tr, scenario, level):
    dialog = "\n".join(f"{'Менеджер' if w == 'manager' else 'Собственник'}: {x}" for w, x in tr)
    return llm.complete_json([{"role": "user", "content": _JUDGE.format(
        level=level, ctx=SCENARIOS[scenario]["context"], dialog=dialog)}], model=JUDGE)


def _num(v, key):
    try:
        return int(v.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def main():
    t0 = time.time()
    per = 4 * REPS_PER_LEVEL                       # вимірів на сценарій
    denom = len(SCENARIOS) * REPS_PER_LEVEL        # вимірів на рівень
    grad = {1: 0, 2: 0, 3: 0, 4: 0}
    resist = {1: 0, 2: 0, 3: 0, 4: 0}              # сума спротиву (1-10) по рівнях
    obj = {1: 0, 2: 0, 3: 0, 4: 0}                 # сума к-сті заперечень по рівнях
    tot_onscn = tot_contra = tot_broke = tot_foreign = n = 0
    saved = []
    print(f"{'сц':>3} {'сценарій':32} {'on-scn':>7} {'супер':>6} {'чужі':>5}")
    for sid in SCENARIOS:
        onscn = contra = broke = foreign = 0
        for level in (1, 2, 3, 4):
            for _ in range(REPS_PER_LEVEL):
                tr, fr = _dialog(sid, level)
                v = _judge(tr, sid, level)
                n += 1; foreign += fr; tot_foreign += fr
                onscn += int(bool(v.get("on_scenario"))); tot_onscn += int(bool(v.get("on_scenario")))
                contra += int(bool(v.get("contradicted"))); tot_contra += int(bool(v.get("contradicted")))
                broke += int(bool(v.get("broke_character"))); tot_broke += int(bool(v.get("broke_character")))
                grad[level] += int(bool(v.get("agreed_meeting")))
                resist[level] += _num(v, "resistance")
                obj[level] += _num(v, "objections_raised")
                saved.append({"scenario": sid, "level": level, "transcript": tr, "judge": v})
        name = SCENARIOS[sid]["name"][:31]
        print(f"{sid:>3} {name:32} {onscn:>5}/{per} {contra:>4}/{per} {foreign:>4}")

    print(f"\nЗгода по рівнях (з {denom}): "
          + " ".join(f"L{l}={grad[l]}" for l in (1, 2, 3, 4)))
    print("Сер. СПРОТИВ (1-10, має зростати): "
          + " ".join(f"L{l}={resist[l]/denom:.1f}" for l in (1, 2, 3, 4)))
    print("Сер. К-СТЬ ЗАПЕРЕЧЕНЬ (нова вісь, має зростати): "
          + " ".join(f"L{l}={obj[l]/denom:.1f}" for l in (1, 2, 3, 4)))
    print(f"on-scenario: {tot_onscn}/{n} | суперечності: {tot_contra}/{n} | "
          f"вихід з ролі: {tot_broke}/{n} | чужі символи: {tot_foreign}")
    print(f"Готово за {time.time()-t0:.0f}с")
    json.dump(saved, open("/tmp/qa_scenarios.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
