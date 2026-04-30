import os
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

# ===== ENV CONFIG =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

if not TOKEN:
    raise ValueError("TOKEN не найден")

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# ===== DB =====
conn = sqlite3.connect("db.db")
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS participants (user_id INTEGER, giveaway_id INTEGER, number INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS giveaways (id INTEGER PRIMARY KEY AUTOINCREMENT, win_amount INTEGER, status TEXT)")
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
        f"👤 <b>Профиль</b>\n\n💰 Баланс: <b>{bal}</b>",
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
    if call.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎁 Создать розыгрыш", callback_data="create_give"))
    kb.add(InlineKeyboardButton("🏁 Завершить розыгрыш", callback_data="finish"))
    kb.add(InlineKeyboardButton("📥 Заявки", callback_data="withdraws"))
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="back"))

    await call.message.edit_text("🛠 <b>Админ панель</b>", reply_markup=kb)

# ===== STATES =====
user_state = {}

# ===== CREATE GIVE =====
@dp.callback_query_handler(lambda c: c.data == "create_give")
async def create_give(call: types.CallbackQuery):
    user_state[call.from_user.id] = "wait_amount"
    await call.message.answer("💰 Введи сумму выигрыша:")

# ===== WITHDRAW BTN =====
@dp.callback_query_handler(lambda c: c.data == "withdraw")
async def withdraw(call: types.CallbackQuery):
    user_state[call.from_user.id] = "withdraw_amount"
    await call.message.answer("💸 Введи сумму:")

# ===== ALL TEXT =====
@dp.message_handler()
async def all_messages(msg: types.Message):
    state = user_state.get(msg.from_user.id)

    # СОЗДАНИЕ РОЗЫГРЫША
    if state == "wait_amount":
        if not msg.text.isdigit():
            return

        amount = int(msg.text)

        cursor.execute("INSERT INTO giveaways (win_amount, status) VALUES (?, 'active')", (amount,))
        conn.commit()

        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🎯 Участвовать", callback_data="join"))

        await bot.send_message(
            CHANNEL_ID,
            f"🎁 <b>РОЗЫГРЫШ</b>\n\n💰 Выигрыш: <b>{amount}</b>",
            reply_markup=kb
        )

        await msg.answer("✅ Розыгрыш создан")
        user_state.pop(msg.from_user.id)

    # ВЫВОД СУММЫ
    elif state == "withdraw_amount":
        if not msg.text.isdigit():
            return

        amount = int(msg.text)

        if get_balance(msg.from_user.id) < amount:
            await msg.answer("❌ Недостаточно средств")
            return

        user_state[msg.from_user.id] = ("withdraw_link", amount)
        await msg.answer("🔗 Скинь ссылку с @BOR_CASINO_BOT")

    # ССЫЛКА
    elif isinstance(state, tuple):
        amount = state[1]

        cursor.execute(
            "INSERT INTO withdraws (user_id, amount, link, status) VALUES (?, ?, ?, 'pending')",
            (msg.from_user.id, amount, msg.text)
        )
        conn.commit()

        wid = cursor.lastrowid

        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"ok_{wid}"),
            InlineKeyboardButton("❌ Отменить", callback_data=f"no_{wid}")
        )

        await bot.send_message(
            ADMIN_ID,
            f"💸 Заявка на вывод\n\n👤 {msg.from_user.id}\n💰 {amount}\n🔗 {msg.text}",
            reply_markup=kb
        )

        await msg.answer("⏳ Заявка отправлена")
        user_state.pop(msg.from_user.id)

# ===== JOIN =====
@dp.callback_query_handler(lambda c: c.data == "join")
async def join(call: types.CallbackQuery):
    g = get_active()
    if not g:
        return

    kb = InlineKeyboardMarkup(row_width=3)
    for i in range(1, 7):
        kb.insert(InlineKeyboardButton(f"🎯 {i}", callback_data=f"pick_{i}"))

    await call.message.answer("🎲 Выбери число:", reply_markup=kb)

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

    await call.answer(f"✅ Выбрано {num}")

# ===== FINISH =====
@dp.callback_query_handler(lambda c: c.data == "finish")
async def finish(call: types.CallbackQuery):
    g = get_active()
    if not g:
        return

    gid, amount = g

    dice = await bot.send_dice(CHANNEL_ID)
    num = dice.dice.value

    cursor.execute("SELECT user_id FROM participants WHERE giveaway_id=? AND number=?", (gid, num))
    winners = cursor.fetchall()

    text = f"🎲 Выпало: <b>{num}</b>\n\n🏆 Победители:\n"

    if not winners:
        text += "❌ Нет победителей"
    else:
        for w in winners:
            update_balance(w[0], amount)
            text += f"<blockquote>{w[0]}</blockquote>\n"

    await bot.send_message(CHANNEL_ID, text)

    cursor.execute("UPDATE giveaways SET status='done' WHERE id=?", (gid,))
    conn.commit()

# ===== ADMIN CONFIRM =====
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

    await call.message.edit_text("❌ Отменено")

# ===== RUN =====
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
