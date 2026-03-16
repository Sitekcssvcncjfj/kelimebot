import sqlite3

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
        total_correct INTEGER DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),))
    row = cur.fetchone()
    conn.close()
    return row

def create_user(user_id, name):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT OR IGNORE INTO users (user_id, name, points, xp, coins, daily_correct, streak, total_correct)
    VALUES (?, ?, 0, 0, 0, 0, 0, 0)
    """, (str(user_id), name))
    conn.commit()
    conn.close()

def ensure_user(user_id, name):
    create_user(user_id, name)

def add_reward(user_id, name, points=5, xp=3, coins=2):
    ensure_user(user_id, name)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    UPDATE users
    SET name = ?,
        points = points + ?,
        xp = xp + ?,
        coins = coins + ?,
        daily_correct = daily_correct + 1,
        streak = streak + 1,
        total_correct = total_correct + 1
    WHERE user_id = ?
    """, (name, points, xp, coins, str(user_id)))
    conn.commit()
    conn.close()

def get_profile(user_id, name):
    ensure_user(user_id, name)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT name, points, xp, coins, daily_correct, streak, total_correct
    FROM users WHERE user_id = ?
    """, (str(user_id),))
    row = cur.fetchone()
    conn.close()
    return row

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

def level_from_xp(xp):
    return xp // 50 + 1
