from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from database.db import add_user, update_user_subscription, get_tariff_price, get_marzban_username, add_pending_payment, get_pending_payment, remove_pending_payment
from dotenv import load_dotenv
import os
from yookassa import Configuration, Payment
from bot.marzban import create_marzban_subscription, get_marzban_subscription_url
from datetime import datetime
import sqlite3
from collections import defaultdict

load_dotenv()

bot = Bot(token=os.getenv('TELEGRAM_TOKEN'))
dp = Dispatcher(bot)

Configuration.account_id = os.getenv('SHOP_ID')
Configuration.secret_key = os.getenv('SECRET_KEY')

# Хранилище ID последнего сообщения для каждого чата
last_message_ids = defaultdict(lambda: None)

# Функция проверки активной подписки
def has_active_subscription(telegram_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT subscription_end FROM users WHERE telegram_id = ?", (telegram_id,))
    user = c.fetchone()
    conn.close()
    return user and user[0] and user[0] > datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# Динамическое главное меню
def get_main_menu(telegram_id):
    main_menu = InlineKeyboardMarkup(row_width=2)
    if not has_active_subscription(telegram_id):
        main_menu.add(
            InlineKeyboardButton("Купить подписку", callback_data="buy_subscription")
        )
    main_menu.add(
        InlineKeyboardButton("Личный кабинет", callback_data="profile")
    )
    return main_menu

# Меню подписки с динамическими целыми ценами
def get_subscription_menu():
    month_price = int(get_tariff_price('month') or 300)
    year_price = int(get_tariff_price('year') or 3650)
    subscription_menu = InlineKeyboardMarkup(row_width=1)
    subscription_menu.add(
        InlineKeyboardButton(f"1 месяц - {month_price} руб.", callback_data="buy_month"),
        InlineKeyboardButton(f"1 год - {year_price} руб.", callback_data="buy_year"),
        InlineKeyboardButton("Назад", callback_data="back_to_main")
    )
    return subscription_menu

# Меню личного кабинета
def profile_menu(telegram_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT subscription_type, subscription_end FROM users WHERE telegram_id = ?", (telegram_id,))
    user = c.fetchone()
    conn.close()
    
    menu = InlineKeyboardMarkup(row_width=1)
    if user and user[1] and user[1] > datetime.now().strftime('%Y-%m-%d %H:%M:%S'):
        username = get_marzban_username(telegram_id)
        subscription_url = get_marzban_subscription_url(username)
        menu.add(
            InlineKeyboardButton("Открыть подписку", url=subscription_url),
            InlineKeyboardButton("Назад", callback_data="back_to_main")
        )
    else:
        menu.add(
            InlineKeyboardButton("Купить подписку", callback_data="buy_subscription"),
            InlineKeyboardButton("Назад", callback_data="back_to_main")
        )
    return menu

# Меню оплаты с кнопками "Оплатить" и "Проверить платеж"
def get_payment_menu(confirmation_url, payment_id):
    payment_menu = InlineKeyboardMarkup(row_width=1)
    payment_menu.add(
        InlineKeyboardButton("Оплатить", url=confirmation_url),
        InlineKeyboardButton("Проверить платеж", callback_data=f"check_payment_{payment_id}"),
        InlineKeyboardButton("Назад", callback_data="back_to_main")
    )
    return payment_menu

async def update_message(chat_id, text, reply_markup=None):
    last_message_id = last_message_ids[chat_id]
    try:
        if last_message_id:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=last_message_id,
                text=text,
                reply_markup=reply_markup
            )
        else:
            sent_message = await bot.send_message(chat_id, text, reply_markup=reply_markup)
            last_message_ids[chat_id] = sent_message.message_id
    except Exception:
        sent_message = await bot.send_message(chat_id, text, reply_markup=reply_markup)
        last_message_ids[chat_id] = sent_message.message_id

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    user_id = str(message.from_user.id)
    first_name = message.from_user.first_name
    username = message.from_user.username
    add_user(user_id, first_name, username)
    
    welcome_text = (
        "Добро пожаловать в Rafaello VPN!\n\n"
        "Мы предоставляем надежный и быстрый VPN-сервис для вашей безопасности и свободы в интернете."
    )
    await update_message(message.chat.id, welcome_text, reply_markup=get_main_menu(user_id))

@dp.callback_query_handler(lambda c: c.data == "buy_subscription")
async def process_buy_subscription(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    await bot.answer_callback_query(callback_query.id)
    await update_message(chat_id, "Выберите тариф:", reply_markup=get_subscription_menu())

@dp.callback_query_handler(lambda c: c.data in ["buy_month", "buy_year"])
async def process_payment(callback_query: types.CallbackQuery):
    user_id = str(callback_query.from_user.id)
    chat_id = callback_query.message.chat.id
    
    month_price = int(get_tariff_price('month') or 300)
    year_price = int(get_tariff_price('year') or 3650)
    
    amount = month_price if callback_query.data == "buy_month" else year_price
    days = 30 if callback_query.data == "buy_month" else 365
    subscription_type = "month" if callback_query.data == "buy_month" else "year"

    # Проверяем, есть ли незавершённый платёж
    pending_payment = get_pending_payment(user_id)
    if pending_payment:
        payment_id, existing_type, existing_amount, confirmation_url = pending_payment
        payment_text = f"Оплатите подписку ({existing_type}):"
        await update_message(chat_id, payment_text, reply_markup=get_payment_menu(confirmation_url, payment_id))
        await bot.answer_callback_query(callback_query.id)
        return

    # Создаём новый платёж
    payment = Payment.create({
        "amount": {"value": str(amount), "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://t.me/your_bot_username"},
        "capture": True,
        "description": f"Подписка {subscription_type} для {user_id}",
        "metadata": {"user_id": user_id},
        "save_payment_method": True
    })

    add_pending_payment(user_id, payment.id, subscription_type, amount, payment.confirmation.confirmation_url)
    payment_text = f"Оплатите подписку ({subscription_type}):"
    await update_message(chat_id, payment_text, reply_markup=get_payment_menu(payment.confirmation.confirmation_url, payment.id))
    await bot.answer_callback_query(callback_query.id)

@dp.callback_query_handler(lambda c: c.data.startswith("check_payment_"))
async def check_payment(callback_query: types.CallbackQuery):
    user_id = str(callback_query.from_user.id)
    chat_id = callback_query.message.chat.id
    payment_id = callback_query.data.split("_")[2]

    pending_payment = get_pending_payment(user_id)
    if not pending_payment or pending_payment[0] != payment_id:
        await bot.answer_callback_query(callback_query.id, text="Этот платёж не найден или уже обработан.")
        await update_message(chat_id, "Главное меню:", reply_markup=get_main_menu(user_id))
        return

    payment = Payment.find_one(payment_id)
    if payment.status == "succeeded":
        # Используем subscription_type из pending_payment, а не вычисляем заново
        payment_id, subscription_type, amount, confirmation_url = pending_payment
        days = 30 if subscription_type == "month" else 365
        
        username = get_marzban_username(user_id)
        subscription_url = create_marzban_subscription(username, days)
        end_date = update_user_subscription(user_id, subscription_type, days, payment.payment_method.id)
        remove_pending_payment(user_id, payment_id)
        
        profile_text = (
            f"Ваш личный кабинет:\n"
            f"Тариф: {subscription_type}\n"
            f"Дата окончания: {end_date}"
        )
        await bot.answer_callback_query(callback_query.id, text="Платёж подтверждён!")
        await update_message(chat_id, profile_text, reply_markup=profile_menu(user_id))
    else:
        await bot.answer_callback_query(callback_query.id, text="Платёж ещё не подтверждён. Попробуйте позже.")
        payment_text = f"Оплатите подписку ({pending_payment[1]}):"
        await update_message(chat_id, payment_text, reply_markup=get_payment_menu(pending_payment[3], payment_id))

@dp.callback_query_handler(lambda c: c.data == "profile")
async def process_profile(callback_query: types.CallbackQuery):
    user_id = str(callback_query.from_user.id)
    chat_id = callback_query.message.chat.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT subscription_type, subscription_end FROM users WHERE telegram_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()

    if user and user[1] and user[1] > datetime.now().strftime('%Y-%m-%d %H:%M:%S'):
        subscription_type = user[0]
        end_date = user[1]
        days_left = (datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S') - datetime.now()).days
        profile_text = (
            f"Ваш личный кабинет:\n"
            f"Тариф: {subscription_type}\n"
            f"Осталось дней: {days_left}\n"
            f"Дата окончания: {end_date}"
        )
    else:
        profile_text = "У вас нет активной подписки. Купите подписку, чтобы получить доступ к VPN!"
    
    await bot.answer_callback_query(callback_query.id)
    await update_message(chat_id, profile_text, reply_markup=profile_menu(user_id))

@dp.callback_query_handler(lambda c: c.data == "back_to_main")
async def process_back_to_main(callback_query: types.CallbackQuery):
    user_id = str(callback_query.from_user.id)
    chat_id = callback_query.message.chat.id
    await bot.answer_callback_query(callback_query.id)
    await update_message(chat_id, "Главное меню:", reply_markup=get_main_menu(user_id))

@dp.message_handler()
async def handle_any_message(message: types.Message):
    user_id = str(message.from_user.id)
    error_text = "Пожалуйста, используйте команды или кнопки для взаимодействия с ботом."
    await update_message(message.chat.id, error_text, reply_markup=get_main_menu(user_id))

async def on_startup(_):
    print("Бот запущен")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)