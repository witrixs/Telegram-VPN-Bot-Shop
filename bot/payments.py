from yookassa import Configuration, Payment
from dotenv import load_dotenv
import os

load_dotenv()

Configuration.account_id = os.getenv('YOOKASSA_SHOP_ID')
Configuration.secret_key = os.getenv('YOOKASSA_SECRET_KEY')

def create_payment(amount, user_id):
    payment = Payment.create({
        "amount": {"value": str(amount), "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://127.0.0.1:5000/success"},
        "description": f"Подписка для Telegram ID {user_id}",
        "metadata": {"user_id": str(user_id)}
    })
    return payment.confirmation.confirmation_url