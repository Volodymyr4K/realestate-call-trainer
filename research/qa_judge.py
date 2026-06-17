"""LLM-суддя над збереженими транскриптами QA: чесні цифри замість регексу.

Для кожної розмови питає модель (JSON): погодився на зустріч? суперечив собі?
вийшов з ролі? тон відповідає рівню? Запуск: .venv/bin/python -m tests.qa_judge
"""
import json
import ollama
from bot.config import LLM_MODEL

data = json.load(open("/tmp/qa_results.json"))

JUDGE = (
    "Ниже стенограмма тренировочного звонка: менеджер агентства недвижимости звонит "
    "собственнику (его играет бот). Оцени ПОВЕДЕНИЕ СОБСТВЕННИКА. Ответь СТРОГО JSON "
    "без пояснений: {{\"agreed_meeting\": bool, \"contradicted\": bool, "
    "\"broke_character\": bool, \"tone_ok_for_level\": bool}}.\n"
    "agreed_meeting — согласился ли собственник на встречу/бесплатную оценку.\n"
    "contradicted — противоречил ли сам себе (согласился, потом отказался, и наоборот).\n"
    "broke_character — признал ли, что он ИИ/бот, или вышел из роли.\n"
    "tone_ok_for_level — соответствует ли тон уровню (1=тёплый дружелюбный, "
    "2=вежливо-осторожный, 3=прохладный скептик, 4=холодный раздражённый отказ).\n\n"
    "УРОВЕНЬ СЛОЖНОСТИ: {level}\nСТЕНОГРАММА:\n{text}"
)


def judge(rec) -> dict:
    text = "\n".join(f"{'Менеджер' if w=='manager' else 'Собственник'}: {t}"
                     for w, t in rec["transcript"])
    resp = ollama.chat(
        model=LLM_MODEL, format="json", keep_alive="10m",
        messages=[{"role": "user", "content": JUDGE.format(level=rec["level"], text=text)}],
    )
    try:
        return json.loads(resp["message"]["content"])
    except Exception:
        return {}


for lvl in (1, 2, 3, 4):
    rows = [r for r in data if r["level"] == lvl]
    agg = {"agreed_meeting": 0, "contradicted": 0, "broke_character": 0, "tone_ok_for_level": 0}
    for r in rows:
        v = judge(r)
        for k in agg:
            agg[k] += int(bool(v.get(k)))
    print(f"рів{lvl}: згода {agg['agreed_meeting']}/10 | "
          f"тон ОК {agg['tone_ok_for_level']}/10 | "
          f"суперечності {agg['contradicted']}/10 | вихід з ролі {agg['broke_character']}/10")
