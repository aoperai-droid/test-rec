import asyncio
import json
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import aiosqlite

# ---------------- НАСТРОЙКИ ----------------
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = -1003939484246
ADMIN_ID = 1364254252

# ---------------- ЛОГИ ----------------

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ---------------- БАЗА ----------------

DB = "ads.db"

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT,
                file_id TEXT,
                file_type TEXT,
                times TEXT
            )
        """)
        await db.commit()

async def save_ad(text, file_id, file_type, times):
    async with aiosqlite.connect(DB) as db:
        c = await db.execute(
            "INSERT INTO ads (text, file_id, file_type, times) VALUES (?, ?, ?, ?)",
            (text, file_id, file_type, json.dumps(times))
        )
        await db.commit()
        return c.lastrowid

async def get_all():
    async with aiosqlite.connect(DB) as db:
        c = await db.execute("SELECT * FROM ads ORDER BY id DESC")
        return await c.fetchall()

async def get_for_time(t):
    async with aiosqlite.connect(DB) as db:
        c = await db.execute("SELECT * FROM ads WHERE times LIKE ?", (f'%"{t}"%',))
        return await c.fetchall()

async def delete_ad(ad_id):
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM ads WHERE id = ?", (ad_id,))
        await db.commit()

# ---------------- ХРАНИЛИЩЕ ----------------

new_post = None
new_times = []

# ---------------- КНОПКИ (24 часа) ----------------

def time_kb():
    buttons = []
    for hour in range(0, 24, 2):
        row = []
        for h in [hour, hour + 1]:
            if h < 24:
                time_str = f"{h:02d}:00"
                row.append(InlineKeyboardButton(text=time_str, callback_data=f"t:{time_str}"))
        buttons.append(row)
    
    buttons.append([
        InlineKeyboardButton(text="✅ Сохранить", callback_data="save"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---------------- КОМАНДЫ ----------------

@dp.message(Command("start"))
async def start(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "📢 <b>Бот для рекламы</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Команды:</b>\n"
        "/new — добавить новый пост\n"
        "/list — список постов\n"
        "/del id — удалить пост\n\n"
        "<b>Как добавить пост:</b>\n"
        "1. Отправьте /new\n"
        "2. Пришлите пост (текст, фото, видео)\n"
        "3. Выберите время кнопками (можно 2)\n"
        "4. Нажмите «Сохранить»",
        parse_mode="HTML"
    )

@dp.message(Command("new"))
async def cmd_new(message: Message):
    global new_post, new_times
    if message.from_user.id != ADMIN_ID:
        return
    
    new_post = None
    new_times = []
    
    await message.answer("📝 <b>Новый рекламный пост</b>\n\nОтправьте текст, фото или видео.", parse_mode="HTML")

@dp.message(Command("list"))
async def cmd_list(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    ads = await get_all()
    
    if not ads:
        await message.answer("📭 <b>Нет сохранённых постов</b>", parse_mode="HTML")
        return
    
    text = "📋 <b>Сохранённые посты:</b>\n\n"
    for ad in ads:
        times = json.loads(ad[4])
        times_str = ", ".join(times) if times else "без времени"
        preview = ad[1][:40] + "..." if ad[1] and len(ad[1]) > 40 else ad[1]
        text += (
            f"<b>#{ad[0]}</b> | {ad[3]}\n"
            f"⏰ {times_str}\n"
            f"📝 {preview}\n\n"
        )
    
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("del"))
async def cmd_del(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        ad_id = int(message.text.split()[1])
        await delete_ad(ad_id)
        await message.answer(f"✅ <b>Пост #{ad_id} удалён</b>", parse_mode="HTML")
        logger.info(f"Удалён пост #{ad_id}")
    except:
        await message.answer("❌ Использование: /del 1")

# ---------------- ПРИЁМ ПОСТА ----------------

@dp.message()
async def handle_message(message: Message):
    global new_post
    if message.from_user.id != ADMIN_ID:
        return
    
    text = message.text or message.caption or ""
    file_id = None
    file_type = "text"
    
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    
    new_post = {"text": text, "file_id": file_id, "file_type": file_type}
    
    await message.answer(
        "✅ <b>Пост принят!</b>\n\n"
        "Теперь выберите время публикации (можно 2).",
        reply_markup=time_kb(),
        parse_mode="HTML"
    )

# ---------------- CALLBACKS ----------------

@dp.callback_query(F.data.startswith("t:"))
async def pick_time(callback: CallbackQuery):
    global new_times
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    t = callback.data.split(":")[1] + ":" + callback.data.split(":")[2]
    
    if t in new_times:
        await callback.answer(f"⏰ {t} уже выбрано", show_alert=True)
        return
    
    if len(new_times) >= 2:
        await callback.answer("❌ Максимум 2 времени!", show_alert=True)
        return
    
    new_times.append(t)
    new_times.sort()
    
    await callback.answer(f"✅ {t} | Выбрано: {', '.join(new_times)}", show_alert=True)


@dp.callback_query(F.data == "save")
async def save_post(callback: CallbackQuery):
    global new_post, new_times
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    if new_post is None:
        await callback.answer("❌ Сначала отправьте пост", show_alert=True)
        return
    
    if not new_times:
        await callback.answer("❌ Выберите хотя бы одно время", show_alert=True)
        return
    
    ad_id = await save_ad(new_post["text"], new_post["file_id"], new_post["file_type"], new_times)
    
    await callback.message.delete()
    await callback.message.answer(
        f"✅ <b>Пост #{ad_id} сохранён!</b>\n\n"
        f"⏰ Время: {', '.join(new_times)}\n"
        f"📝 {new_post['text'][:50]}...\n\n"
        f"Бот опубликует его по расписанию.",
        parse_mode="HTML"
    )
    
    logger.info(f"Сохранён пост #{ad_id} на {new_times}")
    
    new_post = None
    new_times = []
    
    await callback.answer("✅ Сохранено!")


@dp.callback_query(F.data == "cancel")
async def cancel_post(callback: CallbackQuery):
    global new_post, new_times
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    new_post = None
    new_times = []
    
    await callback.message.delete()
    await callback.message.answer("❌ Отменено.")
    await callback.answer("Отменено")

# ---------------- ПЛАНИРОВЩИК ----------------

async def scheduler():
    last = {}
    
    while True:
        now = datetime.now()
        current = now.strftime("%H:%M")
        
        ads = await get_for_time(current)
        
        for ad in ads:
            key = f"{ad[0]}_{current}"
            
            if last.get(key) != now.date():
                try:
                    if ad[3] == "photo" and ad[2]:
                        await bot.send_photo(CHANNEL_ID, ad[2], caption=ad[1])
                    elif ad[3] == "video" and ad[2]:
                        await bot.send_video(CHANNEL_ID, ad[2], caption=ad[1])
                    else:
                        await bot.send_message(CHANNEL_ID, ad[1])
                    
                    last[key] = now.date()
                    logger.info(f"✅ Опубликован #{ad[0]} в {current}")
                except Exception as e:
                    logger.error(f"❌ Ошибка #{ad[0]}: {e}")
        
        await asyncio.sleep(30)

# ---------------- ЗАПУСК ----------------

async def main():
    await init_db()
    logger.info("🚀 Бот запущен")
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
