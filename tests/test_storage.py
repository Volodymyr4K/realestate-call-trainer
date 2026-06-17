"""Тести збереження: round-trip розмов/аудіо/звітів + stt_log (тимчасова БД)."""
import pytest

from bot import storage


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "test.sqlite"))
    storage.init_db()


def test_save_and_get_with_audio(db):
    cid = storage.save_conversation(
        1, 3, 4, [["owner", "Алло?"], ["manager", "Здрав"]], 1,
        "2026-06-17T10:00:00+00:00", {"overall": 55}, [["owner", "a.ogg"]])
    g = storage.get_conversation(cid)
    assert g["scenario"] == 3 and g["level"] == 4
    assert g["report"]["overall"] == 55
    assert g["audio"] == [["owner", "a.ogg"]]
    assert g["transcript"] == [["owner", "Алло?"], ["manager", "Здрав"]]


def test_report_none_when_absent(db):
    cid = storage.save_conversation(1, 1, 1, [["owner", "Алло?"]], 0)
    assert storage.get_conversation(cid)["report"] is None


def test_get_missing_returns_none(db):
    assert storage.get_conversation(999) is None


def test_list_conversations_newest_first(db):
    storage.save_conversation(7, 1, 1, [], 1)
    storage.save_conversation(7, 2, 2, [], 1)
    rows = storage.list_conversations(7)
    assert len(rows) == 2 and rows[0]["id"] > rows[1]["id"]


def test_stt_log_success_and_fail(db):
    storage.log_stt(1, "sid", 1, "a.ogg", "привет", True)
    storage.log_stt(1, "sid", 2, "b.ogg", "", False)
    rows = storage.list_stt()
    assert len(rows) == 2
    assert rows[0]["ok"] == 0 and rows[0]["turn"] == 2          # новіші зверху
    assert rows[1]["ok"] == 1 and rows[1]["text"] == "привет"
