import os
import random
import asyncio
import time
from pathlib import Path
from collections import deque
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

from database import (
    init_db,
    ensure_user,
    add_reward,
    get_profile,
    top_users,
    get_level,
    claim_daily,
    buy_item,
    use_hint,
    get_achievements,
)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
QUESTION_TIME = int(os.getenv("QUESTION_TIME", 20))
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/telegram")
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBotUsername")

if not TOKEN:
    raise ValueError("BOT_TOKEN bulunamadı. .env dosyasını kontrol et.")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

oyunlar = {}
group_scores = {}

plakalar = {
    "01": "adana","02": "adiyaman","03": "afyonkarahisar","04": "agri","05": "amasya","06": "ankara",
    "07": "antalya","08": "artvin","09": "aydin","10": "balikesir","11": "bilecik","12": "bingol",
    "13": "bitlis","14": "bolu","15": "burdur","16": "bursa","17": "canakkale","18": "cankiri",
    "19": "corum","20": "denizli","21": "diyarbakir","22": "edirne","23": "elazig","24": "erzincan",
    "25": "erzurum","26": "eskisehir","27": "gaziantep","28": "giresun","29": "gumushane","30": "hakkari",
    "31": "hatay","32": "isparta","33": "mersin","34": "istanbul","35": "izmir","36": "kars",
    "37": "kastamonu","38": "kayseri","39": "kirklareli","40": "kirsehir","41": "kocaeli","42": "konya",
    "43": "kutahya","44": "malatya","45": "manisa","46": "kahramanmaras","47": "mardin","48": "mugla",
    "49": "mus","50": "nevsehir","51": "nigde","52": "ordu","53": "rize","54": "sakarya","55": "samsun",
    "56": "siirt","57": "sinop","58": "sivas","59": "tekirdag","60": "tokat","61": "trabzon","62": "tunceli",
    "63": "sanliurfa","64": "usak","65": "van","66": "yozgat","67": "zonguldak","68": "aksaray","69": "bayburt",
    "70": "karaman","71": "kirikkale","72": "batman","73": "sirnak","74": "bartin","75": "ardahan","76": "igdir",
    "77": "yalova","78": "karabuk","79": "kilis","80": "osmaniye","81": "duzce"
}

def load_words():
    path = DATA_DIR / "kelimeler.txt"
    try:
        with open(path, encoding="utf-8") as f:
            words = [x.strip().lower() for x in f if x.strip()]
            print(f"Kelime sayısı yüklendi: {len(words)}")
            return words
    except FileNotFoundError:
        print(f"HATA: {path} bulunamadı")
        return []

def load_pairs(filename):
    items = {}
    path = DATA_DIR / filename
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "|" not in line:
                    continue
                q, a = line.split("|", 1)
                q = q.strip()
                a = a.strip().lower()
                if q and a:
                    items[q] = a
        print(f"{filename} yüklendi: {len(items)} kayıt")
    except FileNotFoundError:
        print(f"HATA: {path} bulunamadı")
    return items

def load_quiz():
    path = DATA_DIR / "quiz.txt"
    questions = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "|" not in line:
                    continue
                parts = line.split("|")
                if len(parts) == 6:
                    soru, a, b, c, d, dogru = parts
                    questions.append({
                        "soru": soru.strip(),
                        "secenekler": [a.strip(), b.strip(), c.strip(), d.strip()],
                        "dogru": dogru.strip().upper()
                    })
        print(f"quiz.txt yüklendi: {len(questions)} kayıt")
    except FileNotFoundError:
        print(f"HATA: {path} bulunamadı")
    return questions

kelimeler = load_words()
emoji = load_pairs("emoji.txt")
bayrak = load_pairs("bayrak.txt")
quizler = load_quiz()

def make_scrambled_word(word):
    if len(word) <= 1:
        return word
    mixed = word
    tries = 0
    while mixed == word and tries < 10:
        mixed = "".join(random.sample(word, len(word)))
        tries += 1
    return mixed

def normalize(text):
    text = text.lower().strip()
    replace_map = {
        "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "İ": "i",
    }
    for tr, en in replace_map.items():
        text = text.replace(tr, en)
    return text

def calc_rewards(elapsed, zorluk):
    base_points = {"kolay": 5, "orta": 8, "zor": 12}
    base_xp = {"kolay": 3, "orta": 5, "zor": 8}
    base_coin = {"kolay": 2, "orta": 3, "zor": 5}

    points = base_points.get(zorluk, 5)
    xp = base_xp.get(zorluk, 3)
    coin = base_coin.get(zorluk, 2)

    if elapsed <= 3:
        points += 3
        xp += 2
        coin += 1
    elif elapsed <= 7:
        points += 1
        xp += 1

    return points, xp, coin

def get_hint_text(category, answer):
    if category == "kelime":
        if len(answer) <= 2:
            return f"💡 *İpucu*\n\nKelime `{answer[0]}` harfi ile başlıyor."
        return (
            f"💡 *İpucu*\n\n"
            f"🔠 İlk harf: `{answer[0]}`\n"
            f"🔚 Son harf: `{answer[-1]}`\n"
            f"📏 Uzunluk: `{len(answer)}`"
        )
    elif category in ["plaka", "bayrak", "emoji"]:
        return f"💡 *İpucu*\n\n🔠 İlk harf: `{answer[0]}`\n📏 Uzunluk: `{len(answer)}`"
    elif category == "mat":
        return "💡 *İpucu*\n\nSonucun tek mi çift mi olduğuna dikkat et."
    elif category == "quiz":
        return "💡 *İpucu*\n\nŞıkları tekrar dikkatlice incele."
    return "💡 İpucu mevcut değil."

def main_menu_text(user_name, is_group=False):
    if is_group:
        return (
            f"✨ *QUIZ ARENA - GRUP MODU*\n\n"
            f"👋 Merhaba *{user_name}*\n"
            f"Bu grupta herkes oyunu başlatabilir ve cevap verebilir.\n\n"
            f"🎮 Kategoriler:\n"
            f"🔤 Kelime • 🚗 Plaka • 😀 Emoji • 🌍 Bayrak • 🧠 Matematik • ❓ Quiz\n\n"
            f"👇 Aşağıdan seçim yapın."
        )
    return (
        f"✨ *QUIZ ARENA BOT*\n\n"
        f"👋 Hoş geldin *{user_name}*\n"
        f"Bilgini test et, puan kazan, level atla.\n\n"
        f"👇 Aşağıdan devam et."
    )

def build_main_menu():
    add_to_group_url = f"https://t.me/{BOT_USERNAME}?startgroup=true"
    keyboard = [
        [
            InlineKeyboardButton("🎮 Oyun Menüsü", callback_data="menu_games"),
            InlineKeyboardButton("👤 Profilim", callback_data="menu_profil"),
        ],
        [
            InlineKeyboardButton("🏆 Global Liderlik", callback_data="menu_top"),
            InlineKeyboardButton("👥 Grup Liderliği", callback_data="menu_gtop"),
        ],
        [
            InlineKeyboardButton("🎁 Günlük Ödül", callback_data="menu_daily"),
            InlineKeyboardButton("🛒 Market", callback_data="menu_market"),
        ],
        [
            InlineKeyboardButton("🏅 Başarımlar", callback_data="menu_achievements"),
        ],
        [
            InlineKeyboardButton("➕ Beni Gruba Ekle", url=add_to_group_url),
        ],
        [
            InlineKeyboardButton("📢 Destek / Kanal", url=SUPPORT_URL),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def add_group_score(chat_id, user_id, name, points):
    chat_id = str(chat_id)
    user_id = str(user_id)
    if chat_id not in group_scores:
        group_scores[chat_id] = {}
    if user_id not in group_scores[chat_id]:
        group_scores[chat_id][user_id] = {"name": name, "points": 0}
    group_scores[chat_id][user_id]["name"] = name
    group_scores[chat_id][user_id]["points"] += points

def get_group_top(chat_id, limit=10):
    chat_id = str(chat_id)
    if chat_id not in group_scores:
        return []
    rows = list(group_scores[chat_id].values())
    rows.sort(key=lambda x: x["points"], reverse=True)
    return rows[:limit]

def choose_non_repeating(seq, used_keys, key_func):
    if not seq:
        return None
    available = [x for x in seq if key_func(x) not in used_keys]
    if not available:
        used_keys.clear()
        available = seq[:]
    item = random.choice(available)
    used_keys.append(key_func(item))
    return item

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    ensure_user(user.id, user.first_name)

    is_group = chat.type in ["group", "supergroup"]

    await update.message.reply_text(
        main_menu_text(user.first_name, is_group=is_group),
        reply_markup=build_main_menu(),
        parse_mode="Markdown"
    )

async def oyun_menusu(query):
    keyboard = [
        [
            InlineKeyboardButton("🎲 Karışık", callback_data="karisik"),
            InlineKeyboardButton("🔤 Kelime", callback_data="kelime"),
        ],
        [
            InlineKeyboardButton("🚗 Plaka", callback_data="plaka"),
            InlineKeyboardButton("😀 Emoji", callback_data="emoji"),
        ],
        [
            InlineKeyboardButton("🌍 Bayrak", callback_data="bayrak"),
            InlineKeyboardButton("🧠 Matematik", callback_data="mat"),
        ],
        [
            InlineKeyboardButton("❓ 4 Şıklı Quiz", callback_data="quiz"),
        ],
        [
            InlineKeyboardButton("🟢 Kolay", callback_data="zorluk_kolay"),
            InlineKeyboardButton("🟡 Orta", callback_data="zorluk_orta"),
            InlineKeyboardButton("🔴 Zor", callback_data="zorluk_zor"),
        ],
        [
            InlineKeyboardButton("🏠 Ana Menü", callback_data="menu_home"),
        ]
    ]

    text = (
        "🎮 *OYUN MENÜSÜ*\n\n"
        "Bir kategori seç.\n"
        "Zorluk ayarlayıp oyunu başlatabilirsin.\n\n"
        "🟢 Kolay • 🟡 Orta • 🔴 Zor"
    )

    await query.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat = query.message.chat.id
    secim = query.data
    user = update.effective_user
    chat_type = query.message.chat.type

    if "zorluk" not in context.user_data:
        context.user_data["zorluk"] = "kolay"

    if secim == "menu_home":
        await query.message.reply_text(
            main_menu_text(user.first_name, is_group=chat_type in ["group", "supergroup"]),
            reply_markup=build_main_menu(),
            parse_mode="Markdown"
        )
        return

    if secim == "menu_games":
        await oyun_menusu(query)
        return

    if secim.startswith("zorluk_"):
        level = secim.split("_", 1)[1]
        context.user_data["zorluk"] = level
        await query.message.reply_text(f"🎚️ Zorluk ayarlandı: *{level.capitalize()}*", parse_mode="Markdown")
        return

    if secim == "game_stop":
        if chat in oyunlar:
            if "task" in oyunlar[chat] and oyunlar[chat]["task"]:
                oyunlar[chat]["task"].cancel()
            del oyunlar[chat]
        await query.message.reply_text("🛑 Oyun durduruldu.")
        return

    if secim == "game_next":
        if chat not in oyunlar:
            await query.message.reply_text("❌ Aktif oyun yok.")
            return
        oyunlar[chat]["aktif"] = False
        oyunlar[chat]["qid"] = random.randint(10000000, 99999999)
        await query.message.reply_text("⏭️ Sonraki soru hazırlanıyor...")
        return

    if secim == "game_hint":
        if chat not in oyunlar or not oyunlar[chat]["aktif"]:
            await query.message.reply_text("❌ Aktif bir soru yok.")
            return

        if oyunlar[chat]["hint_used"]:
            await query.message.reply_text("❌ Bu soru için zaten ipucu kullandın.")
            return

        ok = use_hint(user.id, user.first_name)
        if not ok:
            await query.message.reply_text("❌ İpucu hakkın yok. Marketten satın alabilirsin.")
            return

        oyun = oyunlar[chat].get("oyun", oyunlar[chat]["kategori"])
        cevap = oyunlar[chat]["cevap"]
        hint = get_hint_text(oyun, cevap)
        oyunlar[chat]["hint_used"] = True

        await query.message.reply_text(hint, parse_mode="Markdown")
        return

    if secim.startswith("quiz_"):
        if chat not in oyunlar or not oyunlar[chat]["aktif"]:
            await query.message.reply_text("❌ Aktif quiz sorusu yok.")
            return

        if oyunlar[chat].get("oyun") != "quiz":
            await query.message.reply_text("❌ Şu an aktif soru quiz değil.")
            return

        verilen = secim.split("_", 1)[1].upper()
        cevap = oyunlar[chat]["cevap"].upper()

        if verilen == cevap:
            elapsed = time.time() - oyunlar[chat]["baslangic"]
            zorluk = oyunlar[chat].get("zorluk", "kolay")
            points, xp, coins = calc_rewards(elapsed, zorluk)

            add_reward(user.id, user.first_name, points, xp, coins)
            add_group_score(chat, user.id, user.first_name, points)

            profile = get_profile(user.id, user.first_name)
            name, total_points, total_xp, total_coins, daily_correct, streak, total_correct, last_daily, hint_count, x2_xp, x2_coin = profile
            lvl = get_level(total_xp)

            await query.message.reply_text(
                f"🎉 *{name}* doğru şıkkı seçti!\n\n"
                f"⏱️ Süre: `{elapsed:.2f}` sn\n"
                f"🏆 Puan: `+{points}`\n"
                f"⭐ XP: `+{xp}`\n"
                f"💰 Coin: `+{coins}`\n\n"
                f"📊 *Durumun*\n"
                f"🏅 Toplam Puan: `{total_points}`\n"
                f"🆙 Level: `{lvl}`\n"
                f"🔥 Streak: `{streak}`",
                parse_mode="Markdown"
            )
            oyunlar[chat]["aktif"] = False
        else:
            await query.message.reply_text("❌ Yanlış cevap! Tekrar dene.")
        return

    if secim == "menu_profil":
        profile = get_profile(user.id, user.first_name)
        name, points, xp, coins, daily_correct, streak, total_correct, last_daily, hint_count, x2_xp, x2_coin = profile
        lvl = get_level(xp)

        await query.message.reply_text(
            f"👤 *Profilin*\n\n"
            f"🙍 İsim: *{name}*\n"
            f"🏆 Puan: `{points}`\n"
            f"⭐ XP: `{xp}`\n"
            f"🆙 Level: `{lvl}`\n"
            f"💰 Coin: `{coins}`\n"
            f"🔥 Streak: `{streak}`\n"
            f"💡 İpucu: `{hint_count}`\n"
            f"⚡ x2 XP: `{x2_xp}`\n"
            f"💸 x2 Coin: `{x2_coin}`\n"
            f"✅ Günlük Doğru: `{daily_correct}`\n"
            f"📚 Toplam Doğru: `{total_correct}`",
            parse_mode="Markdown"
        )
        return

    if secim == "menu_top":
        rows = top_users(10)
        if not rows:
            await query.message.reply_text("🏆 Henüz global liderlik verisi yok.")
            return

        text = "🏆 *GLOBAL LİDERLİK*\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, (name, points) in enumerate(rows, start=1):
            medal = medals[i - 1] if i <= 3 else f"{i}."
            text += f"{medal} {name} — *{points}* puan\n"
        await query.message.reply_text(text, parse_mode="Markdown")
        return

    if secim == "menu_gtop":
        rows = get_group_top(chat, 10)
        if not rows:
            await query.message.reply_text("👥 Bu grup için henüz liderlik verisi yok.")
            return

        text = "👥 *GRUP LİDERLİĞİ*\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(rows, start=1):
            medal = medals[i - 1] if i <= 3 else f"{i}."
            text += f"{medal} {row['name']} — *{row['points']}* puan\n"
        await query.message.reply_text(text, parse_mode="Markdown")
        return

    if secim == "menu_daily":
        ok, remain = claim_daily(user.id, user.first_name)
        if ok:
            await query.message.reply_text("🎁 Günlük ödül alındı!\n💰 +25 coin\n⭐ +10 XP")
        else:
            saat = remain // 3600
            dakika = (remain % 3600) // 60
            await query.message.reply_text(f"⏳ Günlük ödül için beklemen gerekiyor.\nYaklaşık: {saat} saat {dakika} dakika")
        return

    if secim == "menu_market":
        text = (
            "🛒 *Market*\n\n"
            "💡 İpucu — 10 coin\n"
            "⚡ x2 XP (5 soru) — 50 coin\n"
            "💸 x2 Coin (5 soru) — 50 coin"
        )
        keyboard = [
            [InlineKeyboardButton("💡 İpucu Al", callback_data="buy_hint")],
            [InlineKeyboardButton("⚡ x2 XP Al", callback_data="buy_x2_xp")],
            [InlineKeyboardButton("💸 x2 Coin Al", callback_data="buy_x2_coin")],
            [InlineKeyboardButton("🏠 Ana Menü", callback_data="menu_home")],
        ]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if secim == "menu_achievements":
        achievements = get_achievements(user.id, user.first_name)
        if not achievements:
            text = "🏅 Henüz başarım açmadın."
        else:
            text = "🏅 *Başarımların*\n\n" + "\n".join(f"• {a}" for a in achievements)
        await query.message.reply_text(text, parse_mode="Markdown")
        return

    if secim.startswith("buy_"):
        item = secim.replace("buy_", "")
        success, msg = buy_item(user.id, user.first_name, item)
        if success:
            await query.message.reply_text(f"✅ Satın alma başarılı: `{item}`", parse_mode="Markdown")
        else:
            await query.message.reply_text(f"❌ {msg}")
        return

    if chat in oyunlar and "task" in oyunlar[chat]:
        oyunlar[chat]["task"].cancel()

    oyunlar[chat] = {
        "kategori": secim,
        "aktif": False,
        "cevap": None,
        "baslangic": None,
        "task": None,
        "qid": 0,
        "zorluk": context.user_data.get("zorluk", "kolay"),
        "hint_used": False,
        "starter_name": user.first_name,
        "used_questions": deque(maxlen=20),
        "last_wrong_attempts": {},
    }

    kategori_adi = {
        "karisik": "🎲 Karışık",
        "kelime": "🔤 Kelime",
        "plaka": "🚗 Plaka",
        "emoji": "😀 Emoji",
        "bayrak": "🌍 Bayrak",
        "mat": "🧠 Matematik",
        "quiz": "❓ Quiz"
    }.get(secim, secim)

    await query.message.reply_text(
        f"{kategori_adi} modu başladı!\n"
        f"👤 Başlatan: *{user.first_name}*\n"
        f"🎚️ Zorluk: *{oyunlar[chat]['zorluk'].capitalize()}*\n"
        f"🚀 Hazır olun!",
        parse_mode="Markdown"
    )

    task = context.application.create_task(oyun_loop(chat, context.application))
    oyunlar[chat]["task"] = task

async def soru(chat, app):
    if chat not in oyunlar:
        return

    kat = oyunlar[chat]["kategori"]
    zorluk = oyunlar[chat].get("zorluk", "kolay")
    used = oyunlar[chat]["used_questions"]
    oyun = random.choice(["kelime", "plaka", "mat", "emoji", "bayrak", "quiz"]) if kat == "karisik" else kat

    cevap = None
    soru_text = None

    if oyun == "kelime":
        if not kelimeler:
            await app.bot.send_message(chat, "❌ Kelime verisi bulunamadı. Oyun durduruldu.")
            if "task" in oyunlar[chat] and oyunlar[chat]["task"]:
                oyunlar[chat]["task"].cancel()
            del oyunlar[chat]
            return

        uygun = kelimeler
        if zorluk == "kolay":
            uygun = [k for k in kelimeler if 3 <= len(k) <= 5] or kelimeler
        elif zorluk == "orta":
            uygun = [k for k in kelimeler if 6 <= len(k) <= 8] or kelimeler
        elif zorluk == "zor":
            uygun = [k for k in kelimeler if len(k) >= 9] or kelimeler

        k = choose_non_repeating(uygun, used, lambda x: f"kelime:{x}")
        cevap = k
        soru_text = (
            f"🔤 *Kelime Oyunu*\n\n"
            f"🌀 Karışık harfler: `{make_scrambled_word(k)}`\n\n"
            f"👤 Başlatan: *{oyunlar[chat]['starter_name']}*\n"
            f"👥 İlk doğru yazan kazanır!\n"
            f"⏳ {QUESTION_TIME} saniye içinde cevap ver."
        )

    elif oyun == "plaka":
        item = choose_non_repeating(list(plakalar.items()), used, lambda x: f"plaka:{x[0]}")
        p, s = item
        cevap = s.lower()
        soru_text = (
            f"🚗 *Plaka Sorusu*\n\n"
            f"📍 `{p}` plakası hangi şehre ait?\n\n"
            f"👤 Başlatan: *{oyunlar[chat]['starter_name']}*\n"
            f"👥 İlk doğru yazan kazanır!\n"
            f"⏳ {QUESTION_TIME} saniye içinde cevap ver."
        )

    elif oyun == "mat":
        if zorluk == "kolay":
            a = random.randint(10, 30); b = random.randint(10, 30)
        elif zorluk == "orta":
            a = random.randint(20, 70); b = random.randint(20, 70)
        else:
            a = random.randint(50, 200); b = random.randint(50, 200)

        expr_key = f"mat:{a}+{b}"
        if expr_key in used:
            a += random.randint(1, 7)
            b += random.randint(1, 9)
            expr_key = f"mat:{a}+{b}"
        used.append(expr_key)

        cevap = str(a + b)
        soru_text = (
            f"🧠 *Matematik Sorusu*\n\n"
            f"➕ `{a} + {b} = ?`\n\n"
            f"👤 Başlatan: *{oyunlar[chat]['starter_name']}*\n"
            f"👥 İlk doğru yazan kazanır!\n"
            f"⏳ {QUESTION_TIME} saniye içinde cevap ver."
        )

    elif oyun == "emoji":
        if not emoji:
            await app.bot.send_message(chat, "❌ Emoji verisi bulunamadı. Oyun durduruldu.")
            if "task" in oyunlar[chat] and oyunlar[chat]["task"]:
                oyunlar[chat]["task"].cancel()
            del oyunlar[chat]
            return

        item = choose_non_repeating(list(emoji.items()), used, lambda x: f"emoji:{x[0]}")
        e, c = item
        cevap = c.lower()
        soru_text = (
            f"😀 *Emoji Tahmini*\n\n{e}\n\n"
            f"👤 Başlatan: *{oyunlar[chat]['starter_name']}*\n"
            f"👥 İlk doğru yazan kazanır!\n"
            f"⏳ {QUESTION_TIME} saniye içinde cevap ver."
        )

    elif oyun == "bayrak":
        if not bayrak:
            await app.bot.send_message(chat, "❌ Bayrak verisi bulunamadı. Oyun durduruldu.")
            if "task" in oyunlar[chat] and oyunlar[chat]["task"]:
                oyunlar[chat]["task"].cancel()
            del oyunlar[chat]
            return

        item = choose_non_repeating(list(bayrak.items()), used, lambda x: f"bayrak:{x[0]}")
        b, c = item
        cevap = c.lower()
        soru_text = (
            f"🌍 *Bayrak Tahmini*\n\n{b}\n\n"
            f"👤 Başlatan: *{oyunlar[chat]['starter_name']}*\n"
            f"👥 İlk doğru yazan kazanır!\n"
            f"⏳ {QUESTION_TIME} saniye içinde cevap ver."
        )

    elif oyun == "quiz":
        if not quizler:
            await app.bot.send_message(chat, "❌ Quiz verisi bulunamadı. Oyun durduruldu.")
            if "task" in oyunlar[chat] and oyunlar[chat]["task"]:
                oyunlar[chat]["task"].cancel()
            del oyunlar[chat]
            return

        q = choose_non_repeating(quizler, used, lambda x: f"quiz:{x['soru']}")
        cevap = q["dogru"]
        secenekler = q["secenekler"]
        soru_text = (
            f"❓ *4 Şıklı Quiz*\n\n"
            f"📘 {q['soru']}\n\n"
            f"🅰️ {secenekler[0]}\n"
            f"🅱️ {secenekler[1]}\n"
            f"🇨 {secenekler[2]}\n"
            f"🇩 {secenekler[3]}\n\n"
            f"👤 Başlatan: *{oyunlar[chat]['starter_name']}*\n"
            f"👥 İlk doğru butona basan kazanır!"
        )

    if not cevap:
        return

    qid = random.randint(1000, 9999999)
    oyunlar[chat]["aktif"] = True
    oyunlar[chat]["cevap"] = cevap.strip()
    oyunlar[chat]["baslangic"] = time.time()
    oyunlar[chat]["qid"] = qid
    oyunlar[chat]["oyun"] = oyun
    oyunlar[chat]["hint_used"] = False
    oyunlar[chat]["last_wrong_attempts"] = {}

    if oyun == "quiz":
        keyboard = [
            [
                InlineKeyboardButton("🅰️ A", callback_data="quiz_A"),
                InlineKeyboardButton("🅱️ B", callback_data="quiz_B"),
            ],
            [
                InlineKeyboardButton("🇨 C", callback_data="quiz_C"),
                InlineKeyboardButton("🇩 D", callback_data="quiz_D"),
            ],
            [
                InlineKeyboardButton("💡 İpucu", callback_data="game_hint"),
                InlineKeyboardButton("⏭️ Sonraki", callback_data="game_next"),
            ],
            [
                InlineKeyboardButton("🛑 Durdur", callback_data="game_stop"),
            ]
        ]
        await app.bot.send_message(chat, soru_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        keyboard = [
            [
                InlineKeyboardButton("💡 İpucu", callback_data="game_hint"),
                InlineKeyboardButton("⏭️ Sonraki", callback_data="game_next"),
            ],
            [
                InlineKeyboardButton("🛑 Durdur", callback_data="game_stop"),
                InlineKeyboardButton("🏠 Ana Menü", callback_data="menu_home"),
            ]
        ]
        await app.bot.send_message(chat, soru_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    await asyncio.sleep(QUESTION_TIME)

    if chat not in oyunlar:
        return
    if oyunlar[chat]["qid"] != qid:
        return

    if oyunlar[chat]["aktif"]:
        await app.bot.send_message(chat, f"⏰ Süre doldu.\n✅ Cevap: *{cevap}*\n\n⏭️ Yeni soru geliyor...", parse_mode="Markdown")
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
    user = update.effective_user

    if chat not in oyunlar:
        return
    if not oyunlar[chat]["aktif"]:
        return
    if not update.message or not update.message.text:
        return

    if oyunlar[chat].get("oyun") == "quiz":
        return

    text = normalize(update.message.text)
    cevap = normalize(oyunlar[chat]["cevap"])

    if text == cevap:
        elapsed = time.time() - oyunlar[chat]["baslangic"]
        zorluk = oyunlar[chat].get("zorluk", "kolay")
        points, xp, coins = calc_rewards(elapsed, zorluk)

        add_reward(user.id, user.first_name, points, xp, coins)
        add_group_score(chat, user.id, user.first_name, points)

        profile = get_profile(user.id, user.first_name)
        name, total_points, total_xp, total_coins, daily_correct, streak, total_correct, last_daily, hint_count, x2_xp, x2_coin = profile
        lvl = get_level(total_xp)

        await update.message.reply_text(
            f"🎉 *{name}* doğru cevap verdi!\n\n"
            f"⏱️ Süre: `{elapsed:.2f}` sn\n"
            f"🏆 Puan: `+{points}`\n"
            f"⭐ XP: `+{xp}`\n"
            f"💰 Coin: `+{coins}`\n\n"
            f"📊 *Durumun*\n"
            f"🏅 Toplam Puan: `{total_points}`\n"
            f"🆙 Level: `{lvl}`\n"
            f"🔥 Streak: `{streak}`",
            parse_mode="Markdown"
        )
        oyunlar[chat]["aktif"] = False
        return

    # yanlış cevap spam koruması
    now = time.time()
    user_id = str(user.id)
    last_try = oyunlar[chat]["last_wrong_attempts"].get(user_id, 0)

    if now - last_try < 2:
        return

    oyunlar[chat]["last_wrong_attempts"][user_id] = now

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
    name, points, xp, coins, daily_correct, streak, total_correct, last_daily, hint_count, x2_xp, x2_coin = profile
    lvl = get_level(xp)

    await update.message.reply_text(
        f"👤 *Kullanıcı Profili*\n\n"
        f"🙍 İsim: *{name}*\n"
        f"🏆 Puan: `{points}`\n"
        f"⭐ XP: `{xp}`\n"
        f"🆙 Level: `{lvl}`\n"
        f"💰 Coin: `{coins}`\n"
        f"🔥 Streak: `{streak}`\n"
        f"💡 İpucu: `{hint_count}`\n"
        f"⚡ x2 XP: `{x2_xp}`\n"
        f"💸 x2 Coin: `{x2_coin}`\n"
        f"✅ Günlük Doğru: `{daily_correct}`\n"
        f"📚 Toplam Doğru: `{total_correct}`",
        parse_mode="Markdown"
    )

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = top_users(20)
    if not rows:
        await update.message.reply_text("Henüz global liderlik verisi yok.")
        return

    text = "🏆 *GLOBAL LİDERLİK*\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (name, points) in enumerate(rows, start=1):
        medal = medals[i - 1] if i <= 3 else f"{i}."
        text += f"{medal} {name} — *{points}* puan\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def gtop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat.id
    rows = get_group_top(chat, 20)
    if not rows:
        await update.message.reply_text("👥 Bu grup için henüz liderlik verisi yok.")
        return

    text = "👥 *GRUP LİDERLİĞİ*\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, row in enumerate(rows, start=1):
        medal = medals[i - 1] if i <= 3 else f"{i}."
        text += f"{medal} {row['name']} — *{row['points']}* puan\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def gunluk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ok, remain = claim_daily(user.id, user.first_name)
    if ok:
        await update.message.reply_text("🎁 Günlük ödül alındı!\n💰 +25 coin\n⭐ +10 XP")
    else:
        saat = remain // 3600
        dakika = (remain % 3600) // 60
        await update.message.reply_text(f"⏳ Günlük ödül hazır değil.\nKalan süre: {saat} saat {dakika} dakika")

async def market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🛒 *Market*\n\n"
        "💡 İpucu — 10 coin\n"
        "⚡ x2 XP (5 soru) — 50 coin\n"
        "💸 x2 Coin (5 soru) — 50 coin\n\n"
        "Satın alma için:\n"
        "`/satin_al hint`\n"
        "`/satin_al x2_xp`\n"
        "`/satin_al x2_coin`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def satin_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Kullanım: /satin_al hint")
        return
    item = context.args[0].strip().lower()
    success, msg = buy_item(user.id, user.first_name, item)
    if success:
        await update.message.reply_text(f"✅ Satın alma başarılı: {item}")
    else:
        await update.message.reply_text(f"❌ {msg}")

async def ipucu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat.id

    if chat not in oyunlar or not oyunlar[chat]["aktif"]:
        await update.message.reply_text("❌ Aktif bir soru yok.")
        return

    if oyunlar[chat]["hint_used"]:
        await update.message.reply_text("❌ Bu soru için zaten ipucu kullandın.")
        return

    ok = use_hint(user.id, user.first_name)
    if not ok:
        await update.message.reply_text("❌ İpucu hakkın yok. Marketten satın alabilirsin.")
        return

    oyun = oyunlar[chat].get("oyun", oyunlar[chat]["kategori"])
    cevap = oyunlar[chat]["cevap"]
    hint = get_hint_text(oyun, cevap)
    oyunlar[chat]["hint_used"] = True

    await update.message.reply_text(hint, parse_mode="Markdown")

async def basarim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    achievements = get_achievements(user.id, user.first_name)
    if not achievements:
        await update.message.reply_text("🏅 Henüz başarım açmadın.")
        return
    text = "🏅 *Başarımların*\n\n" + "\n".join(f"• {a}" for a in achievements)
    await update.message.reply_text(text, parse_mode="Markdown")

async def yardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *Yardım Menüsü*\n\n"
        "🎮 /start - Ana menü\n"
        "👤 /profil - Profilin\n"
        "🏆 /top - Global liderlik\n"
        "👥 /gtop - Grup liderliği\n"
        "🎁 /gunluk - Günlük ödül\n"
        "🛒 /market - Market\n"
        "💡 /ipucu - Aktif soru için ipucu\n"
        "🏅 /basarim - Başarımlar\n"
        "🛑 /son - Oyunu durdur\n\n"
        "👥 Bu bot gruplarda çalışır. Herkes oyunu başlatabilir.",
        parse_mode="Markdown"
    )

def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("son", son))
    app.add_handler(CommandHandler("stop", son))
    app.add_handler(CommandHandler("profil", profil))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("gtop", gtop))
    app.add_handler(CommandHandler("gunluk", gunluk))
    app.add_handler(CommandHandler("market", market))
    app.add_handler(CommandHandler("satin_al", satin_al))
    app.add_handler(CommandHandler("ipucu", ipucu))
    app.add_handler(CommandHandler("basarim", basarim))
    app.add_handler(CommandHandler("yardim", yardim))

    app.add_handler(CallbackQueryHandler(kategori))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mesaj))

    print("🔥 BOT AKTİF 🔥")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
