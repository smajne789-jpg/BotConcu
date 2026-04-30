import os
import asyncio
import json
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatMemberStatus
from aiogram.filters import CommandStart
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DB_FILE = "db.json"

# ================= БАЗА =================
def load_db():
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except:
        return {"users": {}, "withdraws": []}

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(db, f)

db = load_db()

# ================= СОСТОЯНИЯ =================
withdraw_state = {}
admin_state = {}

giveaway = {
    "active": False,
    "choices": {},
    "stats": {i: 0 for i in range(1, 7)},
    "message_id": None,
    "prize": 0
}

# ================= КНОПКИ =================
def main_menu(uid):
    kb = [
        [InlineKeyboardButton(text="🎲 Участвовать", callback_data="participate")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")]
    ]

    if uid == ADMIN_ID:
        kb.append([InlineKeyboardButton(text="⚙️ Админка", callback_data="admin")])

    return InlineKeyboardMarkup(inline_keyboard=kb)

def numbers_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=str(i), callback_data=f"num_{i}") for i in range(1, 7)]
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Создать розыгрыш", callback_data="admin_create")],
        [InlineKeyboardButton(text="💰 Выдать баланс", callback_data="admin_add")],
        [InlineKeyboardButton(text="📊 Пользователи", callback_data="admin_users")]
    ])

# ================= ПОДПИСКА =================
async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except:
        return False

# ================= СТАРТ =================
@dp.message(CommandStart())
async def start(msg: types.Message):
    uid = msg.from_user.id

    if str(uid) not in db["users"]:
        db["users"][str(uid)] = {"balance": 0}
        save_db()

    if not await check_sub(uid):
        await msg.answer("❗ Подпишись на канал")
        return

    await msg.answer("Главное меню:", reply_markup=main_menu(uid))

# ================= ПРОФИЛЬ =================
@dp.callback_query(F.data == "profile")
async def profile(call: types.CallbackQuery):
    uid = str(call.from_user.id)
    bal = db["users"][uid]["balance"]

    await call.message.answer(f"👤 ID: {uid}\n💰 Баланс: {bal}")

# ================= УЧАСТИЕ =================
@dp.callback_query(F.data == "participate")
async def participate(call: types.CallbackQuery):
    uid = str(call.from_user.id)

    if not giveaway["active"]:
        await call.answer("Нет активного розыгрыша", show_alert=True)
        return

    if uid in giveaway["choices"]:
        await call.answer("Ты уже участвовал", show_alert=True)
        return

    await call.message.answer("Выбери число:", reply_markup=numbers_kb())

@dp.callback_query(F.data.startswith("num_"))
async def choose(call: types.CallbackQuery):
    uid = str(call.from_user.id)

    if uid in giveaway["choices"]:
        await call.answer("Уже выбрал", show_alert=True)
        return

    num = int(call.data.split("_")[1])
    giveaway["choices"][uid] = num
    giveaway["stats"][num] += 1

    await call.answer("Принято")
    await update_post()

# ================= ОБНОВЛЕНИЕ =================
async def update_post():
    if giveaway["message_id"]:
        text = "🎲 Розыгрыш\n\n"
        for i in range(1, 7):
            text += f"{i}: {giveaway['stats'][i]}\n"

        try:
            await bot.edit_message_text(CHANNEL_ID, giveaway["message_id"], text)
        except:
            pass

# ================= СОЗДАНИЕ =================
@dp.callback_query(F.data == "admin_create")
async def admin_create(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    admin_state[call.from_user.id] = "create"
    await call.message.answer("Введи: время(сек) приз")

@dp.message()
async def admin_inputs(msg: types.Message):
    uid = msg.from_user.id

    if uid not in admin_state:
        return

    if admin_state[uid] == "create":
        sec, prize = msg.text.split()

        giveaway.update({
            "active": True,
            "choices": {},
            "stats": {i: 0 for i in range(1, 7)},
            "prize": int(prize)
        })

        sent = await bot.send_message(
            CHANNEL_ID,
            "🎲 Новый розыгрыш\nЖми участвовать 👇",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Участвовать", url=f"https://t.me/{(await bot.me()).username}?start=play")]]
            )
        )

        giveaway["message_id"] = sent.message_id

        await msg.answer("Запущено")

        del admin_state[uid]

        await asyncio.sleep(int(sec))
        await finish()

# ================= ФИНИШ =================
async def finish():
    giveaway["active"] = False

    dice = await bot.send_dice(CHANNEL_ID)
    result = dice.dice.value

    winners = [u for u, n in giveaway["choices"].items() if n == result]

    for uid in winners:
        db["users"].setdefault(uid, {"balance": 0})
        db["users"][uid]["balance"] += giveaway["prize"]

    save_db()

    await bot.send_message(CHANNEL_ID, f"🎲 Выпало: {result}\n🏆 Победителей: {len(winners)}")

# ================= ВЫВОД =================
@dp.callback_query(F.data == "withdraw")
async def withdraw(call: types.CallbackQuery):
    withdraw_state[call.from_user.id] = "amount"
    await call.message.answer("Введите сумму:")

@dp.message(F.text.regexp(r"^\d+$"))
async def withdraw_amount(msg: types.Message):
    uid = msg.from_user.id

    if uid not in withdraw_state:
        return

    amount = int(msg.text)

    if db["users"][str(uid)]["balance"] < amount:
        await msg.answer("Недостаточно средств")
        return

    withdraw_state[uid] = {"amount": amount}

    await msg.answer(f"Отправь ссылку из BOR_CASINO_BOT на сумму {amount}")

@dp.message(F.text.startswith("http"))
async def withdraw_link(msg: types.Message):
    uid = msg.from_user.id

    if uid not in withdraw_state or not isinstance(withdraw_state[uid], dict):
        return

    data = withdraw_state[uid]
    amount = data["amount"]

    db["users"][str(uid)]["balance"] -= amount

    req = {"uid": uid, "amount": amount, "link": msg.text}
    db["withdraws"].append(req)
    save_db()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅", callback_data=f"ok_{len(db['withdraws'])-1}"),
         InlineKeyboardButton(text="❌", callback_data=f"no_{len(db['withdraws'])-1}")]
    ])

    await bot.send_message(ADMIN_ID, f"Заявка\n{uid}\n{amount}\n{msg.text}", reply_markup=kb)
    await msg.answer("Заявка отправлена")

    del withdraw_state[uid]

# ================= АДМИН =================
@dp.callback_query(F.data == "admin")
async def admin_panel(call: types.CallbackQuery):
    if call.from_user.id == ADMIN_ID:
        await call.message.answer("Админ панель:", reply_markup=admin_kb())

@dp.callback_query(F.data.startswith("ok_") | F.data.startswith("no_"))
async def admin_decision(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    action, i = call.data.split("_")
    i = int(i)
    req = db["withdraws"][i]

    if action == "no":
        db["users"][str(req["uid"])]["balance"] += req["amount"]

    save_db()
    await call.message.edit_text("Готово")

# ================= ЗАПУСК =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
