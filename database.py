import sqlite3
import time

DB_NAME = "bot.db"

def get_conn():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        name TEXT,
        points INTEGER DEFAULT 0,
        xp INTEGER DEFAULT 0,
        coins INTEGER DEFAULT 0,
        daily_correct INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        total_correct INTEGER DEFAULT 0,
        last_daily INTEGER DEFAULT 0,
        hint_count INTEGER DEFAULT 0,
        x2_xp INTEGER DEFAULT 0,
        x2_coin INTEGER DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()

def ensure_user(user_id, name):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT OR IGNORE INTO users
    (user_id, name, points, xp, coins, daily_correct, streak, total_correct, last_daily, hint_count, x2_xp, x2_coin)
    VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    """, (str(user_id), name))
    conn.commit()
    conn.close()

def get_profile(user_id, name):
    ensure_user(user_id, name)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT name, points, xp, coins, daily_correct, streak, total_correct, last_daily, hint_count, x2_xp, x2_coin
    FROM users WHERE user_id = ?
    """, (str(user_id),))
    row = cur.fetchone()
    conn.close()
    return row

def add_reward(user_id, name, points=5, xp=3, coins=2):
    ensure_user(user_id, name)
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT x2_xp, x2_coin FROM users WHERE user_id = ?", (str(user_id),))
    row = cur.fetchone()
    x2_xp = row[0] if row else 0
    x2_coin = row[1] if row else 0

    if x2_xp > 0:
        xp *= 2
        x2_xp -= 1

    if x2_coin > 0:
        coins *= 2
        x2_coin -= 1

    cur.execute("""
    UPDATE users
    SET name = ?,
        points = points + ?,
        xp = xp + ?,
        coins = coins + ?,
        daily_correct = daily_correct + 1,
        streak = streak + 1,
        total_correct = total_correct + 1,
        x2_xp = ?,
        x2_coin = ?
    WHERE user_id = ?
    """, (name, points, xp, coins, x2_xp, x2_coin, str(user_id)))

    conn.commit()
    conn.close()

def get_level(xp):
    return xp // 50 + 1

def top_users(limit=20):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT name, points FROM users
    ORDER BY points DESC
    LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def claim_daily(user_id, name):
    ensure_user(user_id, name)
    now = int(time.time())

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT last_daily FROM users WHERE user_id = ?", (str(user_id),))
    row = cur.fetchone()
    last_daily = row[0] if row else 0

    if now - last_daily < 86400:
        conn.close()
        return False, 86400 - (now - last_daily)

    cur.execute("""
    UPDATE users
    SET coins = coins + 25,
        xp = xp + 10,
        last_daily = ?
    WHERE user_id = ?
    """, (now, str(user_id)))

    conn.commit()
    conn.close()
    return True, 0

def buy_item(user_id, name, item):
    ensure_user(user_id, name)
    prices = {
        "hint": 10,
        "x2_xp": 50,
        "x2_coin": 50
    }

    if item not in prices:
        return False, "Geçersiz ürün."

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT coins, hint_count, x2_xp, x2_coin FROM users WHERE user_id = ?", (str(user_id),))
    row = cur.fetchone()

    if not row:
        conn.close()
        return False, "Kullanıcı bulunamadı."

    coins, hint_count, x2_xp, x2_coin = row
    price = prices[item]

    if coins < price:
        conn.close()
        return False, "Yeterli coin yok."

    coins -= price

    if item == "hint":
        hint_count += 1
    elif item == "x2_xp":
        x2_xp += 5
    elif item == "x2_coin":
        x2_coin += 5

    cur.execute("""
    UPDATE users
    SET coins = ?, hint_count = ?, x2_xp = ?, x2_coin = ?
    WHERE user_id = ?
    """, (coins, hint_count, x2_xp, x2_coin, str(user_id)))

    conn.commit()
    conn.close()
    return True, f"{item} satın alındı."

def use_hint(user_id, name):
    ensure_user(user_id, name)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT hint_count FROM users WHERE user_id = ?", (str(user_id),))
    row = cur.fetchone()

    if not row or row[0] <= 0:
        conn.close()
        return False

    cur.execute("""
    UPDATE users
    SET hint_count = hint_count - 1
    WHERE user_id = ?
    """, (str(user_id),))

    conn.commit()
    conn.close()
    return True

def get_achievements(user_id, name):
    ensure_user(user_id, name)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT coins, total_correct, streak, xp
    FROM users WHERE user_id = ?
    """, (str(user_id),))
    row = cur.fetchone()
    conn.close()

    if not row:
        return []

    coins, total_correct, streak, xp = row
    achievements = []

    if total_correct >= 1:
        achievements.append("🥉 İlk Doğru")
    if total_correct >= 10:
        achievements.append("🥈 10 Doğru")
    if total_correct >= 50:
        achievements.append("🥇 50 Doğru")
    if total_correct >= 100:
        achievements.append("👑 100 Doğru Ustası")
    if coins >= 100:
        achievements.append("💰 100 Coin Sahibi")
    if streak >= 5:
        achievements.append("🔥 5 Streak")
    if streak >= 10:
        achievements.append("🚀 10 Streak")
    if xp >= 100:
        achievements.append("⭐ 100 XP")
    if xp >= 500:
        achievements.append("🌟 500 XP")

    return achievements
