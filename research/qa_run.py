"""Автоматичний QA: проганяє кожен рівень N повних розмов і ловить проблеми.

Менеджер — скриптований (однаковий тиск у кожному прогоні). Власник — llama.
Запуск: .venv/bin/python -m tests.qa_run
"""
import json
import re
import sys
import time

from bot import llm
from bot.persona import build_system_prompt, SCENARIOS, LEVELS

N_DIALOGS = 10  # розмов на рівень

# Скриптований менеджер: ескалація від контакту до закриття.
MANAGER_TURNS = [
    "Здравствуйте! Меня зовут Андрей, агентство «ДомПро». Видел ваше объявление о продаже квартиры — удобно пару минут поговорить?",
    "Понимаю. Скажите, вы уже давно продаёте? Часто собственники месяцами не могут найти покупателя сами.",
    "У нас большая база проверенных покупателей, и комиссию мы берём только по факту сделки — никаких предоплат.",
    "А что именно вас смущает в работе с агентством? Многие сначала сомневаются, а потом экономят кучу времени.",
    "Давайте я бесплатно приеду, оценю квартиру и покажу план продажи. Ни к чему не обязывает. Когда удобно — завтра или в выходные?",
    "Хорошо, оставлю свой номер — если надумаете, наберите. Спасибо, что уделили время!",
]

# --- детектори проблем ---
CJK = re.compile(r"[　-〿㐀-䶿一-鿿＀-￯]")
LATIN = re.compile(r"[A-Za-z]{2,}")  # латинські слова (англ. протікання)
ROLEBREAK = re.compile(r"(искусственн|нейросет|языков\w+ модел|chatgpt|\bии\b|я\s+бот|ассистент|as an ai)", re.I)
GREET = re.compile(r"(здравствуй|добрый день|добрый вечер|алло|приветствую)", re.I)
AGREE = re.compile(r"(давайте встрет|можно встрет|приезжайте|приходите|договорились|давайте завтра|давайте в выход|хорошо, приезж|согласен на встреч|давайте посмотр|жду вас)", re.I)


def run_dialog(level: int) -> dict:
    """Одна повна розмова. Повертає транскрипт + прапори проблем."""
    history = [
        {"role": "system", "content": build_system_prompt(1, level)},
        {"role": "assistant", "content": "Алло?"},
    ]
    transcript = [("owner", "Алло?")]
    flags = {"cjk": 0, "latin": 0, "rolebreak": 0, "regreet": 0, "empty": 0, "toolong": 0}
    agreed = False

    for i, m in enumerate(MANAGER_TURNS):
        history.append({"role": "user", "content": m})
        transcript.append(("manager", m))
        reply = llm.reply(history)
        history.append({"role": "assistant", "content": reply})
        transcript.append(("owner", reply))

        if CJK.search(reply):
            flags["cjk"] += 1
        if LATIN.search(reply):
            flags["latin"] += 1
        if ROLEBREAK.search(reply):
            flags["rolebreak"] += 1
        if i > 0 and GREET.search(reply):  # вітання після першого ходу
            flags["regreet"] += 1
        if not reply.strip():
            flags["empty"] += 1
        if len(reply) > 400:
            flags["toolong"] += 1
        if AGREE.search(reply):
            agreed = True

    return {"level": level, "agreed": agreed, "flags": flags, "transcript": transcript}


def main():
    print(f"QA: модель={llm.LLM_MODEL}, сценарій='{SCENARIOS[1]['name']}', {N_DIALOGS} розмов/рівень")
    all_results = []
    t0 = time.time()
    for level in (1, 2, 3, 4):
        agg = {"cjk": 0, "latin": 0, "rolebreak": 0, "regreet": 0, "empty": 0, "toolong": 0}
        agreed_count = 0
        for d in range(N_DIALOGS):
            r = run_dialog(level)
            all_results.append(r)
            for k in agg:
                agg[k] += r["flags"][k]
            agreed_count += int(r["agreed"])
            print(f"  рів{level} розмова {d+1}/{N_DIALOGS}: "
                  f"{'ЗГОДА' if r['agreed'] else 'без зустрічі'} "
                  f"{ {k:v for k,v in r['flags'].items() if v} or '' }")
        print(f"== РІВЕНЬ {level} ({LEVELS[level]['name']}): "
              f"згод на зустріч {agreed_count}/{N_DIALOGS} | проблеми {agg}\n")

    with open("/tmp/qa_results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"Готово за {time.time()-t0:.0f}с. Повні транскрипти -> /tmp/qa_results.json")


if __name__ == "__main__":
    sys.exit(main())
