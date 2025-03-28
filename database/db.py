import sqlite3
from datetime import datetime, timedelta
import hashlib

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Создание таблицы users
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, telegram_id TEXT UNIQUE, first_name TEXT, username TEXT, 
                  subscription_type TEXT, subscription_end TEXT, payment_method_id TEXT)''')
    
    # Создание таблицы admins
    c.execute('''CREATE TABLE IF NOT EXISTS admins 
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT)''')
    
    # Создание таблицы transactions
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY, telegram_id TEXT, status TEXT, message TEXT, timestamp TEXT)''')
    
    # Проверка и добавление администратора admin:admin
    default_admin_username = "admin"
    default_admin_password = "admin"
    hashed_password = hashlib.sha256(default_admin_password.encode()).hexdigest()
    
    c.execute("SELECT * FROM admins WHERE username = ?", (default_admin_username,))
    if not c.fetchone():  # Если админ не существует
        c.execute("INSERT INTO admins (username, password) VALUES (?, ?)", 
                  (default_admin_username, hashed_password))
        print(f"Администратор '{default_admin_username}' создан с паролем '{default_admin_password}' (хеширован).")
    
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

def get_transactions():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM transactions ORDER BY timestamp DESC LIMIT 10")
    transactions = c.fetchall()
    conn.close()
    return transactions

def get_stats(period="all"):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Определяем временной диапазон
    now = datetime.now()
    if period == "year":
        start_date = (now - timedelta(days=365)).strftime('%Y-%m-%d %H:%M:%S')
    elif period == "month":
        start_date = (now - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    elif period == "week":
        start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    elif period == "day":
        start_date = (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    else:
        start_date = None

    # Общее количество пользователей
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]

    # Активные подписки
    c.execute("SELECT COUNT(*) FROM users WHERE subscription_end > ?", (now.strftime('%Y-%m-%d %H:%M:%S'),))
    active_subscriptions = c.fetchone()[0]

    # Просроченные подписки
    c.execute("SELECT COUNT(*) FROM users WHERE subscription_end < ? AND subscription_end IS NOT NULL", 
              (now.strftime('%Y-%m-%d %H:%M:%S'),))
    expired_subscriptions = c.fetchone()[0]

    # Выручка
    if start_date:
        c.execute("SELECT SUM(CASE WHEN subscription_type = 'month' THEN 300 ELSE 3650 END) FROM users WHERE subscription_end > ? AND subscription_end <= ?", 
                  (start_date, now.strftime('%Y-%m-%d %H:%M:%S')))
    else:
        c.execute("SELECT SUM(CASE WHEN subscription_type = 'month' THEN 300 ELSE 3650 END) FROM users WHERE subscription_end IS NOT NULL")
    total_revenue = c.fetchone()[0] or 0

    conn.close()
    return {
        "total_users": total_users,
        "active_subscriptions": active_subscriptions,
        "total_revenue": total_revenue,
        "expired_subscriptions": expired_subscriptions
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