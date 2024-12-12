import os
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
import json
import httpx
from models import (
    MessageCreate,
    MessageStatusUpdate,
    ChatCreate,
    Message,
    Chat,
)
from fastapi.responses import HTMLResponse


log_file = "service.log"

CONFIG_FILE = 'config.json'
if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"Ф айл конфигурации {CONFIG_FILE} не найден.")

with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

MONGODB_URL = config.get('mongodb_url', 'mongodb://localhost:27017')
DATABASE_NAME = config.get('database_name', 'random_chats_db')
SERVICE_NAME = config.get('service_name', 'Message Service')
LOG_LEVEL = config.get('log_level', 'INFO')
API_GATEWAY_URL = config.get('api_gateway_url', 'http://localhost:8500')
MAX_ATTEMPTS = config.get('max_attempts', 5)

client = AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]

app = FastAPI(title=SERVICE_NAME)

logging.basicConfig(level=LOG_LEVEL,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[
                        logging.StreamHandler(),
                        logging.FileHandler(log_file, mode='a')
                    ])
logger = logging.getLogger(SERVICE_NAME)

http_client = httpx.AsyncClient()


def validate_object_id(id_str: str, name: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid {name}: {id_str}")


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


async def get_user_name_by_id(user_id: str) -> str:
    """
    Получает имя пользователя по UID.

    :param user_id: UID пользователя.
    :return: Имя пользователя или "Unknown", если не удалось получить.
    """
    payload = {
        "uid": user_id,
    }
    result = await request_with_retry("GET", "auth_service", "/get_info_by_id", json=payload)

    if result and "username" in result:
        return result["username"]
    return "Unknown"  # Если имя не удалось получить, возвращаем "Unknown"


@app.on_event("startup")
async def create_indexes():
    try:
        await db["messages"].create_index([("chat_id", 1), ("timestamp", 1)])
        await db["chats"].create_index([("participants", 1), ("created_at", -1)])
        logger.info("Индексы созданы успешно")
    except Exception as e:
        logger.error(f"Ошибка при создании индексов: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании индексов")


@app.on_event("shutdown")
async def shutdown_event():
    """Закрытие HTTP клиента при завершении работы приложения."""
    await http_client.aclose()


@app.post("/messages/", response_model=Message)
async def create_message(message: MessageCreate):
    """Создает новое сообщение и сохраняет его в MongoDB."""
    try:
        message_dict = message.dict()
        message_dict["chat_id"] = validate_object_id(message.chat_id, "chat_id")

        # Получаем участников чата
        chat = await db["chats"].find_one({"_id": message_dict["chat_id"]})
        if not chat:
            raise HTTPException(status_code=404, detail="Чат не найден")

        participants = chat["participants"]
        recipients = [user_id for user_id in participants if user_id != message.sender_id]

        # Инициализируем статус для каждого получателя
        message_dict["status"] = {
            recipient_id: {
                "status": "undelivered",
                "timestamp": datetime.utcnow()
            } for recipient_id in recipients
        }

        result = await db["messages"].insert_one(message_dict)
        message_dict["_id"] = result.inserted_id
        # Обновляем last_message в чате
        await db["chats"].update_one(
            {"_id": message_dict["chat_id"]},
            {"$set": {"last_message": {
                "message_id": str(result.inserted_id),
                "content": message.content,
                "timestamp": message.timestamp
            }}}
        )
        return Message(**message_dict)
    except HTTPException as e:
        # Перехватываем и повторно выбрасываем HTTPException
        raise e
    except Exception as e:
        logger.error(f"Ошибка при создании сообщения: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании сообщения")


@app.put("/messages/{message_id}/status")
async def update_message_status(message_id: str, status_update: MessageStatusUpdate):
    """Обновляет статус сообщения для определенного получателя."""
    try:
        message_oid = validate_object_id(message_id, "message_id")
        result = await db["messages"].update_one(
            {"_id": message_oid},
            {"$set": {f"status.{status_update.receiver_id}": {
                "status": status_update.status,
                "timestamp": status_update.timestamp
            }}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Сообщение не найдено")
        return {"message": "Статус сообщения обновлен"}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса сообщения: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении статуса сообщения")


@app.post("/chats/", response_model=Chat)
async def create_chat(chat: ChatCreate):
    """Создает новый чат между участниками."""
    try:
        # Проверяем, существует ли уже чат с этими участниками, только если их двое
        if len(chat.participants) == 2:
            existing_chat = await db["chats"].find_one({"participants": {"$all": chat.participants, "$size": 2}})
            if existing_chat:
                raise HTTPException(status_code=400, detail="Чат между этими участниками уже существует")

        participants_names = [await get_user_name_by_id(user_id) for user_id in chat.participants]

        chat_dict = chat.dict()
        chat_dict["created_at"] = datetime.utcnow()
        chat_dict["participants_names"] = participants_names  # Сохраняем имена участников
        # Инициализируем статус доставки для каждого участника как 'undelivered'
        chat_dict["status"] = {participant: "undelivered" for participant in chat.participants}

        result = await db["chats"].insert_one(chat_dict)
        chat_dict["_id"] = result.inserted_id
        return Chat(**chat_dict)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Ошибка при создании чата: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании чата")



@app.get("/chats/{user_id}", response_model=List[Chat])
async def get_user_chats(user_id: str):
    """Получает список чатов, в которых участвует пользователь."""
    try:
        chats_cursor = db["chats"].find({"participants": user_id}).sort("created_at", -1)
        chats = []
        async for chat in chats_cursor:
            chats.append(Chat(**chat))
        return chats
    except Exception as e:
        logger.error(f"Ошибка при получении чатов пользователя {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении чатов")


@app.get("/messages/{chat_id}", response_model=List[Message])
async def get_chat_messages(chat_id: str, limit: int = 50, skip: int = 0):
    """Получает сообщения из чата."""
    try:
        chat_oid = validate_object_id(chat_id, "chat_id")
        messages_cursor = db["messages"].find({"chat_id": chat_oid}).skip(skip).limit(limit).sort("timestamp", 1)
        messages = []
        async for message in messages_cursor:
            messages.append(Message(**message))
        return messages
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Ошибка при получении сообщений: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении сообщений")


@app.get("/messages/{chat_id}/new", response_model=List[Message])
async def get_new_messages(chat_id: str, last_message_id: Optional[str] = None):
    """Получает новые сообщения в чате после определенного сообщения."""
    try:
        chat_oid = validate_object_id(chat_id, "chat_id")
        query = {"chat_id": chat_oid}
        if last_message_id:
            last_message_oid = validate_object_id(last_message_id, "last_message_id")
            last_message = await db["messages"].find_one({"_id": last_message_oid})
            if last_message:
                query["timestamp"] = {"$gt": last_message["timestamp"]}
            else:
                raise HTTPException(status_code=404, detail="Последнее сообщение не найдено")
        messages_cursor = db["messages"].find(query).sort("timestamp", 1)
        messages = []
        async for message in messages_cursor:
            messages.append(Message(**message))
        return messages
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Ошибка при получении новых сообщений для чата {chat_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении новых сообщений")


@app.get("/messages/{chat_id}/new/{user_id}", response_model=List[Message])
async def get_new_messages(chat_id: str, user_id: str):
    """Получает новые сообщения в чате, которые не были доставлены пользователю."""
    try:
        query = {
            "chat_id": ObjectId(chat_id),
            f"status.{user_id}.status": {"$eq": "undelivered"}
        }
        messages_cursor = db["messages"].find(query).sort("timestamp", 1)
        messages = []
        async for message in messages_cursor:
            messages.append(Message(**message))
        return messages
    except Exception as e:
        logger.error(f"Ошибка при получении новых сообщений для чата {chat_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении новых сообщений")


@app.get("/chats/{user_id}/new", response_model=List[Chat])
async def get_new_chats(user_id: str):
    """Получает новые чаты пользователя, которые не были доставлены ему ранее."""
    try:
        query = {
            "participants": user_id,
            f"status.{user_id}": {"$ne": "delivered"}
        }
        chats_cursor = db["chats"].find(query)
        chats = []
        async for chat in chats_cursor:
            chats.append(Chat(**chat))
        return chats
    except Exception as e:
        logger.error(f"Ошибка при получении новых чатов пользователя {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении новых чатов")


@app.put("/chats/{chat_id}/status")
async def update_chat_status(chat_id: str, status_update: MessageStatusUpdate):
    """Обновляет статус чата для определенного пользователя."""
    try:
        chat_oid = validate_object_id(chat_id, "chat_id")
        result = await db["chats"].update_one(
            {"_id": chat_oid},
            {"$set": {f"status.{status_update.receiver_id}": status_update.status}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Чат не найден")
        return {"message": "Статус чата обновлен"}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса чата: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении статуса чата")


@app.get("/")
async def health():
    """
    Эндпоинт для проверки состояния сервиса.

    :return: Сообщение о том, что сервис работает.
    """
    return {"status": "Message Service is work!"}


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
                    <h1>Message Service Logs</h1>
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

