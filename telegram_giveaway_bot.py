import os
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

# ===== ENV =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# ===== DB =====
conn = sqlite3.connect("db.db")
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS participants (user_id INTEGER, giveaway_id INTEGER, number INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS giveaways (id INTEGER PRIMARY KEY AUTOINCREMENT, win_amount INTEGER, end_time INTEGER, status TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS withdraws (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, link TEXT, status TEXT)")
conn.commit()

# ===== FUNCS =====
def add_user(uid):
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, 0)", (uid,))
    conn.commit()

def get_balance(uid):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    return cursor.fetchone()[0]

def update_balance(uid, amount):
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
    conn.commit()

def get_active():
    cursor.execute("SELECT id, win_amount FROM giveaways WHERE status='active'")
    return cursor.fetchone()

# ===== START =====
@dp.message_handler(commands=['start'])
async def start(msg: types.Message):
    add_user(msg.from_user.id)

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile"))

    if msg.from_user.id == ADMIN_ID:
        kb.add(InlineKeyboardButton("🛠 АДМИНКА", callback_data="admin"))

    await msg.answer("🎲 <b>Wins Rush</b>", reply_markup=kb)

# ===== PROFILE =====
@dp.callback_query_handler(lambda c: c.data == "profile")
async def profile(call: types.CallbackQuery):
    bal = get_balance(call.from_user.id)

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💸 Вывести", callback_data="withdraw"))
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="back"))

    await call.message.edit_text(
        f"👤 <b>{call.from_user.username or call.from_user.id}</b>\n"
        f"💰 Баланс: <b>{bal}</b>",
        reply_markup=kb
    )

# ===== BACK =====
@dp.callback_query_handler(lambda c: c.data == "back")
async def back(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile"))

    if call.from_user.id == ADMIN_ID:
        kb.add(InlineKeyboardButton("🛠 АДМИНКА", callback_data="admin"))

    await call.message.edit_text("🎲 <b>Wins Rush</b>", reply_markup=kb)

# ===== ADMIN =====
@dp.callback_query_handler(lambda c: c.data == "admin")
async def admin(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎁 Создать", callback_data="create"))
    kb.add(InlineKeyboardButton("📋 Заявки", callback_data="list_w"))
    kb.add(InlineKeyboardButton("💰 Баланс ±", callback_data="balance_edit"))
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="back"))

    await call.message.edit_text("🛠 Админка", reply_markup=kb)

# ===== STATES =====
state = {}

# ===== CREATE =====
@dp.callback_query_handler(lambda c: c.data == "create")
async def create(call: types.CallbackQuery):
    state[call.from_user.id] = "create"
    await call.message.answer("Формат: сумма время(сек)\nПример: 50 300")

@dp.message_handler()
async def text(msg: types.Message):
    st = state.get(msg.from_user.id)

    # СОЗДАНИЕ
    if st == "create":
        try:
            amount, time_sec = map(int, msg.text.split())
        except:
            return

        cursor.execute(
            "INSERT INTO giveaways (win_amount, end_time, status) VALUES (?, ?, 'active')",
            (amount, int(asyncio.get_event_loop().time()) + time_sec)
        )
        conn.commit()
        gid = cursor.lastrowid

        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🎯 Участвовать", callback_data="join"))

        await bot.send_message(
            CHANNEL_ID,
            f"🎁 Розыгрыш\n💰 {amount}\n⏱ {time_sec} сек",
            reply_markup=kb
        )

        asyncio.create_task(auto_finish(gid, time_sec))
        await msg.answer("✅ Создано")
        state.pop(msg.from_user.id)

    # ВЫВОД
    elif st == "withdraw":
        if not msg.text.isdigit():
            return

        amount = int(msg.text)
        if get_balance(msg.from_user.id) < amount:
            await msg.answer("❌ Нет денег")
            return

        state[msg.from_user.id] = ("link", amount)
        await msg.answer("🔗 Ссылка с @BOR_CASINO_BOT")

    elif isinstance(st, tuple):
        amount = st[1]

        cursor.execute(
            "INSERT INTO withdraws (user_id, amount, link, status) VALUES (?, ?, ?, 'pending')",
            (msg.from_user.id, amount, msg.text)
        )
        conn.commit()

        wid = cursor.lastrowid

        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("✅", callback_data=f"ok_{wid}"),
            InlineKeyboardButton("❌", callback_data=f"no_{wid}")
        )

        await bot.send_message(
            ADMIN_ID,
            f"💸 Заявка\n@{msg.from_user.username}\n💰 {amount}\n{msg.text}",
            reply_markup=kb
        )

        await msg.answer("⏳ Отправлено")
        state.pop(msg.from_user.id)

# ===== AUTO FINISH =====
async def auto_finish(gid, delay):
    await asyncio.sleep(delay)

    cursor.execute("SELECT win_amount FROM giveaways WHERE id=?", (gid,))
    amount = cursor.fetchone()[0]

    dice = await bot.send_dice(CHANNEL_ID)
    num = dice.dice.value

    cursor.execute("SELECT user_id FROM participants WHERE giveaway_id=? AND number=?", (gid, num))
    winners = cursor.fetchall()

    text = f"🎲 {num}\n🏆 Победители:\n"

    for w in winners:
        update_balance(w[0], amount)
        text += f"<blockquote>{w[0]}</blockquote>\n"

    await bot.send_message(CHANNEL_ID, text)

    cursor.execute("UPDATE giveaways SET status='done' WHERE id=?", (gid,))
    conn.commit()

# ===== JOIN =====
@dp.callback_query_handler(lambda c: c.data == "join")
async def join(call: types.CallbackQuery):
    g = get_active()
    if not g:
        return

    kb = InlineKeyboardMarkup(row_width=3)
    for i in range(1, 7):
        kb.insert(InlineKeyboardButton(str(i), callback_data=f"pick_{i}"))

    await call.message.answer("🎲 Выбери:", reply_markup=kb)

# ===== PICK =====
@dp.callback_query_handler(lambda c: c.data.startswith("pick_"))
async def pick(call: types.CallbackQuery):
    num = int(call.data.split("_")[1])
    g = get_active()
    if not g:
        return

    gid = g[0]

    cursor.execute("SELECT * FROM participants WHERE user_id=? AND giveaway_id=?", (call.from_user.id, gid))
    if cursor.fetchone():
        await call.answer("❌ Уже выбрал")
        return

    cursor.execute("INSERT INTO participants VALUES (?, ?, ?)", (call.from_user.id, gid, num))
    conn.commit()

    await call.answer(f"✅ {num}")

# ===== WITHDRAW BTN =====
@dp.callback_query_handler(lambda c: c.data == "withdraw")
async def withdraw(call: types.CallbackQuery):
    state[call.from_user.id] = "withdraw"
    await call.message.answer("💸 Сумма:")

# ===== ADMIN ACTIONS =====
@dp.callback_query_handler(lambda c: c.data.startswith("ok_"))
async def ok(call: types.CallbackQuery):
    wid = int(call.data.split("_")[1])

    cursor.execute("SELECT user_id, amount FROM withdraws WHERE id=?", (wid,))
    uid, amount = cursor.fetchone()

    update_balance(uid, -amount)

    cursor.execute("UPDATE withdraws SET status='done' WHERE id=?", (wid,))
    conn.commit()

    await call.message.edit_text("✅ Выплачено")

@dp.callback_query_handler(lambda c: c.data.startswith("no_"))
async def no(call: types.CallbackQuery):
    wid = int(call.data.split("_")[1])

    cursor.execute("UPDATE withdraws SET status='cancel' WHERE id=?", (wid,))
    conn.commit()

    await call.message.edit_text("❌ Отмена")

# ===== RUN =====
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
