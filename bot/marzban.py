import requests
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

MARZBAN_API_URL = os.getenv("VITE_BASE_API")
MARZBAN_USERNAME = os.getenv("MARZBAN_USERNAME")
MARZBAN_PASSWORD = os.getenv("MARZBAN_PASSWORD")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 1440))

if not MARZBAN_API_URL or MARZBAN_API_URL == "None":
    raise ValueError("MARZBAN_API_URL не задан в .env или имеет некорректное значение")

MARZBAN_API_URL = MARZBAN_API_URL.rstrip('/')
print(f"Используется MARZBAN_API_URL: {MARZBAN_API_URL}")

MARZBAN_TOKEN = None
TOKEN_EXPIRY = None

def get_marzban_token():
    global MARZBAN_TOKEN, TOKEN_EXPIRY
    current_time = datetime.now()

    if not MARZBAN_TOKEN or (TOKEN_EXPIRY and current_time >= TOKEN_EXPIRY):
        url = f"{MARZBAN_API_URL}/admin/token"
        print(f"Запрос токена: {url}")
        response = requests.post(
            url,
            data={"username": MARZBAN_USERNAME, "password": MARZBAN_PASSWORD}
        )
        print(f"Ответ на запрос токена: {response.status_code} - {response.text}")
        if response.status_code == 200:
            MARZBAN_TOKEN = response.json()["access_token"]
            TOKEN_EXPIRY = current_time + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
            print(f"Токен получен: {MARZBAN_TOKEN[:10]}...")
        else:
            raise Exception(f"Ошибка получения токена: {response.status_code} - {response.text}")
    return MARZBAN_TOKEN

def create_marzban_subscription(telegram_id, days):
    token = get_marzban_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "username": f"witrix_{telegram_id}",
        "expire": int((datetime.now() + timedelta(days=days)).timestamp()),
        "data_limit": 0,
        "proxies": {"vless": {}, "vmess": {}},
        "status": "active"
    }
    
    url = f"{MARZBAN_API_URL}/user"
    print(f"Создание пользователя: {url} с данными {payload}")
    response = requests.post(url, headers=headers, json=payload)
    print(f"Ответ от сервера: {response.status_code} - {response.text}")
    
    if response.status_code in (200, 201):
        data = response.json()
        return data.get("subscription_url", f"{MARZBAN_API_URL}/sub/witrix_{telegram_id}")
    else:
        raise Exception(f"Ошибка создания пользователя: {response.status_code} - {response.text}")

def update_marzban_subscription(telegram_id, additional_days):
    token = get_marzban_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    url = f"{MARZBAN_API_URL}/user/witrix_{telegram_id}"
    print(f"Получение данных пользователя: {url}")
    response = requests.get(url, headers=headers)
    print(f"Ответ: {response.status_code} - {response.text}")
    if response.status_code != 200:
        raise Exception(f"Пользователь не найден: {response.status_code} - {response.text}")
    
    user_data = response.json()
    current_expire = datetime.fromtimestamp(user_data["expire"]) if user_data["expire"] else datetime.now()
    new_expire = current_expire + timedelta(days=additional_days)
    
    payload = {
        "expire": int(new_expire.timestamp()),
        "data_limit": user_data["data_limit"],
        "proxies": user_data["proxies"],
        "status": "active"
    }
    
    print(f"Обновление пользователя: {url} с данными {payload}")
    response = requests.put(url, headers=headers, json=payload)
    print(f"Ответ: {response.status_code} - {response.text}")
    if response.status_code == 200:
        data = response.json()
        return data.get("subscription_url", f"{MARZBAN_API_URL}/sub/witrix_{telegram_id}")
    else:
        raise Exception(f"Ошибка обновления пользователя: {response.status_code} - {response.text}")

def delete_marzban_user(telegram_id):
    token = get_marzban_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    url = f"{MARZBAN_API_URL}/user/witrix_{telegram_id}"
    print(f"Удаление пользователя: {url}")
    response = requests.delete(url, headers=headers)
    print(f"Ответ: {response.status_code} - {response.text}")
    if response.status_code == 200:
        return True
    else:
        raise Exception(f"Ошибка удаления пользователя: {response.status_code} - {response.text}")

def get_marzban_subscription_url(telegram_id):
    token = get_marzban_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    url = f"{MARZBAN_API_URL}/user/witrix_{telegram_id}"
    print(f"Получение ссылки на подписку: {url}")
    response = requests.get(url, headers=headers)
    print(f"Ответ: {response.status_code} - {response.text}")
    if response.status_code == 200:
        data = response.json()
        return data.get("subscription_url", f"{MARZBAN_API_URL}/sub/witrix_{telegram_id}")
    else:
        raise Exception(f"Ошибка получения ссылки: {response.status_code} - {response.text}")

def pause_marzban_subscription(telegram_id):
    token = get_marzban_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    url = f"{MARZBAN_API_URL}/user/witrix_{telegram_id}"
    print(f"Получение данных пользователя для паузы: {url}")
    response = requests.get(url, headers=headers)
    print(f"Ответ: {response.status_code} - {response.text}")
    if response.status_code != 200:
        raise Exception(f"Пользователь не найден: {response.status_code} - {response.text}")
    
    user_data = response.json()
    payload = {
        "expire": user_data["expire"],
        "data_limit": user_data["data_limit"],
        "proxies": user_data["proxies"],
        "status": "disabled"  # Приостанавливаем подписку
    }
    
    print(f"Приостановка пользователя: {url} с данными {payload}")
    response = requests.put(url, headers=headers, json=payload)
    print(f"Ответ: {response.status_code} - {response.text}")
    if response.status_code != 200:
        raise Exception(f"Ошибка приостановки пользователя: {response.status_code} - {response.text}")