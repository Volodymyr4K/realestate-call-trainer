"""Чи тримається градієнт рівнів проти АДАПТИВНОГО менеджера (не скрипта)?

Менеджер — окремий gpt-4o-mini, що веде живий діалог і відпрацьовує заперечення.
Порівнюємо згоду+спротив по рівнях зі скриптованим базлайном (88/12/0/0; 4.6/6.2/6.7/7.9).
Запуск: .venv/bin/python -m tests.investigate_manager2
"""
import time

from bot import llm
from bot.persona import build_system_prompt

MODEL = "openai/gpt-4o-mini"
SCN = [1, 3, 9]
REPS = 2
MAX_EXCHANGES = 6

MGR_PROMPT = (
    "Ты — опытный менеджер агентства недвижимости «ДомПро». Ты звонишь собственнику по "
    "его объявлению о продаже квартиры. Цель — договориться о личной встрече (бесплатная "
    "оценка, без обязательств). Веди живой телефонный разговор: коротко и естественно, "
    "ОТРАБАТЫВАЙ возражения собственника аргументами, не сдавайся после первого отказа, "
    "но не будь навязчивым. Когда уместно — конкретно предложи встречу. Только реплики, "
    "по-русски, без ремарок в скобках."
)

_JUDGE = (
    "Стенограмма звонка: менеджер агентства звонит собственнику. Уровень сложности {lvl} "
    "(1=лёгкий,4=очень сложный). Ответь СТРОГО JSON: "
    "{{\"agreed_meeting\":bool,\"resistance\":int}}. agreed_meeting — собственник дал ЧЁТКОЕ "
    "согласие на встречу (не «подумаю»). resistance — холодность/сопротивление 1-10.\n\n{d}"
)


def _view(transcript, me):
    return [{"role": "assistant" if who == me else "user", "content": t}
            for who, t in transcript]


def _dialog(scenario, level):
    owner_sys = build_system_prompt(scenario, level)
    transcript = [("owner", "Алло?")]
    for _ in range(MAX_EXCHANGES):
        mgr = llm.reply([{"role": "system", "content": MGR_PROMPT}] + _view(transcript, "manager"),
                        model=MODEL)
        transcript.append(("manager", mgr))
        own = llm.reply([{"role": "system", "content": owner_sys}] + _view(transcript, "owner"),
                        model=MODEL)
        transcript.append(("owner", own))
    return transcript


def _judge(transcript, level):
    d = "\n".join(f"{'Менеджер' if w == 'manager' else 'Собственник'}: {t}" for w, t in transcript)
    return llm.complete_json([{"role": "user", "content": _JUDGE.format(lvl=level, d=d)}], model=MODEL)


def main():
    t0 = time.time()
    agree = {1: 0, 2: 0, 3: 0, 4: 0}
    resist = {1: 0, 2: 0, 3: 0, 4: 0}
    denom = len(SCN) * REPS
    for level in (1, 2, 3, 4):
        for scen in SCN:
            for _ in range(REPS):
                tr = _dialog(scen, level)
                v = _judge(tr, level)
                agree[level] += int(bool(v.get("agreed_meeting")))
                try:
                    resist[level] += int(v.get("resistance") or 0)
                except (TypeError, ValueError):
                    pass
        print(f"L{level}: згода {agree[level]}/{denom} | спротив {resist[level]/denom:.1f}", flush=True)
    print("\n=== АДАПТИВНИЙ менеджер ===")
    print("Згода %:   " + " ".join(f"L{l}={100*agree[l]//denom}%" for l in (1, 2, 3, 4)))
    print("Спротив:   " + " ".join(f"L{l}={resist[l]/denom:.1f}" for l in (1, 2, 3, 4)))
    print("Базлайн (скрипт): згода 88/12/0/0% ; спротив 4.6/6.2/6.7/7.9")
    print(f"Готово за {time.time()-t0:.0f}с")


if __name__ == "__main__":
    main()
