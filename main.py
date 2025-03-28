from bot.bot import dp, bot
from web.app import app
from database.db import init_db
import asyncio
from aiogram.utils import executor
import threading

async def on_startup(_):
    init_db()
    print("Бот и база данных запущены")

def run_flask():
    app.run(port=5000)

if __name__ == '__main__':
    init_db()
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)