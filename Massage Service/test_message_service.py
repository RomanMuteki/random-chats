# Тест для старой версии main.py (ниже старая версия)
# import pytest
# from httpx import AsyncClient
# from main import app
# from motor.motor_asyncio import AsyncIOMotorClient
# from bson import ObjectId
# import pytest_asyncio
#
# MONGODB_URL = "mongodb://localhost:27017"
# DATABASE_NAME = "random_chats_db_test"
#
#
# @pytest.fixture(scope="session")
# def anyio_backend():
#     return "asyncio"
#
#
# @pytest_asyncio.fixture(scope="session", autouse=True)
# async def setup_db():
#     # Настройка тестовой базы данных
#     client = AsyncIOMotorClient(MONGODB_URL)
#     test_db = client[DATABASE_NAME]
#     # Очищаем коллекции
#     await test_db["messages"].delete_many({})
#     await test_db["chats"].delete_many({})
#     # Присваиваем тестовую БД приложению
#     app.db = test_db
#     app.client = client
#     yield
#     # Очистка после тестов
#     await client.drop_database(DATABASE_NAME)
#     client.close()
#
#
# @pytest_asyncio.fixture(scope="function")
# async def async_client():
#     async with AsyncClient(base_url="http://localhost:8200") as ac:
#         yield ac
#
#
# class TestMessageService:
#     chat_id = None
#     message_id = None
#
#     @pytest.mark.asyncio
#     async def test_create_chat(self, async_client):
#         # Тест создания чата
#         payload = {
#             "participants": ["user1", "user2"]
#         }
#         response = await async_client.post("/chats/", json=payload)
#         assert response.status_code == 200
#         data = response.json()
#         assert "_id" in data
#         assert "participants" in data
#         assert data["participants"] == ["user1", "user2"]
#         TestMessageService.chat_id = data["_id"]
#
#     @pytest.mark.asyncio
#     async def test_create_message(self, async_client):
#         # Тест создания сообщения
#         payload = {
#             "chat_id": TestMessageService.chat_id,
#             "sender_id": "user1",
#             "content": "Hello user2!"
#         }
#         response = await async_client.post("/messages/", json=payload)
#         assert response.status_code == 200
#         data = response.json()
#         assert data["chat_id"] == TestMessageService.chat_id
#         assert data["sender_id"] == "user1"
#         assert data["content"] == "Hello user2!"
#         TestMessageService.message_id = data["_id"]
#
#     @pytest.mark.asyncio
#     async def test_get_chat_messages(self, async_client):
#         # Тест получения сообщений из чата
#         response = await async_client.get(f"/messages/{TestMessageService.chat_id}")
#         assert response.status_code == 200
#         messages = response.json()
#         assert len(messages) == 1
#         message = messages[0]
#         assert message["_id"] == TestMessageService.message_id
#         assert message["content"] == "Hello user2!"
#
#     @pytest.mark.asyncio
#     async def test_update_message_status(self, async_client):
#         # Тест обновления статуса сообщения
#         payload = {
#             "receiver_id": "user2",
#             "status": "delivered"
#         }
#         response = await async_client.put(f"/messages/{TestMessageService.message_id}/status", json=payload)
#         assert response.status_code == 200
#         data = response.json()
#         assert data["message"] == "Статус сообщения обновлен"
#
#         # Проверяем, что статус обновлен
#         response = await async_client.get(f"/messages/{TestMessageService.chat_id}")
#         assert response.status_code == 200
#         messages = response.json()
#         assert len(messages) == 1
#         message = messages[0]
#         assert "status" in message
#         assert "user2" in message["status"]
#         assert message["status"]["user2"]["status"] == "delivered"
#
#     @pytest.mark.asyncio
#     async def test_get_new_messages_for_user(self, async_client):
#         # Тест получения новых сообщений для user2
#         response = await async_client.get(f"/messages/{TestMessageService.chat_id}/new/user2")
#         assert response.status_code == 200
#         messages = response.json()
#         # Поскольку статус обновлен на 'delivered', новых сообщений не должно быть
#         assert len(messages) == 0
#
#         # Отправляем еще одно сообщение
#         payload = {
#             "chat_id": TestMessageService.chat_id,
#             "sender_id": "user1",
#             "content": "How are you?"
#         }
#         response = await async_client.post("/messages/", json=payload)
#         assert response.status_code == 200
#         data = response.json()
#         new_message_id = data["_id"]
#         # Получаем новые сообщения для user2
#         response = await async_client.get(f"/messages/{TestMessageService.chat_id}/new/user2")
#         assert response.status_code == 200
#         messages = response.json()
#         assert len(messages) == 1
#         message = messages[0]
#         assert message["_id"] == new_message_id
#         assert message["content"] == "How are you?"
#
#     @pytest.mark.asyncio
#     async def test_get_user_chats(self, async_client):
#         # Тест получения чатов пользователя
#         response = await async_client.get(f"/chats/user1")
#         assert response.status_code == 200
#         chats = response.json()
#         assert len(chats) >= 1  # Может быть больше, если тесты запускались несколько раз
#         chat_ids = [chat["_id"] for chat in chats]
#         assert TestMessageService.chat_id in chat_ids
#
#     @pytest.mark.asyncio
#     async def test_update_chat_status(self, async_client):
#         # Тест обновления статуса чата
#         payload = {
#             "receiver_id": "user1",
#             "status": "delivered"
#         }
#         response = await async_client.put(f"/chats/{TestMessageService.chat_id}/status", json=payload)
#         assert response.status_code == 200
#         data = response.json()
#         assert data["message"] == "Статус чата обновлен"
#
#         # Получаем новые чаты для user1
#         response = await async_client.get(f"/chats/user1/new")
#         assert response.status_code == 200
#         new_chats = response.json()
#         # Поскольку статус обновлен на 'delivered', чата не должно быть в новых
#         chat_ids = [chat["_id"] for chat in new_chats]
#         assert TestMessageService.chat_id not in chat_ids
#
#     @pytest.mark.asyncio
#     async def test_get_new_chats(self, async_client):
#         # Создаем новый чат и проверяем
#         payload = {
#             "participants": ["user1", "user3"]
#         }
#         response = await async_client.post("/chats/", json=payload)
#         assert response.status_code == 200
#         data = response.json()
#         new_chat_id = data["_id"]
#
#         # Получаем новые чаты для user1
#         response = await async_client.get(f"/chats/user1/new")
#         assert response.status_code == 200
#         new_chats = response.json()
#         chat_ids = [chat["_id"] for chat in new_chats]
#         assert new_chat_id in chat_ids
#
#     @pytest.mark.asyncio
#     async def test_error_handling_create_message_invalid_chat(self, async_client):
#         # Тест создания сообщения с неверным chat_id
#         payload = {
#             "chat_id": "invalid_chat_id",
#             "sender_id": "user1",
#             "content": "Hello!"
#         }
#         response = await async_client.post("/messages/", json=payload)
#         assert response.status_code == 422  # Неверный ввод
#
#     @pytest.mark.asyncio
#     async def test_error_handling_update_message_status_invalid_message(self, async_client):
#         # Тест обновления статуса несуществующего сообщения
#         payload = {
#             "receiver_id": "user2",
#             "status": "delivered"
#         }
#         invalid_message_id = str(ObjectId())
#         response = await async_client.put(f"/messages/{invalid_message_id}/status", json=payload)
#         assert response.status_code == 404
#
#     @pytest.mark.asyncio
#     async def test_get_new_messages_with_last_message_id(self, async_client):
#         # Тест получения новых сообщений после указанного сообщения
#         # Отправляем новое сообщение
#         payload = {
#             "chat_id": TestMessageService.chat_id,
#             "sender_id": "user1",
#             "content": "Third message"
#         }
#         response = await async_client.post("/messages/", json=payload)
#         assert response.status_code == 200
#         data = response.json()
#         last_message_id = data["_id"]
#
#         # Отправляем еще одно сообщение
#         payload = {
#             "chat_id": TestMessageService.chat_id,
#             "sender_id": "user1",
#             "content": "Fourth message"
#         }
#         response = await async_client.post("/messages/", json=payload)
#         assert response.status_code == 200
#
#         # Получаем новые сообщения после last_message_id
#         response = await async_client.get(f"/messages/{TestMessageService.chat_id}/new?last_message_id={last_message_id}")
#         assert response.status_code == 200
#         messages = response.json()
#         assert len(messages) == 1
#         assert messages[0]["content"] == "Fourth message"
#
#     @pytest.mark.asyncio
#     async def test_get_new_messages_invalid_last_message_id(self, async_client):
#         # Тест получения новых сообщений с неверным last_message_id
#         invalid_message_id = "invalid_id"
#         response = await async_client.get(f"/messages/{TestMessageService.chat_id}/new?last_message_id={invalid_message_id}")
#         assert response.status_code == 422  # Неверный ввод
#
#     @pytest.mark.asyncio
#     async def test_get_messages_invalid_chat_id(self, async_client):
#         # Тест получения сообщений с неверным chat_id
#         response = await async_client.get(f"/messages/invalid_chat_id")
#         assert response.status_code == 422  # Неверный ввод
#
#     @pytest.mark.asyncio
#     async def test_update_chat_status_invalid_chat(self, async_client):
#         # Тест обновления статуса несуществующего чата
#         payload = {
#             "receiver_id": "user1",
#             "status": "delivered"
#         }
#         invalid_chat_id = str(ObjectId())
#         response = await async_client.put(f"/chats/{invalid_chat_id}/status", json=payload)
#         assert response.status_code == 404
#
#     @pytest.mark.asyncio
#     async def test_create_chat_missing_participants(self, async_client):
#         # Тест создания чата без участников
#         payload = {}
#         response = await async_client.post("/chats/", json=payload)
#         assert response.status_code == 422



# Старая версия main.py
# import os
# import logging
# from typing import List, Optional
# from datetime import datetime
# from fastapi import FastAPI, HTTPException
# from bson import ObjectId
# from motor.motor_asyncio import AsyncIOMotorClient
# import json
# from models import (
#     MessageCreate,
#     MessageStatusUpdate,
#     ChatCreate,
#     Message,
#     Chat,
# )
#
# CONFIG_FILE = 'config.json'
# if not os.path.exists(CONFIG_FILE):
#     raise FileNotFoundError(f"Файл конфигурации {CONFIG_FILE} не найден.")
#
# with open(CONFIG_FILE, 'r') as f:
#     config = json.load(f)
#
# MONGODB_URL = config.get('mongodb_url', 'mongodb://localhost:27017')
# DATABASE_NAME = config.get('database_name', 'random_chats_db')
# SERVICE_NAME = config.get('service_name', 'Message Service')
# LOG_LEVEL = config.get('log_level', 'INFO')
#
# client = AsyncIOMotorClient(MONGODB_URL)
# db = client[DATABASE_NAME]
#
# logging.basicConfig(level=LOG_LEVEL)
# logger = logging.getLogger(SERVICE_NAME)
#
# app = FastAPI(title=SERVICE_NAME)
#
#
# def validate_object_id(id_str: str, name: str) -> ObjectId:
#     try:
#         return ObjectId(id_str)
#     except Exception:
#         raise HTTPException(status_code=422, detail=f"Invalid {name}: {id_str}")
#
#
# @app.on_event("startup")
# async def create_indexes():
#     try:
#         await db["messages"].create_index([("chat_id", 1), ("timestamp", 1)])
#         await db["chats"].create_index([("participants", 1), ("created_at", -1)])
#         logger.info("Индексы созданы успешно")
#     except Exception as e:
#         logger.error(f"Ошибка при создании индексов: {e}")
#         raise HTTPException(status_code=500, detail="Ошибка при создании индексов")
#
#
# @app.post("/messages/", response_model=Message)
# async def create_message(message: MessageCreate):
#     """Создает новое сообщение и сохраняет его в MongoDB."""
#     try:
#         message_dict = message.dict()
#         message_dict["chat_id"] = validate_object_id(message.chat_id, "chat_id")
#
#         # Получаем участников чата
#         chat = await db["chats"].find_one({"_id": message_dict["chat_id"]})
#         if not chat:
#             raise HTTPException(status_code=404, detail="Чат не найден")
#
#         participants = chat["participants"]
#         recipients = [user_id for user_id in participants if user_id != message.sender_id]
#
#         # Инициализируем статус для каждого получателя
#         message_dict["status"] = {
#             recipient_id: {
#                 "status": "undelivered",
#                 "timestamp": datetime.utcnow()
#             } for recipient_id in recipients
#         }
#
#         result = await db["messages"].insert_one(message_dict)
#         message_dict["_id"] = result.inserted_id
#         # Обновляем last_message в чате
#         await db["chats"].update_one(
#             {"_id": message_dict["chat_id"]},
#             {"$set": {"last_message": {
#                 "message_id": str(result.inserted_id),
#                 "content": message.content,
#                 "timestamp": message.timestamp
#             }}}
#         )
#         return Message(**message_dict)
#     except HTTPException as e:
#         # Перехватываем и повторно выбрасываем HTTPException
#         raise e
#     except Exception as e:
#         logger.error(f"Ошибка при создании сообщения: {e}")
#         raise HTTPException(status_code=500, detail="Ошибка при создании сообщения")
#
#
# @app.put("/messages/{message_id}/status")
# async def update_message_status(message_id: str, status_update: MessageStatusUpdate):
#     """Обновляет статус сообщения для определенного получателя."""
#     try:
#         message_oid = validate_object_id(message_id, "message_id")
#         result = await db["messages"].update_one(
#             {"_id": message_oid},
#             {"$set": {f"status.{status_update.receiver_id}": {
#                 "status": status_update.status,
#                 "timestamp": status_update.timestamp
#             }}}
#         )
#         if result.matched_count == 0:
#             raise HTTPException(status_code=404, detail="Сообщение не найдено")
#         return {"message": "Статус сообщения обновлен"}
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         logger.error(f"Ошибка при обновлении статуса сообщения: {e}")
#         raise HTTPException(status_code=500, detail="Ошибка при обновлении статуса сообщения")
#
#
# @app.post("/chats/", response_model=Chat)
# async def create_chat(chat: ChatCreate):
#     """Создает новый чат между участниками."""
#     try:
#         chat_dict = chat.dict()
#         chat_dict["created_at"] = datetime.utcnow()
#         # Инициализируем статус доставки для каждого участника как 'undelivered'
#         chat_dict["status"] = {participant: "undelivered" for participant in chat.participants}
#         result = await db["chats"].insert_one(chat_dict)
#         chat_dict["_id"] = result.inserted_id
#         return Chat(**chat_dict)
#     except Exception as e:
#         logger.error(f"Ошибка при создании чата: {e}")
#         raise HTTPException(status_code=500, detail="Ошибка при создании чата")
#
#
# @app.get("/chats/{user_id}", response_model=List[Chat])
# async def get_user_chats(user_id: str):
#     """Получает список чатов, в которых участвует пользователь."""
#     try:
#         chats_cursor = db["chats"].find({"participants": user_id}).sort("created_at", -1)
#         chats = []
#         async for chat in chats_cursor:
#             chats.append(Chat(**chat))
#         return chats
#     except Exception as e:
#         logger.error(f"Ошибка при получении чатов пользователя {user_id}: {e}")
#         raise HTTPException(status_code=500, detail="Ошибка при получении чатов")
#
#
# @app.get("/messages/{chat_id}", response_model=List[Message])
# async def get_chat_messages(chat_id: str, limit: int = 50, skip: int = 0):
#     """Получает сообщения из чата."""
#     try:
#         chat_oid = validate_object_id(chat_id, "chat_id")
#         messages_cursor = db["messages"].find({"chat_id": chat_oid}).skip(skip).limit(limit).sort("timestamp", 1)
#         messages = []
#         async for message in messages_cursor:
#             messages.append(Message(**message))
#         return messages
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         logger.error(f"Ошибка при получении сообщений: {e}")
#         raise HTTPException(status_code=500, detail="Ошибка при получении сообщений")
#
#
# @app.get("/messages/{chat_id}/new", response_model=List[Message])
# async def get_new_messages(chat_id: str, last_message_id: Optional[str] = None):
#     """Получает новые сообщения в чате после определенного сообщения."""
#     try:
#         chat_oid = validate_object_id(chat_id, "chat_id")
#         query = {"chat_id": chat_oid}
#         if last_message_id:
#             last_message_oid = validate_object_id(last_message_id, "last_message_id")
#             last_message = await db["messages"].find_one({"_id": last_message_oid})
#             if last_message:
#                 query["timestamp"] = {"$gt": last_message["timestamp"]}
#             else:
#                 raise HTTPException(status_code=404, detail="Последнее сообщение не найдено")
#         messages_cursor = db["messages"].find(query).sort("timestamp", 1)
#         messages = []
#         async for message in messages_cursor:
#             messages.append(Message(**message))
#         return messages
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         logger.error(f"Ошибка при получении новых сообщений для чата {chat_id}: {e}")
#         raise HTTPException(status_code=500, detail="Ошибка при получении новых сообщений")
#
#
# @app.get("/messages/{chat_id}/new/{user_id}", response_model=List[Message])
# async def get_new_messages(chat_id: str, user_id: str):
#     """Получает новые сообщения в чате, которые не были доставлены пользователю."""
#     try:
#         query = {
#             "chat_id": ObjectId(chat_id),
#             f"status.{user_id}.status": {"$eq": "undelivered"}
#         }
#         messages_cursor = db["messages"].find(query).sort("timestamp", 1)
#         messages = []
#         async for message in messages_cursor:
#             messages.append(Message(**message))
#         return messages
#     except Exception as e:
#         logger.error(f"Ошибка при получении новых сообщений для чата {chat_id}: {e}")
#         raise HTTPException(status_code=500, detail="Ошибка при получении новых сообщений")
#
#
# @app.get("/chats/{user_id}/new", response_model=List[Chat])
# async def get_new_chats(user_id: str):
#     """Получает новые чаты пользователя, которые не были доставлены ему ранее."""
#     try:
#         query = {
#             "participants": user_id,
#             f"status.{user_id}": {"$ne": "delivered"}
#         }
#         chats_cursor = db["chats"].find(query)
#         chats = []
#         async for chat in chats_cursor:
#             chats.append(Chat(**chat))
#         return chats
#     except Exception as e:
#         logger.error(f"Ошибка при получении новых чатов пользователя {user_id}: {e}")
#         raise HTTPException(status_code=500, detail="Ошибка при получении новых чатов")
#
#
# @app.put("/chats/{chat_id}/status")
# async def update_chat_status(chat_id: str, status_update: MessageStatusUpdate):
#     """Обновляет статус чата для определенного пользователя."""
#     try:
#         chat_oid = validate_object_id(chat_id, "chat_id")
#         result = await db["chats"].update_one(
#             {"_id": chat_oid},
#             {"$set": {f"status.{status_update.receiver_id}": status_update.status}}
#         )
#         if result.matched_count == 0:
#             raise HTTPException(status_code=404, detail="Чат не найден")
#         return {"message": "Статус чата обновлен"}
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         logger.error(f"Ошибка при обновлении статуса чата: {e}")
#         raise HTTPException(status_code=500, detail="Ошибка при обновлении статуса чата")
#
#
# @app.get("/")
# async def root():
#     """Корневой эндпоинт для проверки работоспособности сервиса."""
#     return {"message": f"{SERVICE_NAME} работает"}
