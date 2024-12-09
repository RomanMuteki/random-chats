from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis.asyncio as redis  # Используем асинхронный клиент Redis
import json
import os
import logging
from fastapi.middleware.cors import CORSMiddleware



logging.basicConfig(level=logging.INFO)

CONFIG_FILE = 'config.json'

if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"Файл конфигурации {CONFIG_FILE} не найден.")

with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

REDIS_HOST = config.get('redis_host', 'localhost')
REDIS_PORT = config.get('redis_port', 6379)
REDIS_DB = config.get('redis_db', 0)

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True
)

app = FastAPI(title="WebSocket Manager")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешает доступ с любых доменов
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Connection(BaseModel):
    user_id: str
    websocket_handler_id: str


class User(BaseModel):
    user_id: str


class HandlerRegistration(BaseModel):
    websocket_handler_id: str
    websocket_handler_url: str


@app.post("/register_handler")
async def register_handler(handler: HandlerRegistration):
    """
    Регистрирует WebSocket Handler с его URL.

    :param handler: Объект, содержащий идентификатор и URL WebSocket Handler.
    :return: Статус регистрации и информация об обработчике.
    """
    handler_key = f"handler:{handler.websocket_handler_id}:url"
    await r.set(handler_key, handler.websocket_handler_url)
    logging.info(f"Обработчик {handler.websocket_handler_id} зарегистрирован с URL {handler.websocket_handler_url}")
    return {
        "status": "registered",
        "websocket_handler_id": handler.websocket_handler_id,
        "websocket_handler_url": handler.websocket_handler_url
    }


@app.get("/handler_url/{handler_id}")
async def get_handler_url(handler_id: str):
    """
    Получает URL WebSocket Handler по его ID.

    :param handler_id: Идентификатор WebSocket Handler.
    :return: URL WebSocket Handler.
    """
    handler_key = f"handler:{handler_id}:url"
    url = await r.get(handler_key)
    if not url:
        raise HTTPException(status_code=404, detail="WebSocket Handler не найден")
    return {
        "websocket_handler_id": handler_id,
        "websocket_handler_url": url
    }


@app.post("/connect")
async def connect_user(connection: Connection):
    """
    Регистрирует подключение пользователя к WebSocket обработчику.

    :param connection: Объект, содержащий идентификатор пользователя и WebSocket обработчика.
    :return: Статус подключения и идентификаторы пользователя и обработчика.
    """
    user_key = f"user:{connection.user_id}"
    handler_key = f"WSH:{connection.websocket_handler_id}:connected_users"

    # Проверка, был ли пользователь подключен ранее
    previous_handler_id = await r.get(user_key)

    # Если пользователь был подключен к другому обработчику, удаляем его оттуда
    if previous_handler_id and previous_handler_id != connection.websocket_handler_id:
        prev_handler_key = f"WSH:{previous_handler_id}:connected_users"
        await r.srem(prev_handler_key, connection.user_id)

    # Устанавливаем новое подключение пользователя
    await r.set(user_key, connection.websocket_handler_id)
    await r.sadd(handler_key, connection.user_id)

    logging.info(f"Пользователь {connection.user_id} подключен к {connection.websocket_handler_id}")

    return {
        "status": "connected",
        "user_id": connection.user_id,
        "websocket_handler_id": connection.websocket_handler_id
    }


@app.post("/disconnect")
async def disconnect_user(user: User):
    """
    Удаляет информацию о подключении пользователя.

    :param user: Объект, содержащий идентификатор пользователя.
    :return: Статус отключения и идентификатор пользователя.
    """
    user_key = f"user:{user.user_id}"
    # Получаем текущий обработчик пользователя
    handler_id = await r.get(user_key)
    if not handler_id:
        raise HTTPException(status_code=404, detail="Пользователь не подключен")

    handler_key = f"WSH:{handler_id}:connected_users"

    # Удаляем пользователя из списка подключенных пользователей обработчика
    await r.srem(handler_key, user.user_id)
    # Удаляем информацию о подключении пользователя
    await r.delete(user_key)

    logging.info(f"Пользователь {user.user_id} отключен от {handler_id}")

    return {
        "status": "disconnected",
        "user_id": user.user_id
    }


@app.get("/handler/{user_id}")
async def get_handler_for_user(user_id: str):
    """
    Получает идентификатор WebSocket обработчика, к которому подключен пользователь.

    :param user_id: Идентификатор пользователя.
    :return: Идентификатор пользователя и WebSocket обработчика.
    """
    user_key = f"user:{user_id}"
    handler_id = await r.get(user_key)
    if not handler_id:
        raise HTTPException(status_code=404, detail="Пользователь не подключен")

    return {
        "user_id": user_id,
        "websocket_handler_id": handler_id
    }


@app.get("/users/{websocket_handler_id}")
async def get_users_for_handler(websocket_handler_id: str):
    """
    Получает список пользователей, подключенных к указанному WebSocket обработчику.

    :param websocket_handler_id: Идентификатор WebSocket обработчика.
    :return: Идентификатор WebSocket обработчика и список пользователей.
    """
    handler_key = f"WSH:{websocket_handler_id}:connected_users"
    users = await r.smembers(handler_key)
    return {
        "websocket_handler_id": websocket_handler_id,
        "users": list(users)
    }


@app.get("/")
def read_root():
    """
    Проверка работоспособности сервиса.

    :return: Сообщение о статусе сервиса.
    """
    return {"message": "WebSocket Manager работает"}
