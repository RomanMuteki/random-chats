import os
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi.middleware.cors import CORSMiddleware
import json
from models import (
    MessageCreate,
    MessageStatusUpdate,
    ChatCreate,
    Message,
    Chat,
)

CONFIG_FILE = 'config.json'
if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"Файл конфигурации {CONFIG_FILE} не найден.")

with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

MONGODB_URL = config.get('mongodb_url', 'mongodb://localhost:27017')
DATABASE_NAME = config.get('database_name', 'random_chats_db')
SERVICE_NAME = config.get('service_name', 'Message Service')
LOG_LEVEL = config.get('log_level', 'INFO')

client = AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(SERVICE_NAME)

app = FastAPI(title=SERVICE_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешает доступ с любых доменов
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def validate_object_id(id_str: str, name: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid {name}: {id_str}")


@app.on_event("startup")
async def create_indexes():
    try:
        await db["messages"].create_index([("chat_id", 1), ("timestamp", 1)])
        await db["chats"].create_index([("participants", 1), ("created_at", -1)])
        logger.info("Индексы созданы успешно")
    except Exception as e:
        logger.error(f"Ошибка при создании индексов: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании индексов")


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
        chat_dict = chat.dict()
        chat_dict["created_at"] = datetime.utcnow()
        # Инициализируем статус доставки для каждого участника как 'undelivered'
        chat_dict["status"] = {participant: "undelivered" for participant in chat.participants}
        result = await db["chats"].insert_one(chat_dict)
        chat_dict["_id"] = result.inserted_id
        return Chat(**chat_dict)
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
async def root():
    """Корневой эндпоинт для проверки работоспособности сервиса."""
    return {"message": f"{SERVICE_NAME} работает"}
