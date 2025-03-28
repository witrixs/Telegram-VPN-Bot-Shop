from flask import Flask, render_template, request, redirect, url_for, flash, session
from database.db import get_users, update_user_subscription, get_admin, log_transaction, get_transactions, get_stats, check_expired_subscriptions, reset_subscription
from dotenv import load_dotenv
import os
import hashlib
from bot.bot import bot
from bot.marzban import create_marzban_subscription, update_marzban_subscription, delete_marzban_user, pause_marzban_subscription
from yookassa import Configuration, Payment
import asyncio
import threading
import time
import sqlite3
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='templates/static')
app.secret_key = os.urandom(24)

Configuration.account_id = os.getenv('SHOP_ID')
Configuration.secret_key = os.getenv('SECRET_KEY')

def auto_renew_subscriptions():
    while True:
        expired_users = check_expired_subscriptions()
        for telegram_id, subscription_type, payment_method_id in expired_users:
            days = 30 if subscription_type == "month" else 365
            amount = 300.00 if subscription_type == "month" else 3650.00
            attempts = 0
            max_attempts = 3

            while attempts < max_attempts:
                payment = Payment.create({
                    "amount": {"value": str(amount), "currency": "RUB"},
                    "payment_method_id": payment_method_id,
                    "description": f"Автопродление подписки ({subscription_type}) для {telegram_id}",
                    "metadata": {"user_id": telegram_id}
                })
                
                if payment.status == "succeeded":
                    subscription_url = update_marzban_subscription(telegram_id, days)
                    end_date = update_user_subscription(telegram_id, subscription_type, days, payment_method_id)
                    log_transaction(telegram_id, "success", f"Автоплатеж: подписка {subscription_type} продлена до {end_date}")
                    loop = bot.loop
                    asyncio.run_coroutine_threadsafe(bot.send_message(telegram_id, f"Ваша подписка автоматически продлена!\nСсылка на подписку: {subscription_url}"), loop)
                    break
                else:
                    attempts += 1
                    log_transaction(telegram_id, "error", f"Ошибка автоплатежа (попытка {attempts}/{max_attempts}): {payment.status}")
                    time.sleep(300)

            if attempts == max_attempts:
                reset_subscription(telegram_id)
                log_transaction(telegram_id, "error", "Автоплатеж не удался после 3 попыток, подписка обнулена")
                loop = bot.loop
                asyncio.run_coroutine_threadsafe(bot.send_message(telegram_id, "Ваша подписка закончилась, автоплатеж не удался. Продлите её вручную в личном кабинете!"), loop)

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT telegram_id, subscription_end FROM users WHERE subscription_end < ? AND subscription_end IS NOT NULL", 
                  ((datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S'),))
        expired_long = c.fetchall()
        conn.close()

        for telegram_id, subscription_end in expired_long:
            try:
                delete_marzban_user(telegram_id)
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
                conn.commit()
                conn.close()
                log_transaction(telegram_id, "success", "Пользователь удален из системы и Marzban через 3 дня после окончания подписки")
            except Exception as e:
                log_transaction(telegram_id, "error", f"Ошибка удаления пользователя: {str(e)}")

        time.sleep(3600)

@app.route('/')
def index():
    if 'admin' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = get_admin(username)
        if admin and hashlib.sha256(password.encode()).hexdigest() == admin[2]:
            session['admin'] = username
            flash('Вы успешно вошли!', 'success')
            return redirect(url_for('dashboard'))
        flash('Неверный логин или пароль', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'admin' not in session:
        return redirect(url_for('login'))
    
    period = request.args.get('period', 'all')
    stats = get_stats(period)
    transactions = get_transactions()
    all_users = get_users()

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_subscription':
            telegram_id = request.form.get('telegram_id')
            subscription_type = request.form.get('subscription_type')
            if telegram_id and subscription_type:
                days = 30 if subscription_type == "month" else 365
                try:
                    conn = sqlite3.connect('users.db')
                    c = conn.cursor()
                    c.execute("SELECT subscription_end FROM users WHERE telegram_id = ?", (telegram_id,))
                    existing = c.fetchone()
                    conn.close()

                    if existing and existing[0] and existing[0] > datetime.now().strftime('%Y-%m-%d %H:%M:%S'):
                        subscription_url = update_marzban_subscription(telegram_id, days)
                    else:
                        subscription_url = create_marzban_subscription(telegram_id, days)
                    
                    end_date = update_user_subscription(telegram_id, subscription_type, days)
                    log_transaction(telegram_id, "success", f"Подписка {subscription_type} создана вручную до {end_date}")
                    flash(f'Подписка для {telegram_id} создана: {subscription_type}', 'success')
                    loop = bot.loop
                    asyncio.run_coroutine_threadsafe(bot.send_message(telegram_id, f"Ваша подписка ({subscription_type}) активирована!\nСсылка на подписку: {subscription_url}"), loop)
                except Exception as e:
                    log_transaction(telegram_id, "error", f"Ошибка создания подписки: {str(e)}")
                    flash(f'Ошибка при создании подписки: {str(e)}', 'error')
            else:
                flash('Выберите пользователя и тип подписки', 'error')
        
        elif action == 'extend':
            telegram_id = request.form.get('telegram_id')
            days = request.form.get('days', type=int)
            if telegram_id and days:
                subscription_url = create_marzban_subscription(telegram_id, days)
                end_date = update_user_subscription(telegram_id, "manual", days)
                log_transaction(telegram_id, "success", f"Подписка продлена вручную на {days} дней до {end_date}")
                flash(f'Подписка для {telegram_id} продлена на {days} дней', 'success')
        
        return redirect(url_for('dashboard', period=period))
    
    return render_template('dashboard.html', stats=stats, transactions=transactions, users=all_users, period=period)

@app.route('/users', methods=['GET', 'POST'])
def users():
    if 'admin' not in session:
        return redirect(url_for('login'))
    
    all_users = get_users()
    search_query = request.args.get('search', '').lower()
    page = request.args.get('page', 1, type=int)
    per_page = 10

    if search_query:
        all_users = [u for u in all_users if search_query in (u[1].lower() + (u[2] or '').lower() + (u[3] or '').lower())]

    total_users = len(all_users)
    total_pages = (total_users + per_page - 1) // per_page
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    paginated_users = all_users[start:end]

    if request.method == 'POST':
        telegram_id = request.form.get('telegram_id')
        action = request.form.get('action')
        
        if action == 'extend':
            days = request.form.get('days', type=int)
            if telegram_id and days:
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute("SELECT subscription_end FROM users WHERE telegram_id = ?", (telegram_id,))
                existing = c.fetchone()
                if existing and existing[0] and existing[0] > datetime.now().strftime('%Y-%m-%d %H:%M:%S'):
                    subscription_url = update_marzban_subscription(telegram_id, days)
                else:
                    subscription_url = create_marzban_subscription(telegram_id, days)
                end_date = update_user_subscription(telegram_id, "manual", days)
                log_transaction(telegram_id, "success", f"Подписка продлена вручную на {days} дней до {end_date}")
                flash(f'Подписка для {telegram_id} продлена на {days} дней', 'success')
                conn.close()
        
        elif action == 'pause':  # Заменяем reset на pause
            pause_marzban_subscription(telegram_id)
            log_transaction(telegram_id, "success", "Подписка приостановлена")
            flash(f'Подписка для {telegram_id} приостановлена', 'success')

        elif action == 'delete':
            delete_marzban_user(telegram_id)
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
            conn.commit()
            conn.close()
            log_transaction(telegram_id, "success", "Пользователь полностью удален")
            flash(f'Пользователь {telegram_id} удален', 'success')

        return redirect(url_for('users', page=page, search=search_query))

    return render_template(
        'users.html',
        users=paginated_users,
        search_query=search_query,
        page=page,
        per_page=per_page,
        total_users=total_users
    )

@app.route('/webhook', methods=['POST'])
async def webhook():
    data = request.json
    if data['event'] == 'payment.succeeded':
        user_id = data['object']['metadata']['user_id']
        amount = float(data['object']['amount']['value'])
        days = 30 if amount == 300 else 365
        subscription_type = "month" if amount == 300 else "year"
        payment_method_id = data['object']['payment_method']['id']

        log_transaction(user_id, "processing", f"Обработка платежа на {amount} руб.")
        try:
            subscription_url = create_marzban_subscription(user_id, days)
            end_date = update_user_subscription(user_id, subscription_type, days, payment_method_id)
            log_transaction(user_id, "success", f"Подписка {subscription_type} активирована до {end_date} с автоплатежом")
            await bot.send_message(
                user_id,
                f"Подписка успешно активирована с автоплатежом!\n"
                f"Ваша ссылка на подписку: {subscription_url}\n"
                "Перейдите по ссылке для инструкций и ключей."
            )
        except Exception as e:
            log_transaction(user_id, "error", str(e))
            await bot.send_message(user_id, "Ошибка при активации подписки, обратитесь в поддержку.")
    return '', 200

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    threading.Thread(target=auto_renew_subscriptions, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)