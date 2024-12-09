import json
import os
import logging
import asyncio
from typing import Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from cachetools import TTLCache
import httpx
import time
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)

CONFIG_FILE = 'config.json'

if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"Файл конфигурации {CONFIG_FILE} не найден.")

with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

WEBSOCKET_MANAGER_URL = config.get('websocket_manager_url', 'http://localhost:8000')
MESSAGE_SERVICE_URL = config.get('message_service_url', 'http://localhost:8200')
HANDLER_ID = config.get('handler_id', 'WSH1')  # Уникальный ID для каждого обработчика

HANDLER_URLS = {
    'WSH1': 'http://localhost:8001',
    'WSH2': 'http://localhost:8002',
}

app = FastAPI(title=f"WebSocket Handler {HANDLER_ID}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

user_cache = TTLCache(maxsize=1000, ttl=60)
connected_users: Dict[str, WebSocket] = {}

http_client = httpx.AsyncClient()


@app.on_event("shutdown")
async def shutdown_event():
    await http_client.aclose()


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """
    Обрабатывает WebSocket соединения от пользователей.
    Параметры:        websocket (WebSocket): WebSocket соединение.        user_id (str): ID подключающегося пользователя.    """
    await websocket.accept()
    try:
        await register_user(user_id)
        # Отправка новых чатов и сообщений после успешной регистрации
        await send_new_chats_and_messages(user_id, websocket)
    except Exception as e:
        logging.error(f"Ошибка при регистрации пользователя {user_id}: {e}")
        await websocket.close(code=1000)
        return

    connected_users[user_id] = websocket
    logging.info(f"Пользователь {user_id} подключен.")

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            await handle_incoming_message(user_id, message)
    except WebSocketDisconnect:
        logging.info(f"Пользователь {user_id} отключился.")
    except Exception as e:
        logging.error(f"Ошибка с пользователем {user_id}: {e}")
    finally:
        # Снятие регистрации пользователя
        await unregister_user(user_id)
        connected_users.pop(user_id, None)
        await websocket.close()


async def register_user(user_id: str):
    url = f"{WEBSOCKET_MANAGER_URL}/connect"
    payload = {
        "user_id": user_id,
        "websocket_handler_id": HANDLER_ID
    }
    logging.info(f"Регистрация пользователя {user_id} на {url} с данными: {payload}")
    response = await http_client.post(url, json=payload)
    logging.info(f"Ответ WebSocket Manager: {response.status_code}, {response.text}")
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code,
                            detail=f"Не удалось зарегистрировать пользователя {user_id}")


async def unregister_user(user_id: str):
    """
    Снимает регистрацию пользователя в WebSocket Manager.
    Параметры:        user_id (str): ID пользователя для снятия регистрации.    """
    url = f"{WEBSOCKET_MANAGER_URL}/disconnect"
    payload = {
        "user_id": user_id
    }
    response = await http_client.post(url, json=payload)
    if response.status_code != 200:
        logging.warning(f"Не удалось снять регистрацию пользователя {user_id}.")


async def handle_incoming_message(sender_id: str, message_data: Dict):
    """
    Обрабатывает входящие сообщения от подключенных пользователей.
    Параметры:        sender_id (str): ID отправляющего пользователя.        message_data (Dict): Данные сообщения, содержащие как минимум 'recipient_id' и 'content'.    """
    recipient_id = message_data.get('recipient_id')
    content = message_data.get('content')

    if not recipient_id or not content:
        logging.warning(f"Некорректное сообщение от {sender_id}: {message_data}")
        return

    # Сохранение сообщения через Message Service (заглушка)
    message_id = await save_message(sender_id, recipient_id, content)

    # Проверка, подключен ли получатель к этому обработчику
    recipient_websocket = connected_users.get(recipient_id)
    if recipient_websocket:
        # Получатель подключен к этому обработчику
        await deliver_message(recipient_websocket, {
            "sender_id": sender_id,
            "content": content,
            "message_id": message_id
        })
        # Обновление статуса сообщения через Message Service
        await update_message_status(message_id, recipient_id, status="delivered")
    else:
        # Получатель не подключен к этому обработчику, проверка кэша или WebSocket Manager
        handler_id = user_cache.get(recipient_id)
        if not handler_id:
            handler_id = await get_handler_for_user(recipient_id)
            if handler_id:
                user_cache[recipient_id] = handler_id

        if handler_id == HANDLER_ID:
            # Крайний случай: получатель должен быть подключен, но не найден
            logging.warning(f"Получатель {recipient_id} должен быть подключен, но не найден.")
        elif handler_id:
            # Отправка сообщения обработчику, к которому подключен получатель
            await forward_message_to_handler(handler_id, {
                "sender_id": sender_id,
                "recipient_id": recipient_id,
                "content": content,
                "message_id": message_id
            })
            # Обновление статуса сообщения через Message Service
            await update_message_status(message_id, recipient_id, status="delivered")
        else:
            # Получатель не в сети
            # Обработка доставки сообщений для оффлайн-получателей            logging.info(f"Получатель {recipient_id} не в сети.")
            await handle_offline_recipient(recipient_id, message_id)


async def save_message(sender_id: str, recipient_id: str, content: str) -> str:
    """
    Сохраняет сообщение через Message Service.
    :param content:
    :param sender_id: str - ID отправителя    :param recipient_id: str - ID получателя    :param content: str - содержимое сообщения    :return: str - ID сохраненного сообщения
    """
    try:
        # Получение или создание chat_id между sender_id и recipient_id
        chat_id = await get_chat_id(sender_id, recipient_id)
        if not chat_id:
            raise HTTPException(status_code=500, detail="Не удалось получить chat_id")

        # Формирование данных сообщения
        message_data = {
            "chat_id": chat_id,
            "sender_id": sender_id,
            "content": content
        }
        url = f"{MESSAGE_SERVICE_URL}/messages/"
        response = await http_client.post(url, json=message_data)
        if response.status_code == 200:
            message = response.json()
            message_id = message.get('_id')
            logging.info(f"Сообщение сохранено с ID {message_id}")
            logging.info(f"message: {message}, keys: {message.keys()}")
            return message_id
        else:
            logging.error(f"Не удалось сохранить сообщение: {response.text}")
            raise HTTPException(status_code=response.status_code, detail="Не удалось сохранить сообщение")
    except Exception as e:
        logging.error(f"Ошибка при сохранении сообщения: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


async def update_message_status(message_id: str, user_id: str, status: str):
    """
    Обновляет статус сообщения через Message Service.
    :param message_id: str - ID сообщения    :param user_id: str - ID пользователя    :param status: str - новый статус сообщения ('delivered', 'read')    """
    try:
        status_data = {
            "receiver_id": user_id,
            "status": status
        }
        url = f"{MESSAGE_SERVICE_URL}/messages/{message_id}/status"
        response = await http_client.put(url, json=status_data)
        if response.status_code == 200:
            logging.info(f"Статус сообщения {message_id} для пользователя {user_id} обновлен на {status}")
        else:
            logging.error(f"Не удалось обновить статус сообщения: {response.text}")
    except Exception as e:
        logging.error(f"Ошибка при обновлении статуса сообщения: {e}")


async def get_chat_id(user1_id: str, user2_id: str) -> str:
    """
    Получает ID чата между двумя пользователями или создает новый чат.
    :param user1_id: str - ID первого пользователя    :param user2_id: str - ID второго пользователя    :return: str - ID чата
    """
    try:
        # Сначала проверяем, существует ли чат
        url = f"{MESSAGE_SERVICE_URL}/chats/{user1_id}"
        response = await http_client.get(url)
        if response.status_code == 200:
            chats = response.json()
            for chat in chats:
                participants = set(chat.get('participants', []))
                if participants == {user1_id, user2_id}:
                    return chat['_id']
        else:
            logging.error(f"Не удалось получить чаты пользователя {user1_id}: {response.text}")

        # Если чат не существует, создаем его
        chat_data = {
            "participants": [user1_id, user2_id]
        }
        url = f"{MESSAGE_SERVICE_URL}/chats/"
        response = await http_client.post(url, json=chat_data)
        if response.status_code == 200:
            chat = response.json()
            chat_id = chat.get('_id')
            if not chat_id:
                logging.error("Не удалось получить 'id' чата из ответа")
                raise HTTPException(status_code=500, detail="Не удалось получить 'id' чата")
            return chat_id
        else:
            logging.error(f"Не удалось создать чат: {response.text}")
            raise HTTPException(status_code=response.status_code, detail="Не удалось создать чат")
    except Exception as e:
        logging.error(f"Ошибка при получении или создании чата: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


async def get_handler_for_user(user_id: str) -> Optional[str]:
    """
    Получает ID обработчика для данного пользователя из WebSocket Manager.
    Параметры:        user_id (str): ID пользователя.
    Возвращает:        Optional[str]: ID обработчика, если пользователь в сети, иначе None.    """
    url = f"{WEBSOCKET_MANAGER_URL}/handler/{user_id}"
    response = await http_client.get(url)
    if response.status_code == 200:
        data = response.json()
        return data.get('websocket_handler_id')
    elif response.status_code == 404:
        return None
    else:
        raise HTTPException(status_code=response.status_code,
                            detail=f"Не удалось получить обработчик для пользователя {user_id}")


async def forward_message_to_handler(handler_id: str, message_data: Dict):
    """
    Пересылает сообщение другому WebSocket Handler.
    Параметры:        handler_id (str): ID целевого обработчика.        message_data (Dict): Данные сообщения для пересылки.    """
    handler_url = HANDLER_URLS.get(handler_id)
    if not handler_url:
        logging.error(f"URL для обработчика {handler_id} не найден.")
        return

    url = f"{handler_url}/forward_message"
    response = await http_client.post(url, json=message_data)
    if response.status_code != 200:
        logging.error(f"Не удалось переслать сообщение обработчику {handler_id}: {response.text}")
    else:
        logging.info(f"Сообщение переслано обработчику {handler_id}.")


async def send_new_chats_and_messages(user_id: str, websocket: WebSocket):
    """
    Отправляет новые чаты и сообщения пользователю при подключении.
    :param user_id: str - ID пользователя    :param websocket: WebSocket - соединение WebSocket    """
    try:
        # Получение новых чатов
        chats_url = f"{MESSAGE_SERVICE_URL}/chats/{user_id}/new"
        response = await http_client.get(chats_url)
        if response.status_code == 200:
            chats = response.json()
            await websocket.send_text(json.dumps({"type": "new_chats", "data": chats}))
            # Для каждого чата получаем новые сообщения
            for chat in chats:
                chat_id = chat["_id"]
                messages_url = f"{MESSAGE_SERVICE_URL}/messages/{chat_id}/new"
                messages_response = await http_client.get(messages_url)
                if messages_response.status_code == 200:
                    messages = messages_response.json()
                    await websocket.send_text(
                        json.dumps({"type": "new_messages", "chat_id": chat_id, "data": messages}))
        else:
            logging.error(f"Не удалось получить новые чаты для пользователя {user_id}: {response.text}")
    except Exception as e:
        logging.error(f"Ошибка при отправке новых чатов и сообщений: {e}")


@app.post("/forward_message")
async def forward_message_endpoint(message_data: Dict):
    """
    Эндпоинт для получения пересылаемых сообщений от других WebSocket Handlers.
    Параметры:        message_data (Dict): Данные сообщения, содержащие 'recipient_id', 'sender_id', 'content' и 'message_id'.    """
    recipient_id = message_data.get('recipient_id')
    recipient_websocket = connected_users.get(recipient_id)
    if recipient_websocket:
        await deliver_message(recipient_websocket, message_data)
        # Обновление статуса сообщения через Message Service
        await update_message_status(message_data.get('message_id'), recipient_id, status="delivered")
        return {"status": "delivered"}
    else:
        logging.warning(f"Получатель {recipient_id} не подключен к этому обработчику.")
        return {"status": "not_delivered"}


async def deliver_message(websocket: WebSocket, message_data: Dict):
    """
    Доставляет сообщение подключенному пользователю через WebSocket.
    Параметры:        websocket (WebSocket): WebSocket соединение получателя.        message_data (Dict): Данные сообщения для отправки.    """
    await websocket.send_text(json.dumps(message_data))
    logging.info(f"Сообщение доставлено пользователю {message_data.get('recipient_id')}")


async def handle_offline_recipient(recipient_id: str, message_id: str):
    """
    Обрабатывает сценарий, когда получатель не в сети.
    Параметры:        recipient_id (str): ID оффлайн-получателя.        message_id (str): ID сообщения.
    Эта функция может быть расширена для отправки push-уведомлений или другой обработки оффлайн-сообщений.    """  # Имитация обработки оффлайн-получателя
    logging.info(f"Обработка оффлайн-получателя {recipient_id} для сообщения {message_id}.")


# Простой HTML клиент для тестирования (опционально)
# Простой HTML клиент для тестирования (опционально)
@app.get("/")
async def get():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>WebSocket Client</title>
        <style>
            body {
                font-family: Arial, sans-serif;
            }
            textarea {
                width: 100%;
                height: 300px;
                margin: 5px 0;
            }
            input, button {
                margin: 5px;
                padding: 10px;
            }
        </style>
    </head>
    <body>
        <h1>WebSocket Client</h1>
        <div>
            <input id="userId" type="text" placeholder="User ID" />
            <button onclick="connect()">Connect</button>
            <button onclick="disconnect()">Disconnect</button>
        </div>
        <textarea id="log" readonly></textarea>
        <div>
            <input id="recipientId" type="text" placeholder="Recipient ID" />
            <input id="messageContent" type="text" placeholder="Message" />
            <button onclick="sendMessage()">Send Message</button>
        </div>
        <script>
            var ws;

            function connect() {
                var userId = document.getElementById("userId").value;
                if (!userId) {
                    alert("User ID is required to connect.");
                    return;
                }
                var ws_url = `ws://${window.location.host}/ws/${userId}`;
                ws = new WebSocket(ws_url);

                ws.onopen = function() {
                    logMessage("Connection opened.");
                };

                ws.onmessage = function(event) {
                    logMessage("Received: " + event.data);
                };

                ws.onclose = function() {
                    logMessage("Connection closed.");
                };

                ws.onerror = function(event) {
                    logMessage("Error: " + event.message);
                };
            }

            function sendMessage() {
                if (!ws || ws.readyState !== WebSocket.OPEN) {
                    alert("WebSocket is not connected.");
                    return;
                }
                var recipientId = document.getElementById("recipientId").value;
                var content = document.getElementById("messageContent").value;

                if (!recipientId || !content) {
                    alert("Recipient ID and message content are required.");
                    return;
                }

                var message = {
                    recipient_id: recipientId,
                    content: content
                };
                ws.send(JSON.stringify(message));
                logMessage("Sent: " + JSON.stringify(message));
            }

            function disconnect() {
                if (ws) {
                    ws.close();
                    ws = null;
                    logMessage("Disconnected.");
                }
            }

            function logMessage(message) {
                var log = document.getElementById("log");
                log.value += message + "\\n";
                log.scrollTop = log.scrollHeight;
            }
        </script>
    </body>
    </html>
    """)
