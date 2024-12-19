from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis.asyncio as redis
import json
import os
import logging
import httpx
from typing import Optional
from fastapi.responses import HTMLResponse


log_file = "service.log"

CONFIG_FILE = 'config.json'

if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"Файл конфигурации {CONFIG_FILE} не найден.")

with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

REDIS_HOST = config.get('redis_host', 'localhost')
REDIS_PORT = config.get('redis_port', 6379)
REDIS_DB = config.get('redis_db', 0)
API_GATEWAY_URL = config.get('api_gateway_url', 'http://localhost:8500')
MAX_ATTEMPTS = config.get('max_attempts', 5)

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True
)

app = FastAPI(title="WebSocket Manager")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[
                        logging.StreamHandler(),
                        logging.FileHandler(log_file, mode='a')
                    ])
logger = logging.getLogger("WebSocket Manager")

http_client = httpx.AsyncClient()


class Connection(BaseModel):
    user_id: str
    websocket_handler_id: str


class User(BaseModel):
    user_id: str


class HandlerRegistration(BaseModel):
    websocket_handler_id: str
    websocket_handler_url: str


async def request_with_retry(method: str, service_name: str, path: str, **kwargs) -> Optional[httpx.Response]:
    """
    Выполняет HTTP запрос к сервису с повторными попытками и обновлением URL из API Gateway.

    :param method: HTTP метод ('GET', 'POST', 'PUT', 'DELETE').
    :param service_name: Название сервиса.
    :param path: Путь эндпоинта в сервисе.
    :param kwargs: Дополнительные параметры для httpx.request.
    :return: Ответ httpx.Response или None.
    """
    attempts = 0
    while attempts < MAX_ATTEMPTS:
        url = f"{API_GATEWAY_URL}/get_service_instance?service_name={service_name}"
        try:
            response = await http_client.get(url)
            if response.status_code == 200:
                instance = response.json().get('instance')
                service_url = instance['url']
                full_url = f"{service_url}{path}"
                response = await http_client.request(method, full_url, **kwargs)
                if response.status_code == 200:
                    return response
                else:
                    logger.error(f"Ошибка при обращении к {service_name}: {response.status_code} {response.text}")
                    attempts += 1
            else:
                logger.error(f"Не удалось получить экземпляр {service_name} из API Gateway: {response.text}")
                attempts += 1
        except Exception as e:
            logger.error(f"Исключение при обращении к {service_name}: {e}")
            attempts += 1
    logger.error(f"Не удалось связаться с {service_name} после {MAX_ATTEMPTS} попыток")
    return None


@app.on_event("shutdown")
async def shutdown_event():
    """Закрытие HTTP клиента при завершении работы приложения."""
    await http_client.aclose()


@app.post("/register_handler")
async def register_handler(handler: HandlerRegistration):
    """
    Регистрирует WebSocket Handler с его URL.

    :param handler: Объект, содержащий идентификатор и URL WebSocket Handler.
    :return: Статус регистрации и информация об обработчике.
    """
    handler_key = f"handler:{handler.websocket_handler_id}:url"
    await r.set(handler_key, handler.websocket_handler_url)
    logger.info(f"Обработчик {handler.websocket_handler_id} зарегистрирован с URL {handler.websocket_handler_url}")
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

    logger.info(f"Пользователь {connection.user_id} подключен к {connection.websocket_handler_id}")

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

    logger.info(f"Пользователь {user.user_id} отключен от {handler_id}")

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
async def health():
    """
    Эндпоинт для проверки состояния сервиса.

    :return: Сообщение о том, что сервис работает.
    """
    return {"status": "WebSocket Manager is work!"}


@app.get("/logs", response_class=HTMLResponse)
async def get_logs():
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            logs = f.read()

        html_content = f"""
        <html>
            <head>
                <style>
                    body {{
                        font-family: 'Arial', sans-serif;
                        background-color: #f7f7f7;
                        margin: 0;
                        padding: 0;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        color: #333;
                    }}
                    h1 {{
                        font-size: 36px;
                        color: #4CAF50;
                        text-align: center;
                        margin-bottom: 20px;
                    }}
                    .log-container {{
                        width: 80%;
                        max-width: 1000px;
                        background-color: #ffffff;
                        border-radius: 10px;
                        box-shadow: 0px 4px 8px rgba(0, 0, 0, 0.1);
                        padding: 20px;
                        overflow: hidden;
                        box-sizing: border-box;
                    }}
                    pre {{
                        background-color: #1e1e1e;
                        color: #f1f1f1;
                        font-size: 14px;
                        padding: 20px;
                        border-radius: 8px;
                        white-space: pre-wrap;
                        word-wrap: break-word;
                        max-height: 70vh;
                        overflow-y: auto;
                    }}
                    .error {{
                        color: #e74c3c;
                        font-weight: bold;
                    }}
                    .refresh-btn {{
                        display: block;
                        margin: 20px auto;
                        padding: 10px 20px;
                        background-color: #4CAF50;
                        color: white;
                        border: none;
                        border-radius: 5px;
                        font-size: 16px;
                        cursor: pointer;
                    }}
                    .refresh-btn:hover {{
                        background-color: #45a049;
                    }}
                    @media (max-width: 768px) {{
                        h1 {{
                            font-size: 28px;
                        }}
                        .log-container {{
                            width: 95%;
                            padding: 15px;
                        }}
                        pre {{
                            font-size: 13px;
                            padding: 15px;
                        }}
                    }}
                </style>
            </head>
            <body>
                <div class="log-container">
                    <h1>WebSocket Manager Logs</h1>
                    <pre>{logs}</pre>
                    <button class="refresh-btn" onclick="window.location.reload();">Обновить логи</button>
                </div>
            </body>
        </html>
        """

        return HTMLResponse(content=html_content, status_code=200, headers={"Content-Type": "text/html; charset=utf-8"})
    except Exception as e:
        logger.error(f"Ошибка при чтении логов: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при чтении логов")
