from flask import Flask, render_template, request, redirect, url_for, flash, session
from database.db import get_users, update_user_subscription, get_admin, log_transaction, get_transactions, get_stats, check_expired_subscriptions, reset_subscription, get_marzban_username, get_tariff_price, update_tariff_price
from dotenv import load_dotenv
import os
import hashlib
from bot.bot import bot  # Импортируем bot из bot/bot.py
from bot.marzban import create_marzban_subscription, update_marzban_subscription, delete_marzban_user
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

# Создаём цикл событий один раз для всего приложения
loop = asyncio.get_event_loop()

# Функция для выполнения асинхронных задач в существующем цикле событий
def run_async(coro):
    asyncio.ensure_future(coro, loop=loop)

async def send_telegram_message(telegram_id, message):
    try:
        await bot.send_message(telegram_id, message)
    except Exception as e:
        print(f"Ошибка отправки сообщения в Telegram: {e}")

def auto_renew_subscriptions():
    while True:
        expired_users = check_expired_subscriptions()
        for telegram_id, subscription_type, payment_method_id in expired_users:
            days = 30 if subscription_type == "month" else 365
            amount = get_tariff_price(subscription_type)
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
                    username = get_marzban_username(telegram_id)
                    subscription_url = update_marzban_subscription(username, days)
                    end_date = update_user_subscription(telegram_id, subscription_type, days, payment_method_id)
                    log_transaction(telegram_id, "success", f"Автоплатеж: подписка {subscription_type} продлена до {end_date}")
                    run_async(send_telegram_message(telegram_id, f"Ваша подписка автоматически продлена!\nСсылка на подписку: {subscription_url}"))
                    break
                else:
                    attempts += 1
                    log_transaction(telegram_id, "error", f"Ошибка автоплатежа (попытка {attempts}/{max_attempts}): {payment.status}")
                    time.sleep(300)

            if attempts == max_attempts:
                reset_subscription(telegram_id)
                log_transaction(telegram_id, "error", "Автоплатеж не удался после 3 попыток, подписка обнулена")
                run_async(send_telegram_message(telegram_id, "Ваша подписка закончилась, автоплатеж не удался. Продлите её вручную в личном кабинете!"))

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT telegram_id, subscription_end FROM users WHERE subscription_end < ? AND subscription_end IS NOT NULL", 
                  ((datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S'),))
        expired_long = c.fetchall()
        conn.close()

        for telegram_id, subscription_end in expired_long:
            try:
                username = get_marzban_username(telegram_id)
                delete_marzban_user(username)
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

@app.route('/dashboard', methods=['GET'])
def dashboard():
    if 'admin' not in session:
        return redirect(url_for('login'))
    
    period = request.args.get('period', 'all')
    stats = get_stats(period)
    
    all_transactions = get_transactions(limit=None)
    page = request.args.get('page', 1, type=int)
    per_page = 10
    total_transactions = len(all_transactions)
    total_pages = (total_transactions + per_page - 1) // per_page
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    paginated_transactions = all_transactions[start:end]

    all_users = get_users()

    return render_template(
        'dashboard.html', 
        stats=stats, 
        transactions=paginated_transactions, 
        users=all_users, 
        period=period, 
        page=page, 
        per_page=per_page, 
        total_transactions=total_transactions
    )

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
        
        if action == 'create_subscription':
            subscription_type = request.form.get('subscription_type')
            if telegram_id and subscription_type:
                days = 30 if subscription_type == "month" else 365
                try:
                    conn = sqlite3.connect('users.db')
                    c = conn.cursor()
                    c.execute("SELECT subscription_end FROM users WHERE telegram_id = ?", (telegram_id,))
                    existing = c.fetchone()
                    conn.close()

                    username = get_marzban_username(telegram_id)
                    if existing and existing[0] and existing[0] > datetime.now().strftime('%Y-%m-%d %H:%M:%S'):
                        subscription_url = update_marzban_subscription(username, days)
                    else:
                        subscription_url = create_marzban_subscription(username, days)
                    
                    end_date = update_user_subscription(telegram_id, subscription_type, days)
                    log_transaction(telegram_id, "success", f"Подписка {subscription_type} создана вручную до {end_date}")
                    flash(f'Подписка для {telegram_id} создана: {subscription_type}', 'success')
                    run_async(send_telegram_message(telegram_id, f"Ваша подписка ({subscription_type}) активирована!\nСсылка на подписку: {subscription_url}"))
                except Exception as e:
                    log_transaction(telegram_id, "error", f"Ошибка создания подписки: {str(e)}")
                    flash(f'Ошибка при создании подписки: {str(e)}', 'error')
            else:
                flash('Выберите пользователя и тип подписки', 'error')

        elif action == 'extend':
            days = request.form.get('days', type=int)
            if telegram_id and days:
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute("SELECT subscription_end FROM users WHERE telegram_id = ?", (telegram_id,))
                existing = c.fetchone()
                username = get_marzban_username(telegram_id)
                if existing and existing[0] and existing[0] > datetime.now().strftime('%Y-%m-%d %H:%M:%S'):
                    subscription_url = update_marzban_subscription(username, days)
                else:
                    subscription_url = create_marzban_subscription(username, days)
                end_date = update_user_subscription(telegram_id, "manual", days)
                log_transaction(telegram_id, "success", f"Подписка продлена вручную на {days} дней до {end_date}")
                flash(f'Подписка для {telegram_id} продлена на {days} дней', 'success')
                conn.close()

        elif action == 'delete':
            try:
                username = get_marzban_username(telegram_id)
                delete_marzban_user(username)
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
                conn.commit()
                conn.close()
                log_transaction(telegram_id, "success", "Пользователь полностью удален")
                flash(f'Пользователь {telegram_id} удален', 'success')
            except Exception as e:
                log_transaction(telegram_id, "error", f"Ошибка удаления пользователя: {str(e)}")
                flash(f'Ошибка при удалении пользователя: {str(e)}', 'error')

        return redirect(url_for('users', page=page, search=search_query))

    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return render_template(
        'users.html',
        users=paginated_users,
        search_query=search_query,
        page=page,
        per_page=per_page,
        total_users=total_users,
        current_time=current_time
    )

@app.route('/edit_tariffs', methods=['GET', 'POST'])
def edit_tariffs():
    if 'admin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        monthly_price = float(request.form['monthly_price'])
        yearly_price = float(request.form['yearly_price'])

        try:
            update_tariff_price('month', monthly_price)
            update_tariff_price('year', yearly_price)
            flash('Цены тарифов успешно обновлены!', 'success')
        except Exception as e:
            flash(f'Ошибка обновления цен тарифов: {str(e)}', 'error')

        return redirect(url_for('dashboard'))

    monthly_price = get_tariff_price('month') or 300
    yearly_price = get_tariff_price('year') or 3650

    return render_template('edit_tariffs.html', monthly_price=monthly_price, yearly_price=yearly_price)

@app.route('/webhook', methods=['POST'])
async def webhook():
    data = request.json
    if data['event'] == 'payment.succeeded':
        user_id = data['object']['metadata']['user_id']
        amount = float(data['object']['amount']['value'])
        days = 30 if amount == get_tariff_price('month') else 365
        subscription_type = "month" if amount == get_tariff_price('month') else "year"
        payment_method_id = data['object']['payment_method']['id']

        log_transaction(user_id, "processing", f"Обработка платежа на {amount} руб.")
        try:
            username = get_marzban_username(user_id)
            subscription_url = create_marzban_subscription(username, days)
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
    # Запускаем цикл событий в отдельном потоке
    threading.Thread(target=lambda: loop.run_forever(), daemon=True).start()
    threading.Thread(target=auto_renew_subscriptions, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)