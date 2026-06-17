"""Тести аналізатора: підрахунок %, кліпінг, типобезпека, формат (без мережі)."""
from bot import analyzer


def test_weights_sum_to_one():
    assert abs(sum(w for _, _, w in analyzer.CRITERIA) - 1.0) < 1e-9


def test_overall_bounds():
    mx = analyzer.build_report({"scores": {k: 100 for k, _, _ in analyzer.CRITERIA}})
    mn = analyzer.build_report({"scores": {k: 0 for k, _, _ in analyzer.CRITERIA}})
    assert mx["overall"] == 100 and mn["overall"] == 0


def test_clamp_and_missing_scores():
    r = analyzer.build_report({"scores": {"contact": 150, "needs": -10}})
    assert r["scores"]["contact"] == 100
    assert r["scores"]["needs"] == 0
    assert r["scores"]["meeting"] == 0          # відсутній -> 0


def test_weighted_overall_matches_manual():
    sc = {"contact": 80, "needs": 60, "questions": 40, "objections": 20,
          "trust": 100, "meeting": 0, "negotiation": 50}
    exp = round(sum(sc[k] * w for k, _, w in analyzer.CRITERIA))
    assert analyzer.build_report({"scores": sc})["overall"] == exp


def test_strengths_string_and_none_coerced():
    r = analyzer.build_report({"scores": {}, "strengths": "один", "recommendations": None})
    assert r["strengths"] == ["один"]
    assert r["recommendations"] == []


def test_comments_carried_and_defaulted():
    r = analyzer.build_report({"scores": {}, "comments": {"contact": "хорошо"}})
    assert r["comments"]["contact"] == "хорошо"
    assert r["comments"]["needs"] == ""


def test_format_report_renders():
    r = analyzer.build_report({"scores": {k: 70 for k, _, _ in analyzer.CRITERIA},
                               "comments": {"contact": "ок"}})
    txt = analyzer.format_report(r)
    assert "ИТОГОВАЯ ОЦЕНКА: 70%" in txt
    assert "Работа с возражениями" in txt
    assert "— ок" in txt


def test_garbage_input_safe():
    r = analyzer.build_report("not a dict")
    assert r["overall"] == 0 and r["strengths"] == []
