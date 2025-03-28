import sqlite3
from datetime import datetime, timedelta
import hashlib

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, telegram_id TEXT UNIQUE, first_name TEXT, username TEXT, 
                  subscription_type TEXT, subscription_end TEXT, payment_method_id TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS admins 
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY, telegram_id TEXT, status TEXT, message TEXT, timestamp TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS tariffs 
                 (type TEXT PRIMARY KEY, price REAL NOT NULL)''')

    default_admin_username = "admin"
    default_admin_password = "admin"
    hashed_password = hashlib.sha256(default_admin_password.encode()).hexdigest()
    
    c.execute("SELECT * FROM admins WHERE username = ?", (default_admin_username,))
    if not c.fetchone():
        c.execute("INSERT INTO admins (username, password) VALUES (?, ?)", 
                  (default_admin_username, hashed_password))
        print(f"Администратор '{default_admin_username}' создан с паролем '{default_admin_password}' (хеширован).")

    c.execute("INSERT OR IGNORE INTO tariffs (type, price) VALUES (?, ?)", ("month", 300))
    c.execute("INSERT OR IGNORE INTO tariffs (type, price) VALUES (?, ?)", ("year", 3650))
    
    conn.commit()
    conn.close()

def add_user(telegram_id, first_name, username):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (telegram_id, first_name, username) VALUES (?, ?, ?)", 
              (telegram_id, first_name, username))
    conn.commit()
    conn.close()

def update_user_subscription(telegram_id, subscription_type, days, payment_method_id=None):
    end_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET subscription_type = ?, subscription_end = ?, payment_method_id = ? WHERE telegram_id = ?", 
              (subscription_type, end_date, payment_method_id, telegram_id))
    conn.commit()
    conn.close()
    return end_date

def get_users():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    users = c.fetchall()
    conn.close()
    return users

def get_admin(username):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM admins WHERE username = ?", (username,))
    admin = c.fetchone()
    conn.close()
    return admin

def log_transaction(telegram_id, status, message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT INTO transactions (telegram_id, status, message, timestamp) VALUES (?, ?, ?, ?)", 
              (telegram_id, status, message, timestamp))
    conn.commit()
    conn.close()

def get_transactions(limit=None):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    if limit:
        c.execute("SELECT * FROM transactions ORDER BY timestamp DESC LIMIT ?", (limit,))
    else:
        c.execute("SELECT * FROM transactions ORDER BY timestamp DESC")
    transactions = c.fetchall()
    conn.close()
    return transactions

def get_stats(period="all"):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    year_start = datetime(now.year, 1, 1).strftime('%Y-%m-%d %H:%M:%S')
    month_start = datetime(now.year, now.month, 1).strftime('%Y-%m-%d %H:%M:%S')
    week_start = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d %H:%M:%S')
    day_start = datetime(now.year, now.month, now.day).strftime('%Y-%m-%d %H:%M:%S')

    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE subscription_end > ?", (now_str,))
    active_subscriptions = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE subscription_end < ? AND subscription_end IS NOT NULL", (now_str,))
    expired_subscriptions = c.fetchone()[0]

    c.execute("SELECT subscription_type, subscription_end FROM users WHERE subscription_end IS NOT NULL")
    subscriptions = c.fetchall()

    total_revenue = 0
    yearly_revenue = 0
    monthly_revenue = 0
    weekly_revenue = 0
    daily_revenue = 0

    month_price = get_tariff_price('month') or 300
    year_price = get_tariff_price('year') or 3650

    for sub_type, sub_end in subscriptions:
        amount = month_price if sub_type == 'month' else year_price if sub_type == 'year' else 0
        sub_end_date = datetime.strptime(sub_end, '%Y-%m-%d %H:%M:%S')
        
        total_revenue += amount
        if sub_end_date >= datetime.strptime(year_start, '%Y-%m-%d %H:%M:%S'):
            yearly_revenue += amount
        if sub_end_date >= datetime.strptime(month_start, '%Y-%m-%d %H:%M:%S'):
            monthly_revenue += amount
        if sub_end_date >= datetime.strptime(week_start, '%Y-%m-%d %H:%M:%S'):
            weekly_revenue += amount
        if sub_end_date >= datetime.strptime(day_start, '%Y-%m-%d %H:%M:%S'):
            daily_revenue += amount

    conn.close()
    return {
        "total_users": total_users,
        "active_subscriptions": active_subscriptions,
        "expired_subscriptions": expired_subscriptions,
        "total_revenue": total_revenue,
        "yearly_revenue": yearly_revenue,
        "monthly_revenue": monthly_revenue,
        "weekly_revenue": weekly_revenue,
        "daily_revenue": daily_revenue
    }

def check_expired_subscriptions():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT telegram_id, subscription_type, payment_method_id FROM users WHERE subscription_end < ? AND payment_method_id IS NOT NULL", 
              (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),))
    expired = c.fetchall()
    conn.close()
    return expired

def reset_subscription(telegram_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET subscription_type = NULL, subscription_end = NULL, payment_method_id = NULL WHERE telegram_id = ?", 
              (telegram_id,))
    conn.commit()
    conn.close()

def get_marzban_username(telegram_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE telegram_id = ?", (telegram_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else telegram_id

def get_tariff_price(tariff_type):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT price FROM tariffs WHERE type = ?", (tariff_type,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def update_tariff_price(tariff_type, price):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO tariffs (type, price) VALUES (?, ?)", (tariff_type, price))
    conn.commit()
    conn.close()