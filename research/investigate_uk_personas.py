"""Investigation script: (A) Ukrainian-language behavior, (B) single vs multi-objection personas.

Run: .venv/bin/python -m tests.investigate_uk_personas
"""
import re
import sys
import textwrap

from bot import llm
from bot.persona import build_system_prompt, SCENARIOS, LEVELS

# ---------------------------------------------------------------------------
# Ukrainian manager script (equivalent of MANAGER_TURNS but in Ukrainian)
# ---------------------------------------------------------------------------
MANAGER_TURNS_UK = [
    "Добрий день! Мене звати Андрій, агентство «ДомПро». Бачив ваше оголошення про продаж квартири — зручно поговорити пару хвилин?",
    "Розумію. Скажіть, ви вже давно продаєте? Часто власники місяцями не можуть знайти покупця самостійно.",
    "У нас велика база перевірених покупців, і комісію ми беремо лише за фактом угоди — ніяких передоплат.",
    "А що саме вас бентежить у роботі з агентством? Багато хто спочатку сумнівається, а потім економить купу часу.",
    "Давайте я безкоштовно приїду, оціню квартиру і покажу план продажу. Ні до чого не зобов'язує. Коли зручно — завтра чи у вихідні?",
    "Добре, залишу свій номер — якщо надумаєте, телефонуйте. Дякую, що приділили час!",
]

# Russian manager script (from qa_run.py) for part B
MANAGER_TURNS_RU = [
    "Здравствуйте! Меня зовут Андрей, агентство «ДомПро». Видел ваше объявление о продаже квартиры — удобно пару минут поговорить?",
    "Понимаю. Скажите, вы уже давно продаёте? Часто собственники месяцами не могут найти покупателя сами.",
    "У нас большая база проверенных покупателей, и комиссию мы берём только по факту сделки — никаких предоплат.",
    "А что именно вас смущает в работе с агентством? Многие сначала сомневаются, а потом экономят кучу времени.",
    "Давайте я бесплатно приеду, оценю квартиру и покажу план продажи. Ни к чему не обязывает. Когда удобно — завтра или в выходные?",
    "Хорошо, оставлю свой номер — если надумаете, наберите. Спасибо, что уделили время!",
]

# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------
# Distinctly Russian words that should NOT appear in Ukrainian replies
RUSSIAN_WORDS = re.compile(
    r"\b(что|нет|да|сейчас|хорошо|спасибо|конечно|просто|очень|тоже|ещё|есть|был|было|"
    r"вас|нам|нас|меня|мне|тебе|тебя|ваши|наши|могу|будет|буду|этот|это|для|как|так|"
    r"уже|только|если|когда|потому|чтобы|вот|ну|давайте|говорит|сказал|скажите|"
    r"понимаю|хочу|хотите|думаю|думаете|знаю|знаете|можете|могут|пожалуйста|"
    r"агентства|агентство|недвижимость|комиссия|покупатели|встреча)\b",
    re.I,
)
# Distinctly Ukrainian words confirming Ukrainian output
UKRAINIAN_WORDS = re.compile(
    r"\b(що|ні|так|зараз|добре|дякую|звичайно|просто|дуже|теж|ще|є|був|було|"
    r"вас|нам|нас|мене|мені|тобі|тебе|ваші|наші|можу|буде|буду|цей|це|для|як|так|"
    r"вже|тільки|якщо|коли|тому|щоб|ось|ну|давайте|каже|сказав|скажіть|"
    r"розумію|хочу|хочете|думаю|думаєте|знаю|знаєте|можете|можуть|будь ласка|"
    r"агентства|агентство|нерухомість|комісія|покупці|зустріч)\b",
    re.I,
)

AGREE = re.compile(
    r"(давайте (зустрін|приїд|поговор|подивим)|можна зустрін|приїжд|"
    r"домовились|давайте завтра|давайте у вихідн|добре, приїжд|згоден на зустріч|"
    r"жду вас|давайте встрет|можно встрет|приезжайте|приходите|договорились|"
    r"согласен на встреч)",
    re.I,
)


def run_dialog(system_prompt: str, manager_turns: list[str], opening: str = "Алло?") -> list[tuple[str, str]]:
    """Run a full scripted dialog, return list of (role, text) turns."""
    history = [
        {"role": "system", "content": system_prompt},
        {"role": "assistant", "content": opening},
    ]
    transcript = [("owner", opening)]
    for manager_text in manager_turns:
        history.append({"role": "user", "content": manager_text})
        reply = llm.reply(history)
        history.append({"role": "assistant", "content": reply})
        transcript.append(("manager", manager_text))
        transcript.append(("owner", reply))
    return transcript


def print_transcript(transcript: list[tuple[str, str]], label: str = ""):
    print(f"\n{'='*70}")
    if label:
        print(f"  {label}")
    print('='*70)
    for role, text in transcript:
        prefix = "MGR: " if role == "manager" else "OWN: "
        wrapped = textwrap.fill(text, width=80, subsequent_indent="      ")
        print(f"{prefix}{wrapped}")


def assess_language(transcript: list[tuple[str, str]]) -> dict:
    """Count Russian-leak and Ukrainian-marker hits in owner turns only."""
    owner_replies = [t for r, t in transcript if r == "owner" and t != "Алло?"]
    total_chars = sum(len(r) for r in owner_replies)
    ru_hits = sum(len(RUSSIAN_WORDS.findall(r)) for r in owner_replies)
    uk_hits = sum(len(UKRAINIAN_WORDS.findall(r)) for r in owner_replies)
    agreed = any(AGREE.search(t) for r, t in transcript if r == "owner")
    return {
        "owner_replies": owner_replies,
        "ru_hits": ru_hits,
        "uk_hits": uk_hits,
        "total_chars": total_chars,
        "agreed": agreed,
    }


# ---------------------------------------------------------------------------
# PART A: Ukrainian language test
# ---------------------------------------------------------------------------
def part_a():
    print("\n" + "#"*70)
    print("# PART A: Ukrainian language behavior")
    print("#"*70)

    # Test 4 scenarios × 2 levels
    scenarios = [1, 2, 3, 4]
    levels = [1, 4]

    results = []
    for scenario_id in scenarios:
        for level in levels:
            label = f"Scenario {scenario_id} ({SCENARIOS[scenario_id]['name']}) | Level {level} ({LEVELS[level]['name']}) | UK"
            print(f"\n--- Running: {label} ---")
            sys_prompt = build_system_prompt(scenario_id, level, lang="uk")
            transcript = run_dialog(sys_prompt, MANAGER_TURNS_UK, opening="Алло?")
            assessment = assess_language(transcript)
            results.append({
                "label": label,
                "transcript": transcript,
                "assessment": assessment,
                "scenario_id": scenario_id,
                "level": level,
            })
            print_transcript(transcript, label)
            print(f"\n  >> UK word hits: {assessment['uk_hits']} | RU leak hits: {assessment['ru_hits']} | Agreed: {assessment['agreed']}")

    # Summary
    print("\n" + "="*70)
    print("PART A SUMMARY")
    print("="*70)
    for r in results:
        a = r["assessment"]
        uk = a["uk_hits"]
        ru = a["ru_hits"]
        flag = "LEAK?" if ru > 3 else "OK"
        agreed = "AGREED" if a["agreed"] else "no-agree"
        print(f"  {r['label'][:60]:<60} | uk={uk:3d} ru={ru:3d} {flag} | {agreed}")

    return results


# ---------------------------------------------------------------------------
# PART B: Single-objection vs multi-objection personas
# ---------------------------------------------------------------------------

# Experimental multi-objection system prompt builder
_BASE_SITUATION = (
    "Ты — собственник квартиры, продаёшь её. Тебе звонит риелтор из "
    "агентства недвижимости по твоему объявлению. "
)

_BASE_RULES_RU = """КАК ГОВОРИТЬ (это самое важное — звучи как живой человек по телефону):
- Очень коротко. Обычно ОДНО предложение, иногда два. Часто — пара слов.
- Живая разговорная речь, а НЕ письменная. Используй частицы и слова-связки: «ну»,
  «слушайте», «честно говоря», «вот», «смотрите», «да как сказать».
- ЗАПРЕЩЕНО звучать как ассистент/бот: никаких списков, длинных гладких объяснений.
- Отвечай КОНКРЕТНО на то, что сказал собеседник.
- Пиши ТОЛЬКО свою реплику. НИКАКИХ ремарок в скобках.

ПРАВИЛА РОЛИ:
- Никогда не выходи из роли.
- Не клади трубку после первого «нет».
- Соглашайся на встречу ТОЛЬКО если менеджер реально снял твои возражения.
- Ты МУЖЧИНА. Говори о себе в мужском роде.
- Будь ПОСЛЕДОВАТЕЛЕН, не противоречь себе.
- Отвечай ТОЛЬКО на русском языке и ТОЛЬКО кириллицей."""


def build_multi_objection_prompt(scenario_id: int, level: int) -> str:
    """
    Experimental prompt: owner blends 2-3 real-estate objections naturally,
    while keeping the primary scenario objection as the dominant one.
    """
    scenario = SCENARIOS[scenario_id]
    lvl = LEVELS[level]

    # Secondary objections to blend in (different for each primary scenario to avoid redundancy)
    secondary_objections = {
        1: "Помимо главного сомнения, ты также беспокоишься о КОМИССИИ (кажется завышенной) и о том, что агент будет НАВЯЗЫВАТЬ сделку.",
        2: "Помимо главного сомнения, у тебя ещё есть опасение, что агентство ЗАМЕДЛИТ продажу лишней бюрократией, а также что КОМИССИЯ съест часть выручки.",
        3: "Помимо главного сомнения о комиссии, ты также сомневаешься, есть ли у агентства РЕАЛЬНЫЕ покупатели (а не просто обещания), и беспокоишься о СКРЫТЫХ договорных обязательствах.",
        4: "Помимо прошлого плохого опыта, ты ещё не понимаешь, чем КОНКРЕТНО агент поможет (объявление и сам выложишь), и сомневаешься — может, лучше ПОДОЖДАТЬ более высокой цены.",
    }

    secondary = secondary_objections.get(scenario_id, "")

    return (
        f"{scenario['context']}\n\n"
        f"УРОВЕНЬ СЛОЖНОСТИ — {lvl['name']}: {lvl['behavior']}\n\n"
        f"ДОПОЛНИТЕЛЬНЫЕ ВОЗРАЖЕНИЯ (добавляй их ОРГАНИЧНО по ходу разговора, "
        f"не все сразу, а когда тема всплывает или после первого возражения снято): "
        f"{secondary}\n\n"
        f"{_BASE_RULES_RU}"
    )


def part_b():
    print("\n" + "#"*70)
    print("# PART B: Single-objection vs Multi-objection personas")
    print("#"*70)

    # Test 2 scenarios, level 2 (medium — interesting middle ground)
    scenarios = [1, 2]
    level = 2

    all_results = []

    for scenario_id in scenarios:
        scenario_name = SCENARIOS[scenario_id]["name"]

        # --- Single-objection (current) ---
        label_single = f"SINGLE | Scenario {scenario_id} ({scenario_name}) | L{level}"
        print(f"\n--- Running: {label_single} ---")
        sys_single = build_system_prompt(scenario_id, level, lang="ru")
        transcript_single = run_dialog(sys_single, MANAGER_TURNS_RU)
        print_transcript(transcript_single, label_single)

        # Count distinct objection types touched
        owner_text_single = " ".join(t for r, t in transcript_single if r == "owner")

        # --- Multi-objection (experimental) ---
        label_multi = f"MULTI  | Scenario {scenario_id} ({scenario_name}) | L{level}"
        print(f"\n--- Running: {label_multi} ---")
        sys_multi = build_multi_objection_prompt(scenario_id, level)
        transcript_multi = run_dialog(sys_multi, MANAGER_TURNS_RU)
        print_transcript(transcript_multi, label_multi)

        owner_text_multi = " ".join(t for r, t in transcript_multi if r == "owner")

        agreed_single = any(AGREE.search(t) for r, t in transcript_single if r == "owner")
        agreed_multi = any(AGREE.search(t) for r, t in transcript_multi if r == "owner")

        all_results.append({
            "scenario_id": scenario_id,
            "scenario_name": scenario_name,
            "level": level,
            "single": {"transcript": transcript_single, "agreed": agreed_single, "owner_text": owner_text_single},
            "multi": {"transcript": transcript_multi, "agreed": agreed_multi, "owner_text": owner_text_multi},
        })

        print(f"\n  >> SINGLE agreed={agreed_single} | MULTI agreed={agreed_multi}")

    # Summary
    print("\n" + "="*70)
    print("PART B SUMMARY")
    print("="*70)
    for r in all_results:
        print(f"\n  Scenario {r['scenario_id']} ({r['scenario_name']}) | Level {r['level']}")
        print(f"    SINGLE: agreed={r['single']['agreed']}")
        print(f"    MULTI:  agreed={r['multi']['agreed']}")

    return all_results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Investigation: Ukrainian behavior + single vs multi-objection personas")
    print(f"Model: {llm.LLM_MODEL}")

    results_a = part_a()
    results_b = part_b()

    # Final analysis report
    print("\n" + "#"*70)
    print("# FINAL ANALYSIS")
    print("#"*70)

    print("\n--- PART A: Ukrainian language verdict ---")
    total_ru = sum(r["assessment"]["ru_hits"] for r in results_a)
    total_uk = sum(r["assessment"]["uk_hits"] for r in results_a)
    agreed_count = sum(1 for r in results_a if r["assessment"]["agreed"])
    l1_agreed = sum(1 for r in results_a if r["level"] == 1 and r["assessment"]["agreed"])
    l4_agreed = sum(1 for r in results_a if r["level"] == 4 and r["assessment"]["agreed"])
    print(f"  Total UK word hits: {total_uk} | Total RU leak hits: {total_ru}")
    print(f"  Dialogs agreed to meeting: {agreed_count}/8")
    print(f"  L1 agreed: {l1_agreed}/4 | L4 agreed: {l4_agreed}/4")

    # Print sample quotes per level
    print("\n  Sample L1 owner replies (first dialog):")
    for r in results_a:
        if r["level"] == 1:
            for reply in r["assessment"]["owner_replies"][:2]:
                print(f"    '{reply}'")
            break

    print("\n  Sample L4 owner replies (first dialog):")
    for r in results_a:
        if r["level"] == 4:
            for reply in r["assessment"]["owner_replies"][:2]:
                print(f"    '{reply}'")
            break

    print("\n--- PART B: Single vs Multi-objection verdict ---")
    for r in results_b:
        print(f"\n  Scenario {r['scenario_id']} ({r['scenario_name']}):")
        print(f"    SINGLE sample (first 3 owner turns):")
        owner_turns_single = [(role, text) for role, text in r["single"]["transcript"] if role == "owner" and text != "Алло?"][:3]
        for _, text in owner_turns_single:
            print(f"      '{text}'")
        print(f"    MULTI  sample (first 3 owner turns):")
        owner_turns_multi = [(role, text) for role, text in r["multi"]["transcript"] if role == "owner" and text != "Алло?"][:3]
        for _, text in owner_turns_multi:
            print(f"      '{text}'")


if __name__ == "__main__":
    sys.exit(main())
