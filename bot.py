import os
import random
import asyncio
import time
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from database import init_db, ensure_user, add_reward, get_profile, top_users, level_from_xp

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
QUESTION_TIME = int(os.getenv("QUESTION_TIME", 15))

if not TOKEN:
    raise ValueError("BOT_TOKEN bulunamadı. .env dosyasını kontrol et.")

oyunlar = {}

plakalar = {
    "34": "istanbul",
    "06": "ankara",
    "35": "izmir",
    "16": "bursa",
    "07": "antalya",
    "01": "adana",
    "27": "gaziantep",
    "41": "kocaeli",
    "55": "samsun"
}

def load_words():
    try:
        with open("data/kelimeler.txt", encoding="utf-8") as f:
            return [x.strip() for x in f if x.strip()]
    except FileNotFoundError:
        return []

def load_pairs(path):
    items = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "|" not in line:
                    continue
                q, a = line.split("|", 1)
                items[q.strip()] = a.strip().lower()
    except FileNotFoundError:
        pass
    return items

kelimeler = load_words()
emoji = load_pairs("data/emoji.txt")
bayrak = load_pairs("data/bayrak.txt")

def make_scrambled_word(word):
    if len(word) <= 1:
        return word
    mixed = word
    tries = 0
    while mixed == word and tries < 10:
        mixed = "".join(random.sample(word, len(word)))
        tries += 1
    return mixed

def calc_rewards(elapsed):
    if elapsed <= 3:
        return 10, 8, 5
    elif elapsed <= 7:
        return 7, 5, 3
    return 5, 3, 2

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.first_name)

    keyboard = [
        [InlineKeyboardButton("🎮 Karışık", callback_data="karisik")],
        [InlineKeyboardButton("🔤 Kelime", callback_data="kelime")],
        [InlineKeyboardButton("🚗 Plaka", callback_data="plaka")],
        [InlineKeyboardButton("😀 Emoji", callback_data="emoji")],
        [InlineKeyboardButton("🌍 Bayrak", callback_data="bayrak")],
        [InlineKeyboardButton("🧠 Matematik", callback_data="mat")],
    ]

    text = (
        "🎮 Oyun seç\n\n"
        "Komutlar:\n"
        "/start - menü\n"
        "/profil - profilin\n"
        "/top - liderlik\n"
        "/son - oyunu durdur"
    )

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat = query.message.chat.id
    secim = query.data

    if chat in oyunlar and "task" in oyunlar[chat]:
        oyunlar[chat]["task"].cancel()

    oyunlar[chat] = {
        "kategori": secim,
        "aktif": False,
        "cevap": None,
        "baslangic": None,
        "task": None,
        "qid": 0,
    }

    await query.message.reply_text(f"🎮 {secim.capitalize()} oyunu başladı.")

    task = context.application.create_task(oyun_loop(chat, context.application))
    oyunlar[chat]["task"] = task

async def soru(chat, app):
    if chat not in oyunlar:
        return

    kat = oyunlar[chat]["kategori"]
    oyun = random.choice(["kelime", "plaka", "mat", "emoji", "bayrak"]) if kat == "karisik" else kat

    cevap = None
    soru_text = None

    if oyun == "kelime":
        if not kelimeler:
            await app.bot.send_message(chat, "❌ Kelime listesi boş.")
            return
        k = random.choice(kelimeler).lower()
        cevap = k
        soru_text = f"🔤 Kelime\n\n{make_scrambled_word(k)}"

    elif oyun == "plaka":
        p, s = random.choice(list(plakalar.items()))
        cevap = s.lower()
        soru_text = f"🚗 {p} hangi şehir?"

    elif oyun == "mat":
        a = random.randint(10, 99)
        b = random.randint(10, 99)
        cevap = str(a + b)
        soru_text = f"🧠 {a} + {b} = ?"

    elif oyun == "emoji":
        if not emoji:
            await app.bot.send_message(chat, "❌ Emoji verisi boş.")
            return
        e, c = random.choice(list(emoji.items()))
        cevap = c.lower()
        soru_text = f"😀 {e}"

    elif oyun == "bayrak":
        if not bayrak:
            await app.bot.send_message(chat, "❌ Bayrak verisi boş.")
            return
        b, c = random.choice(list(bayrak.items()))
        cevap = c.lower()
        soru_text = f"🌍 {b}"

    if not cevap:
        return

    qid = random.randint(1000, 9999999)
    oyunlar[chat]["aktif"] = True
    oyunlar[chat]["cevap"] = cevap.strip()
    oyunlar[chat]["baslangic"] = time.time()
    oyunlar[chat]["qid"] = qid

    await app.bot.send_message(chat, soru_text)

    await asyncio.sleep(QUESTION_TIME)

    if chat not in oyunlar:
        return

    if oyunlar[chat]["qid"] != qid:
        return

    if oyunlar[chat]["aktif"]:
        await app.bot.send_message(chat, f"⏰ Süre bitti.\n✅ Cevap: {cevap}")
        oyunlar[chat]["aktif"] = False

async def oyun_loop(chat, app):
    try:
        while chat in oyunlar:
            if not oyunlar[chat]["aktif"]:
                await soru(chat, app)
            await asyncio.sleep(2)
    except asyncio.CancelledError:
        pass

async def mesaj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat.id

    if chat not in oyunlar:
        return
    if not oyunlar[chat]["aktif"]:
        return
    if not update.message or not update.message.text:
        return

    text = update.message.text.lower().strip()
    cevap = oyunlar[chat]["cevap"]

    if text == cevap:
        elapsed = time.time() - oyunlar[chat]["baslangic"]
        points, xp, coins = calc_rewards(elapsed)

        user = update.effective_user
        add_reward(user.id, user.first_name, points, xp, coins)

        profile = get_profile(user.id, user.first_name)
        name, total_points, total_xp, total_coins, daily_correct, streak, total_correct = profile
        lvl = level_from_xp(total_xp)

        await update.message.reply_text(
            f"🎉 {name} doğru!\n\n"
            f"⏱ Süre: {elapsed:.2f} sn\n"
            f"🏆 +{points} puan\n"
            f"⭐ +{xp} xp\n"
            f"💰 +{coins} coin\n\n"
            f"📊 Toplam Puan: {total_points}\n"
            f"⭐ Level: {lvl}\n"
            f"🔥 Streak: {streak}"
        )

        oyunlar[chat]["aktif"] = False

async def son(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat.id

    if chat in oyunlar:
        if "task" in oyunlar[chat] and oyunlar[chat]["task"]:
            oyunlar[chat]["task"].cancel()
        del oyunlar[chat]

    await update.message.reply_text("🛑 Oyun durduruldu.")

async def profil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    profile = get_profile(user.id, user.first_name)

    name, points, xp, coins, daily_correct, streak, total_correct = profile
    lvl = level_from_xp(xp)

    await update.message.reply_text(
        f"👤 Profil\n\n"
        f"İsim: {name}\n"
        f"🏆 Puan: {points}\n"
        f"⭐ XP: {xp}\n"
        f"🆙 Level: {lvl}\n"
        f"💰 Coin: {coins}\n"
        f"🔥 Streak: {streak}\n"
        f"✅ Günlük Doğru: {daily_correct}\n"
        f"📚 Toplam Doğru: {total_correct}"
    )

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = top_users(20)

    if not rows:
        await update.message.reply_text("Henüz liderlik verisi yok.")
        return

    text = "🏆 Liderlik Tablosu\n\n"
    for i, (name, points) in enumerate(rows, start=1):
        text += f"{i}. {name} - {points} puan\n"

    await update.message.reply_text(text)

async def yardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 Komutlar\n\n"
        "/start - oyun menüsü\n"
        "/profil - profilin\n"
        "/top - liderlik tablosu\n"
        "/son - oyunu durdur\n"
        "/yardim - yardım"
    )

def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("son", son))
    app.add_handler(CommandHandler("stop", son))
    app.add_handler(CommandHandler("profil", profil))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("yardim", yardim))
    app.add_handler(CallbackQueryHandler(kategori))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mesaj))

    print("🔥 BOT AKTİF 🔥")
    app.run_polling()

if __name__ == "__main__":
    main()
