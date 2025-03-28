# 📊 Telegram VPN Bot Shop

> Телегрм бот для продажи VPN подписок с веб админ панелью на Python

## Требования

1. Pyhton 3.11.9+
2. Aiogram 2.25.1
3. Flask 2.3.2
4. YooKassa 2.3.1

## 🚀 Запуск приложения

>Запуск всего проекта
```sh
pip install -r requirements.txt
python main.py
```

## ⚙️ Конфигурация

Скопировать и переименовать `.env.example` в `.env` и заполните значения:

⚠️ **Примечание. Никогда не делитесь публично своим токеном или ключами API.** ⚠️

```.env
TELEGRAM_TOKEN=your_token_telegram
SHOP_ID=your_shop_id
SECRET_KEY=secret_key
VITE_BASE_API="https://your-marzban.com/api/"
MARZBAN_USERNAME=your_user
MARZBAN_PASSWORD=your_pass
DATABASE_PATH=/root/your-project/database/users.db
WEBHOOK_URL=https://your-site.com/webhook
```
⚠️ **Примечание. Для работы нужен сервер Marzban и его настройка.** ⚠️

## ⚙️ Доп. Настройка

⚠️ **Настройка шаблона платежки** ⚠️
>Расположение /bot/bot.py
```
    # Создаём новый платёж
    payment = Payment.create({
        "amount": {"value": str(amount), "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://t.me/your_bot_username"},
        "capture": True,
        "description": f"Подписка {subscription_type} для {user_id}",
        "metadata": {"user_id": user_id},
        "save_payment_method": True
    })
```
⚠️ **Установка на production при помощи Nginx 1.24.0** ⚠️

## ❤️ Dev by witrix
