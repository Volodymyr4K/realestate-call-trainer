"""Головний файл: зв'язує Telegram + STT + LLM + TTS у живий цикл.

Цикл однієї розмови:
  /start -> вибір рівня -> бот «Алло?» -> [голос менеджера -> STT -> LLM -> TTS -> голос] -> /finish

Активні сесії — в памʼяті (dict); завершена розмова + звіт зберігаються в SQLite.
Виклики STT/LLM/TTS блокуючі (CPU), тому ганяємо їх у потоці через to_thread,
щоб бот не «застигав» на час обробки.
"""
import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, FSInputFile, BotCommand,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from bot.config import require_bot_token, RECORDINGS_DIR, SESSION_TIMEOUT_MIN
from bot import stt, llm, tts, storage, analyzer
from bot.persona import build_system_prompt, LEVELS, SCENARIOS

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()

# user_id -> {"history": [...], "scenario", "level", "turn", "last_active"}
sessions: dict[int, dict] = {}

GREETING = "Алло?"


def get_active_session(uid: int) -> dict | None:
    """Повертає сесію або None, якщо її немає чи вона застаріла.

    Ліниве застарівання: сесію старшу за SESSION_TIMEOUT_MIN хв скидаємо при
    наступній взаємодії (без фонових задач).
    """
    s = sessions.get(uid)
    if s is None:
        return None
    if time.monotonic() - s["last_active"] > SESSION_TIMEOUT_MIN * 60:
        del sessions[uid]
        return None
    return s


@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Довідка: як користуватись тренажером."""
    await message.answer(
        "Я — тренажёр телефонных продаж недвижимости. Я играю собственника квартиры, ты — менеджер агентства.\n\n"
        "Как тренироваться:\n"
        "1. /start — выбери сценарий и уровень сложности\n"
        "2. Я «беру трубку» («Алло?») — звони мне голосовым, как риелтор\n"
        "3. Веди разговор голосовыми, отрабатывай возражения\n"
        "4. /finish — завершить и получить отчёт с оценкой\n\n"
        "Команды: /start — начать · /finish — завершить и получить отчёт · /help — справка"
    )


@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Крок 1: вибір сценарію (кого граємо)."""
    rows = [
        [InlineKeyboardButton(text=f"{sc}. {SCENARIOS[sc]['name']}",
                              callback_data=f"scen:{sc}")]
        for sc in SCENARIOS
    ]
    await message.answer(
        "Тренировка звонка. Выбери сценарий — кого играем:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@dp.callback_query(F.data.startswith("scen:"))
async def pick_scenario(cb: CallbackQuery):
    """Крок 2: обрали сценарій -> показуємо рівні складності."""
    await cb.answer()
    scenario = int(cb.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{i}. {LEVELS[i]['name']}",
                              callback_data=f"lvl:{scenario}:{i}") for i in (1, 2)],
        [InlineKeyboardButton(text=f"{i}. {LEVELS[i]['name']}",
                              callback_data=f"lvl:{scenario}:{i}") for i in (3, 4)],
    ])
    await cb.message.answer(
        f"Сценарий: «{SCENARIOS[scenario]['name']}».\nВыбери уровень сложности:",
        reply_markup=kb,
    )


@dp.callback_query(F.data.startswith("lvl:"))
async def pick_level(cb: CallbackQuery):
    """Крок 3: обрали рівень -> стартуємо сесію, бот «бере слухавку»."""
    await cb.answer()  # одразу знімаємо «годинник» на кнопці
    _, scenario_s, level_s = cb.data.split(":")
    scenario, level = int(scenario_s), int(level_s)
    uid = cb.from_user.id
    # session id робить імена аудіофайлів унікальними — щоб нова розмова
    # не затирала записи попередньої (час + короткий uuid).
    sid = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6]
    system = build_system_prompt(scenario, level)
    s = sessions[uid] = {
        "history": [{"role": "system", "content": system},
                    {"role": "assistant", "content": GREETING}],
        "scenario": scenario, "level": level, "turn": 0,
        "last_active": time.monotonic(),
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sid": sid,
        "transcript": [("owner", GREETING)],
        "audio": [],
    }
    await cb.message.answer(
        f"Сценарий «{SCENARIOS[scenario]['name']}», уровень {level} ({LEVELS[level]['name']}).\n"
        "Ты звонишь — начинай разговор голосовым. /finish — завершить и получить отчёт."
    )
    try:
        voice = await asyncio.to_thread(tts.synthesize, GREETING, f"{uid}_{sid}_greet")
        s["audio"].append(["owner", voice])
        await cb.message.answer_voice(FSInputFile(voice))
    except Exception:
        logging.exception("Помилка синтезу вітання (uid=%s)", uid)
        await cb.message.answer("(Не удалось озвучить «Алло?», но можно начинать — пиши голосовым.)")


@dp.message(F.voice)
async def on_voice(message: Message):
    """Повний цикл: голос менеджера -> текст -> відповідь власника -> голос."""
    uid = message.from_user.id
    s = get_active_session(uid)
    if s is None:
        await message.answer("Сначала /start, чтобы выбрать уровень.")
        return
    s["last_active"] = time.monotonic()
    turn = s["turn"] + 1
    in_path = f"{RECORDINGS_DIR}/{uid}_{s['sid']}_{turn}_in.ogg"

    try:
        # «записує голосове…» одразу — щоб менеджер бачив, що бот відповідає, а не завис.
        # Реальну латентність STT/LLM/TTS це не зменшує, лише сприйняття (статус живе ~5с).
        await message.bot.send_chat_action(message.chat.id, "record_voice")

        # 1. Завантажуємо голосове менеджера
        file = await message.bot.get_file(message.voice.file_id)
        await message.bot.download_file(file.file_path, in_path)

        # 2. STT (логуємо КОЖНУ спробу — і успіх, і провал — для перевірки точності)
        text = await asyncio.to_thread(stt.transcribe, in_path)
        await asyncio.to_thread(storage.log_stt, uid, s["sid"], turn, in_path, text, bool(text))
        if not text:
            await message.answer("Не расслышал. Попробуй ещё раз.")
            return

        # 3. LLM (відповідь власника). Працюємо з копією історії —
        #    у сесію записуємо лише після повного успіху (атомарність).
        candidate = s["history"] + [{"role": "user", "content": text}]
        answer = await asyncio.to_thread(llm.reply, candidate)

        # 4. TTS -> голос назад
        voice = await asyncio.to_thread(tts.synthesize, answer, f"{uid}_{s['sid']}_{turn}_out")
        await message.answer_voice(FSInputFile(voice))
    except Exception:
        logging.exception("Помилка обробки голосового (uid=%s, turn=%s)", uid, turn)
        await message.answer("Ой, что-то сломалось на моей стороне. Попробуй ещё раз.")
        return

    # Успіх: фіксуємо історію, транскрипт, аудіо й лічильник (паралельно транскрипту)
    candidate.append({"role": "assistant", "content": answer})
    s["history"] = candidate
    s["transcript"].append(("manager", text))
    s["transcript"].append(("owner", answer))
    s["audio"].append(["manager", in_path])
    s["audio"].append(["owner", voice])
    s["turn"] = turn


@dp.message(Command("finish"))
async def cmd_finish(message: Message):
    """Завершуємо розмову: зберігаємо в БД + формуємо звіт-оцінку."""
    uid = message.from_user.id
    s = get_active_session(uid)
    if s is None:
        await message.answer("Активного разговора нет. /start чтобы начать.")
        return
    if s["turn"] == 0:
        del sessions[uid]
        await message.answer("Разговор не начался — оценивать нечего. /start чтобы попробовать снова.")
        return

    await message.answer("Анализирую разговор, секунду…")

    # Аналіз (LLM). Якщо впаде — розмову все одно збережемо без звіту.
    report = None
    try:
        report = await asyncio.to_thread(
            analyzer.analyze, s["transcript"], s["level"],
            SCENARIOS[s["scenario"]]["context"],
        )
    except Exception:
        logging.exception("Помилка аналізу розмови (uid=%s)", uid)

    try:
        await asyncio.to_thread(
            storage.save_conversation, uid, s["scenario"], s["level"],
            s["transcript"], s["turn"], s["started_at"], report, s["audio"],
        )
    except Exception:
        logging.exception("Помилка збереження розмови (uid=%s)", uid)

    del sessions[uid]

    if report is not None:
        await message.answer(analyzer.format_report(report))
    else:
        await message.answer("Тренировка завершена, но отчёт сформировать не удалось. Попробуйте позже.")


@dp.message()
async def fallback(message: Message):
    """Усе, що не команда й не голосове — підказуємо що робити."""
    await message.answer("Не понял. Пришли голосовое сообщение или /help.")


async def main():
    storage.init_db()
    bot = Bot(require_bot_token())
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать тренировку"),
        BotCommand(command="finish", description="Завершить и получить отчёт"),
        BotCommand(command="help", description="Справка"),
    ])
    logging.info("Бот запущено. Очікую повідомлення...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
