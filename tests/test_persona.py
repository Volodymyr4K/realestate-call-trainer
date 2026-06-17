"""Тести персони: сценарії, рівні, мова, guardrail (чиста логіка, без мережі)."""
from bot.persona import SCENARIOS, LEVELS, build_system_prompt


def test_13_scenarios_unique():
    assert len(SCENARIOS) == 13
    assert len(set(s["context"] for s in SCENARIOS.values())) == 13


def test_all_52_prompts_build():
    for sid in SCENARIOS:
        for lvl in LEVELS:
            p = build_system_prompt(sid, lvl)
            assert SCENARIOS[sid]["context"][:20] in p
            assert LEVELS[lvl]["behavior"][:15] in p


def test_lang_directive_ru_uk():
    assert "кириллицей" in build_system_prompt(1, 1, lang="ru")
    assert "кирилицею" in build_system_prompt(1, 1, lang="uk")


def test_guardrail_present():
    p = build_system_prompt(1, 1)
    assert "Никогда не выходи из роли" in p
    assert "уравнение" in p          # захист від сторонніх задач
