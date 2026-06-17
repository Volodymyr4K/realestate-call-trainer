"""Інструмент перегляду точності STT: генерує HTML, де поряд — аудіоплеєр і те,
що почув Whisper. Ре/цензор слухає й порівнює; провали виділені червоним.

Запуск: .venv/bin/python -m tools.stt_review  →  відкрий stt_review.html у браузері.
"""
import html
import os

from bot import storage

_CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:820px;margin:24px auto;padding:0 16px;color:#1c1c1e;background:#f5f5f7}
h1{font-size:20px} .sub{color:#666;margin-bottom:20px}
.card{background:#fff;border:1px solid #e3e3e8;border-radius:12px;padding:14px 16px;margin:12px 0}
.card.fail{border-color:#ff453a;background:#fff5f4}
.meta{font-size:12px;color:#888;margin-bottom:8px}
.badge{font-weight:700;padding:1px 7px;border-radius:6px;font-size:11px}
.badge.ok{background:#e3f7e8;color:#1d7a33} .badge.fail{background:#ffe2df;color:#c0271c}
audio{width:100%;margin:6px 0}
.text{font-size:15px;margin-top:6px} .text b{color:#0a66c2}
.empty{color:#c0271c;font-style:italic}
"""


def generate(out_path: str = "stt_review.html") -> tuple[str, int, int]:
    rows = storage.list_stt()
    total = len(rows)
    fails = sum(1 for r in rows if not r["ok"])
    cards = []
    for r in rows:
        ap = os.path.abspath(r["audio_path"]) if r["audio_path"] else ""
        ok = bool(r["ok"])
        badge = '<span class="badge ok">OK</span>' if ok else '<span class="badge fail">ПРОВАЛ</span>'
        if ap and os.path.exists(ap):
            audio = f'<audio controls preload="none" src="file://{html.escape(ap)}"></audio>'
        else:
            audio = '<div class="empty">аудіофайл не знайдено</div>'
        heard = html.escape(r["text"]) if r["text"] else ""
        text = (f'Whisper почув: «<b>{heard}</b>»' if heard
                else '<span class="empty">Whisper нічого не розпізнав (провал)</span>')
        cards.append(
            f'<div class="card {"ok" if ok else "fail"}">'
            f'<div class="meta">#{r["id"]} · user {r["user_id"]} · хід {r["turn"]} · '
            f'{r["created_at"]} · {badge}</div>{audio}<div class="text">{text}</div></div>'
        )
    page = (
        f'<!doctype html><html lang="uk"><head><meta charset="utf-8">'
        f'<title>STT review</title><style>{_CSS}</style></head><body>'
        f'<h1>Перевірка STT — аудіо ↔ що почув Whisper</h1>'
        f'<div class="sub">Усього спроб: <b>{total}</b> · Провалів: '
        f'<b style="color:#c0271c">{fails}</b>. Слухай кожне аудіо й звіряй з текстом.</div>'
        f'{"".join(cards) or "<p>Поки немає записів STT. Поговори з ботом голосовими.</p>"}'
        f'</body></html>'
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)
    return os.path.abspath(out_path), total, fails


if __name__ == "__main__":
    path, total, fails = generate()
    print(f"Готово: {path}\n  записів: {total}, провалів: {fails}. Відкрий файл у браузері.")
