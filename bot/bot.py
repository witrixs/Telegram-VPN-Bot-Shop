from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from database.db import add_user, update_user_subscription
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

# Главное меню
main_menu = InlineKeyboardMarkup(row_width=2)
main_menu.add(
    InlineKeyboardButton("Купить подписку", callback_data="buy_subscription"),
    InlineKeyboardButton("Личный кабинет", callback_data="profile")
)

# Меню подписки
subscription_menu = InlineKeyboardMarkup(row_width=1)
subscription_menu.add(
    InlineKeyboardButton("1 месяц - 300 руб.", callback_data="buy_month"),
    InlineKeyboardButton("1 год - 3650 руб.", callback_data="buy_year"),
    InlineKeyboardButton("Назад", callback_data="back_to_main")
)

# Меню личного кабинета
def profile_menu(telegram_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT subscription_type, subscription_end FROM users WHERE telegram_id = ?", (telegram_id,))
    user = c.fetchone()
    conn.close()
    
    menu = InlineKeyboardMarkup(row_width=1)
    if user and user[1] and user[1] > datetime.now().strftime('%Y-%m-%d %H:%M:%S'):
        subscription_url = get_marzban_subscription_url(telegram_id)
        menu.add(
            InlineKeyboardButton("Открыть подписку", web_app=WebAppInfo(url=subscription_url)),
            InlineKeyboardButton("Назад", callback_data="back_to_main")
        )
    else:
        menu.add(
            InlineKeyboardButton("Продлить подписку", callback_data="buy_subscription"),
            InlineKeyboardButton("Назад", callback_data="back_to_main")
        )
    return menu

async def update_message(chat_id, text, reply_markup=None):
    last_message_id = last_message_ids[chat_id]
    if last_message_id:
        try:
            # Пробуем отредактировать существующее сообщение
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=last_message_id,
                text=text,
                reply_markup=reply_markup
            )
        except Exception:
            # Если редактирование не удалось (например, сообщение удалено), отправляем новое
            sent_message = await bot.send_message(chat_id, text, reply_markup=reply_markup)
            last_message_ids[chat_id] = sent_message.message_id
    else:
        # Если сообщения еще нет, отправляем новое
        sent_message = await bot.send_message(chat_id, text, reply_markup=reply_markup)
        last_message_ids[chat_id] = sent_message.message_id

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    user_id = str(message.from_user.id)
    first_name = message.from_user.first_name
    username = message.from_user.username
    add_user(user_id, first_name, username)
    
    welcome_text = (
        "Добро пожаловать в Rafaello VPN PAY Shlyz!\n\n"
        "Мы предоставляем надежный и быстрый VPN-сервис для вашей безопасности и свободы в интернете."
    )
    await update_message(message.chat.id, welcome_text, reply_markup=main_menu)

@dp.callback_query_handler(lambda c: c.data == "buy_subscription")
async def process_buy_subscription(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    await bot.answer_callback_query(callback_query.id)
    await update_message(chat_id, "Выберите тариф:", reply_markup=subscription_menu)

@dp.callback_query_handler(lambda c: c.data in ["buy_month", "buy_year"])
async def process_payment(callback_query: types.CallbackQuery):
    user_id = str(callback_query.from_user.id)
    chat_id = callback_query.message.chat.id
    amount = 300.00 if callback_query.data == "buy_month" else 3650.00
    days = 30 if callback_query.data == "buy_month" else 365
    subscription_type = "month" if callback_query.data == "buy_month" else "year"

    payment = Payment.create({
        "amount": {"value": str(amount), "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://t.me/your_bot_username"},
        "capture": True,
        "description": f"Подписка {subscription_type} для {user_id}",
        "metadata": {"user_id": user_id},
        "save_payment_method": True
    })

    await bot.answer_callback_query(callback_query.id)
    payment_text = f"Оплатите подписку ({subscription_type}) по ссылке:\n{payment.confirmation.confirmation_url}"
    await update_message(chat_id, payment_text, reply_markup=main_menu)

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
        profile_text = "У вас нет активной подписки. Продлите её, чтобы получить доступ к VPN!"
    
    await bot.answer_callback_query(callback_query.id)
    await update_message(chat_id, profile_text, reply_markup=profile_menu(user_id))

@dp.callback_query_handler(lambda c: c.data == "back_to_main")
async def process_back_to_main(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    await bot.answer_callback_query(callback_query.id)
    await update_message(chat_id, "Главное меню:", reply_markup=main_menu)

@dp.message_handler()
async def handle_any_message(message: types.Message):
    error_text = "Пожалуйста, используйте команды или кнопки для взаимодействия с ботом."
    await update_message(message.chat.id, error_text, reply_markup=main_menu)

async def on_startup(_):
    print("Бот запущен")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)