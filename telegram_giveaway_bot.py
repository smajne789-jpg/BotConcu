import random
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

TOKEN = "8422920710:AAGdE6nGod5VzJDHq33Fi5y0s0shb-wdYrY"
CHANNEL_ID = "@first_time67"
ADMIN_ID = 8034491282  # your Telegram ID

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Giveaway storage
giveaways = {}

# Start command (admin panel)
@dp.message_handler(commands=['start'])
async def start(msg: types.Message):
    if msg.from_user.id == ADMIN_ID:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Создать розыгрыш", callback_data="create"))
        await msg.answer("Панель администратора:", reply_markup=kb)

# Create giveaway button
@dp.callback_query_handler(lambda c: c.data == "create")
async def create_giveaway(call: types.CallbackQuery):
    await call.message.answer("Введите название розыгрыша:")
    dp.register_message_handler(set_title, state=None)

# Set giveaway title
async def set_title(msg: types.Message):
    title = msg.text
    giveaway_id = len(giveaways) + 1

    giveaways[giveaway_id] = {
        "title": title,
        "participants": []
    }

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎉 Участвовать", callback_data=f"join_{giveaway_id}"))

    post = await bot.send_message(
        CHANNEL_ID,
        f"🎁 Розыгрыш: {title}\n\nНажми кнопку ниже, чтобы участвовать!",
        reply_markup=kb
    )

    giveaways[giveaway_id]["message_id"] = post.message_id

    await msg.answer("Розыгрыш опубликован!")

# Join giveaway
@dp.callback_query_handler(lambda c: c.data.startswith("join_"))
async def join(call: types.CallbackQuery):
    giveaway_id = int(call.data.split("_")[1])
    user = call.from_user

    if user.id in giveaways[giveaway_id]["participants"]:
        await call.answer("Ты уже участвуешь!", show_alert=True)
        return

    giveaways[giveaway_id]["participants"].append(user.id)
    count = len(giveaways[giveaway_id]["participants"])

    await call.answer(f"Ты участник! ({count}/6)")

    if count == 6:
        await run_giveaway(giveaway_id)

# Run giveaway
async def run_giveaway(giveaway_id):
    data = giveaways[giveaway_id]
    participants = data["participants"]

    random.shuffle(participants)
    winner_number = random.randint(1, 6)
    winner_id = participants[winner_number - 1]

    winner = await bot.get_chat(winner_id)

    result_text = (
        f"🎉 Результаты розыгрыша!\n\n"
        f"🎁 {data['title']}\n"
        f"🎲 Выпало число: {winner_number}\n"
        f"🏆 Победитель: @{winner.username}"
    )

    await bot.send_message(CHANNEL_ID, result_text)

# Run bot
if __name__ == "__main__":
    executor.start_polling(dp)
