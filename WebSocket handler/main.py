import os
import logging
import json
import asyncio
from typing import Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from cachetools import TTLCache
import httpx
from datetime import datetime
from urllib.parse import urljoin
from fastapi.responses import HTMLResponse


log_file = "service.log"

CONFIG_FILE = 'config.json'

if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"Файл конфигурации {CONFIG_FILE} не найден.")

with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)


API_GATEWAY_URL = config.get('api_gateway_url', 'http://localhost:8500')
MAX_ATTEMPTS = config.get('max_attempts', 5)
HANDLER_ID = config.get('handler_id', 'WSH1')  # Уникальный ID для каждого обработчика
HANDLER_URL = config.get('handler_url', 'http://localhost:8001')

app = FastAPI(title=f"WebSocket Handler {HANDLER_ID}")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[
                        logging.StreamHandler(),
                        logging.FileHandler(log_file, mode='a')
                    ])
logger = logging.getLogger(HANDLER_ID)

app.state.HANDLER_ID = HANDLER_ID

user_cache = TTLCache(maxsize=1000, ttl=60)  # Кэш для недавних сопоставлений пользователь-обработчик
connected_users: Dict[str, WebSocket] = {}  # Подключенные пользователи к этому обработчику

# Создаем глобальный HTTP клиент
http_client = httpx.AsyncClient()

# Словари для хранения текущих URL сервисов
SERVICE_URLS = {
    'websocket_manager': None,
    'message_service': None,
    'auth_service': None,
}


async def get_service_url(service_name: str) -> Optional[str]:
    """
    Получает URL экземпляра сервиса из API Gateway.

    :param service_name: Название сервиса.
    :return: URL сервиса или None.
    """
    params = {'service_name': service_name}
    url = f"{API_GATEWAY_URL}/get_service_instance"
    try:
        response = await http_client.get(url, params=params)
        if response.status_code == 200:
            instance = response.json().get('instance')
            return instance['url']
        else:
            logger.error(f"Не удалось получить экземпляр {service_name} из API Gateway: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Ошибка при получении экземпляра {service_name} из API Gateway: {e}")
        return None


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
        service_url = SERVICE_URLS.get(service_name)
        if not service_url:
            service_url = await get_service_url(service_name)
            if not service_url:
                attempts += 1
                continue
            SERVICE_URLS[service_name] = service_url
        url = urljoin(service_url, path)
        try:
            response = await http_client.request(method, url, **kwargs)
            if response.status_code == 200:
                return response
            else:
                # Если получили ошибку, обновляем URL сервиса и повторяем запрос
                logger.error(f"Ошибка при обращении к {service_name}: {response.status_code} {response.text}")
                SERVICE_URLS[service_name] = None  # Сбросим URL, чтобы получить новый на следующей итерации
                attempts += 1
        except Exception as e:
            logger.error(f"Исключение при обращении к {service_name} по адресу {url}: {e}")
            SERVICE_URLS[service_name] = None
            attempts += 1
    logger.error(f"Не удалось связаться с {service_name} после {MAX_ATTEMPTS} попыток")
    return None


@app.on_event("shutdown")
async def shutdown_event():
    """Закрытие HTTP клиента при завершении работы приложения."""
    await http_client.aclose()


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """
    WebSocket эндпоинт для подключения пользователей.

    :param websocket: WebSocket соединение.
    :param user_id: Идентификатор подключающегося пользователя.
    """
    print(f"Попытка подключения к WebSocket от пользователя: {user_id}")
    await websocket.accept()
    background_task = None
    try:
        # Получение токена из параметров URL при WebSocket соединении
        query_params = dict(websocket.headers)
        token = query_params.get('token')
        if not token:
            await websocket.close(code=4001, reason="Требуется токен")
            return
        # Проверяем токен один раз при установлении соединения
        is_valid = await check_token(user_id, token)
        if not is_valid:
            await websocket.close(code=4003, reason="Неверный или истекший токен")
            return

        await register_user(user_id)
        connected_users[user_id] = websocket
        logger.info(f"Пользователь {user_id} подключен.")
        # При подключении отправляем все чаты и сообщения
        await send_all_chats_and_messages(user_id, websocket)
        # Запуск фоновой задачи для регулярной проверки новых сообщений
        background_task = asyncio.create_task(message_listener(user_id, websocket))
    except Exception as e:
        logger.error(f"Ошибка при регистрации пользователя {user_id}: {e}")
        await websocket.close(code=1000)
        return

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            if message.get('type') == 'ping':
                # Обработка сообщения типа 'ping' для поддержания соединения
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif message.get('type') == 'fetch_chats':
                # Отправка всех чатов и сообщений пользователю
                await send_all_chats_and_messages(user_id, websocket)
            elif message.get('type') == 'create_chat':
                # Создание нового чата с другим пользователем
                recipient_id = message.get('recipient_id')
                if recipient_id:
                    chat_id = await get_chat_id(user_id, recipient_id)
                    print(f"Chat created between {user_id} and {recipient_id} with chat_id: {chat_id}")
                    # Отправляем обновленный список чатов
                    await send_all_chats_and_messages(user_id, websocket)
                else:
                    logger.warning(f"Некорректный запрос на создание чата от {user_id}: {message}")
            elif message.get('type') == 'send_message':
                # Обработка входящего сообщения от пользователя
                await handle_incoming_message(user_id, message)
            else:
                logger.warning(f"Неизвестный тип сообщения от {user_id}: {message}")
    except WebSocketDisconnect:
        logger.info(f"Пользователь {user_id} отключился.")
    except Exception as e:
        logger.error(f"Ошибка с пользователем {user_id}: {e}")
    finally:
        # Отмена фоновой задачи при отключении пользователя
        if background_task:
            background_task.cancel()
        # Снятие регистрации пользователя
        await unregister_user(user_id)
        connected_users.pop(user_id, None)
        try:
            await websocket.close()
        except Exception as e:
            logger.error(f"Ошибка при закрытии WebSocket для пользователя {user_id}: {e}")


async def message_listener(user_id: str, websocket: WebSocket):
    """
    Фоновая задача для периодической отправки новых чатов и сообщений пользователю.

    :param user_id: Идентификатор пользователя.
    :param websocket: WebSocket соединение с пользователем.
    """
    try:
        while True:
            await asyncio.sleep(5)  # Проверяем каждые 5 секунд (можете настроить интервал)
            await send_new_chats_and_messages(user_id, websocket)
    except asyncio.CancelledError:
        pass  # Задача была отменена, выходим из функции
    except Exception as e:
        logger.error(f"Ошибка в message_listener для пользователя {user_id}: {e}")


async def register_user(user_id: str):
    """
    Регистрирует пользователя в WebSocket Manager.

    :param user_id: Идентификатор пользователя для регистрации.
    :raises HTTPException: Если регистрация неудачна.
    """
    print(f"Registering user {user_id} with WebSocket Manager.")
    payload = {
        "user_id": user_id,
        "websocket_handler_id": HANDLER_ID
    }
    response = await request_with_retry('POST', 'websocket_manager', '/connect', json=payload)
    if not response or response.status_code != 200:
        raise HTTPException(status_code=response.status_code if response else 500, detail=f"Не удалось зарегистрировать пользователя {user_id}")


async def unregister_user(user_id: str):
    """
    Снимает регистрацию пользователя в WebSocket Manager.

    :param user_id: Идентификатор пользователя для снятия регистрации.
    """
    print(f"Unregistering user {user_id} from WebSocket Manager.")
    payload = {
        "user_id": user_id
    }
    response = await request_with_retry('POST', 'websocket_manager', '/disconnect', json=payload)
    if not response or response.status_code != 200:
        logger.warning(f"Не удалось снять регистрацию пользователя {user_id}.")


async def handle_incoming_message(sender_id: str, message_data: Dict):
    """
    Обрабатывает входящее сообщение от пользователя.

    :param sender_id: Идентификатор отправителя сообщения.
    :param message_data: Данные сообщения, включая recipient_id, content и chat_id.
    """
    print(f"Handling incoming message from {sender_id}: {message_data}")
    recipient_id = message_data.get('recipient_id')
    content = message_data.get('content')
    chat_id = message_data.get('chat_id')  # Предполагаем, что клиент передает chat_id

    if not recipient_id or not content:
        logger.warning(f"Некорректное сообщение от {sender_id}: {message_data}")
        return

    # Сохранение сообщения через Message Service
    message_id = await save_message(sender_id, recipient_id, content, chat_id)
    print(f"Message saved with ID {message_id}")

    # Создаем объект сообщения для отправки
    outgoing_message = {
        "type": "message",
        "chat_id": chat_id,
        "sender_id": sender_id,
        "recipient_id": recipient_id,
        "content": content,
        "message_id": message_id,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Проверка, подключен ли получатель к этому обработчику
    recipient_websocket = connected_users.get(recipient_id)
    if recipient_websocket:
        # Получатель подключен к этому обработчику
        print(f"Delivering message to connected recipient {recipient_id}")
        await deliver_message(recipient_websocket, outgoing_message)
    else:
        # Получатель не подключен к этому обработчику, проверка кэша или WebSocket Manager
        handler_id = user_cache.get(recipient_id)
        if not handler_id:
            handler_id = await get_handler_for_user(recipient_id)
            if handler_id:
                user_cache[recipient_id] = handler_id

        if handler_id == HANDLER_ID:
            # Крайний случай: получатель должен быть подключен, но не найден
            logger.warning(f"Получатель {recipient_id} должен быть подключен, но не найден.")
        elif handler_id:
            # Отправка сообщения обработчику, к которому подключен получатель
            print(f"Forwarding message to handler {handler_id} for recipient {recipient_id}")
            await forward_message_to_handler(handler_id, outgoing_message)
        else:
            # Получатель не в сети
            # Обработка доставки сообщений для оффлайн-получателей
            logger.info(f"Получатель {recipient_id} не в сети.")
            print(f"Recipient {recipient_id} is offline. Handling offline delivery.")
            await handle_offline_recipient(recipient_id, message_id)


async def save_message(sender_id: str, recipient_id: str, content: str, chat_id: Optional[str]) -> str:
    """
    Сохраняет сообщение через Message Service.

    :param sender_id: Идентификатор отправителя.
    :param recipient_id: Идентификатор получателя.
    :param content: Содержимое сообщения.
    :param chat_id: Идентификатор чата (если есть).
    :return: Идентификатор сохраненного сообщения.
    :raises HTTPException: Если сохранение сообщения неудачно.
    """
    print(f"Saving message from {sender_id} to {recipient_id} in chat {chat_id}")
    try:
        # Если chat_id не передан, получаем или создаем chat_id между sender_id и recipient_id
        if not chat_id:
            chat_id = await get_chat_id(sender_id, recipient_id)
            if not chat_id:
                raise HTTPException(status_code=500, detail="Не удалось получить chat_id")

        # Формирование данных сообщения
        message_data = {
            "chat_id": chat_id,
            "sender_id": sender_id,
            "content": content
        }
        response = await request_with_retry('POST', 'message_service', '/messages/', json=message_data)
        if response and response.status_code == 200:
            message = response.json()
            message_id = message.get('_id')
            logger.info(f"Сообщение сохранено с ID {message_id}")
            return message_id
        else:
            logger.error(f"Не удалось сохранить сообщение: {response.text if response else 'No response'}")
            raise HTTPException(status_code=response.status_code if response else 500, detail="Не удалось сохранить сообщение")
    except Exception as e:
        logger.error(f"Ошибка при сохранении сообщения: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


async def update_message_status(message_id: str, user_id: str, status: str):
    """
    Обновляет статус сообщения для определенного пользователя.

    :param message_id: Идентификатор сообщения.
    :param user_id: Идентификатор пользователя.
    :param status: Новый статус сообщения (например, 'delivered' или 'read').
    """
    print(f"Updating message status for message {message_id} to {status} for user {user_id}")
    try:
        if user_id is None:
            logger.error(f"Не удается обновить статус сообщения: значение user_id для сообщения равно None {message_id}")
            return
        status_data = {
            "receiver_id": user_id,
            "status": status
        }
        path = f"/messages/{message_id}/status"
        response = await request_with_retry('PUT', 'message_service', path, json=status_data)
        if response and response.status_code == 200:
            logger.info(f"Статус сообщения {message_id} для пользователя {user_id} обновлен на {status}")
        else:
            logger.error(f"Не удалось обновить статус сообщения: {response.text if response else 'No response'}")
    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса сообщения: {e}")


async def get_chat_id(user1_id: str, user2_id: str) -> str:
    """
    Получает идентификатор чата между двумя пользователями или создает новый чат.

    :param user1_id: Идентификатор первого пользователя.
    :param user2_id: Идентификатор второго пользователя.
    :return: Идентификатор чата.
    :raises HTTPException: Если не удалось получить или создать чат.
    """
    print(f"Fetching chat ID between {user1_id} and {user2_id}")
    try:
        # Сначала проверяем, существует ли чат
        path = f"/chats/{user1_id}"
        response = await request_with_retry('GET', 'message_service', path)
        if response and response.status_code == 200:
            chats = response.json()
            for chat in chats:
                participants = set(chat.get('participants', []))
                if participants == {user1_id, user2_id}:
                    return chat['_id']
        else:
            logger.error(f"Не удалось получить чаты пользователя {user1_id}: {response.text if response else 'No response'}")

        # Если чат не существует, создаем его
        chat_data = {
            "participants": [user1_id, user2_id]
        }
        response = await request_with_retry('POST', 'message_service', '/chats/', json=chat_data)
        if response and response.status_code == 200:
            chat = response.json()
            chat_id = chat.get('_id')
            if not chat_id:
                logger.error("Не удалось получить 'id' чата из ответа")
                raise HTTPException(status_code=500, detail="Не удалось получить 'id' чата")
            return chat_id
        else:
            logger.error(f"Не удалось создать чат: {response.text if response else 'No response'}")
            raise HTTPException(status_code=response.status_code if response else 500, detail="Не удалось создать чат")
    except Exception as e:
        logger.error(f"Ошибка при получении или создании чата: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


async def get_handler_for_user(user_id: str) -> Optional[str]:
    """
    Получает идентификатор обработчика WebSocket, к которому подключен пользователь.

    :param user_id: Идентификатор пользователя.
    :return: Идентификатор обработчика или None, если пользователь оффлайн.
    :raises HTTPException: Если не удалось получить обработчик.
    """
    print(f"Fetching handler for user {user_id}")
    path = f"/handler/{user_id}"
    response = await request_with_retry('GET', 'websocket_manager', path)
    if response and response.status_code == 200:
        data = response.json()
        return data.get('websocket_handler_id')
    elif response and response.status_code == 404:
        return None
    else:
        raise HTTPException(status_code=response.status_code if response else 500, detail=f"Не удалось получить обработчик для пользователя {user_id}")


async def forward_message_to_handler(handler_id: str, message_data: Dict):
    """
    Пересылает сообщение другому обработчику WebSocket.

    :param handler_id: Идентификатор целевого обработчика.
    :param message_data: Данные сообщения для пересылки.
    """
    print(f"Forwarding message to handler {handler_id}")
    # Получаем URL обработчика из API Gateway
    handler_url = await get_handler_url(handler_id)
    if not handler_url:
        logger.error(f"URL для обработчика {handler_id} не найден.")
        return

    url = urljoin(handler_url, '/forward_message')
    try:
        response = await http_client.post(url, json=message_data)
        if response.status_code != 200:
            logger.error(f"Не удалось переслать сообщение обработчику {handler_id}: {response.text}")
        else:
            logger.info(f"Сообщение переслано обработчику {handler_id}.")
    except Exception as e:
        logger.error(f"Ошибка при пересылке сообщения обработчику {handler_id}: {e}")


async def get_handler_url(handler_id: str) -> Optional[str]:
    """
    Получает URL обработчика WebSocket по его идентификатору.

    :param handler_id: Идентификатор обработчика.
    :return: URL обработчика или None.
    """
    # По умолчанию предполагаем, что обработчики зарегистрированы в WebSocket Manager
    path = f"/handler_url/{handler_id}"
    response = await request_with_retry('GET', 'websocket_manager', path)
    if response and response.status_code == 200:
        data = response.json()
        return data.get('websocket_handler_url')
    else:
        logger.error(f"Не удалось получить URL обработчика {handler_id}")
        return None


async def send_new_chats_and_messages(user_id: str, websocket: WebSocket):
    """
    Отправляет новые чаты и сообщения пользователю.

    :param user_id: Идентификатор пользователя.
    :param websocket: WebSocket соединение с пользователем.
    """
    print(f"Sending new chats and messages to user {user_id}")
    try:
        # Получение новых чатов, статус которых для данного пользователя 'undelivered'
        path = f"/chats/{user_id}/new"
        response = await request_with_retry('GET', 'message_service', path)
        if response and response.status_code == 200:
            chats = response.json()
            if chats:
                # Отправляем новые чаты пользователю
                await websocket.send_text(json.dumps({"type": "new_chats", "data": chats}))
                # Обновляем статус чатов на "delivered" для пользователя
                for chat in chats:
                    chat_id = chat["_id"]
                    # Обновляем статус чата
                    await update_chat_status(chat_id, user_id, status="delivered")
                    # Для каждого чата получаем новые сообщения для пользователя
                    messages_path = f"/messages/{chat_id}/new/{user_id}"
                    messages_response = await request_with_retry('GET', 'message_service', messages_path)
                    if messages_response and messages_response.status_code == 200:
                        messages = messages_response.json()
                        if messages:
                            # Отправляем сообщения пользователю
                            await websocket.send_text(json.dumps({"type": "new_messages", "chat_id": chat_id, "data": messages}))
                            # Обновляем статус сообщений на "delivered" для пользователя
                            for message in messages:
                                message_id = message["_id"]
                                await update_message_status(message_id, user_id, status="delivered")
        else:
            logger.error(f"Не удалось получить новые чаты для пользователя {user_id}: {response.text if response else 'No response'}")
    except Exception as e:
        logger.error(f"Ошибка при отправке новых чатов и сообщений: {e}")


async def send_all_chats_and_messages(user_id: str, websocket: WebSocket):
    """
    Отправляет все чаты и сообщения пользователю.

    :param user_id: Идентификатор пользователя.
    :param websocket: WebSocket соединение с пользователем.
    """
    print(f"Sending all chats and messages to user {user_id}")
    try:
        # Получение всех чатов пользователя
        path = f"/chats/{user_id}"
        response = await request_with_retry('GET', 'message_service', path)
        if response and response.status_code == 200:
            chats = response.json()
            if chats:
                # Отправляем чаты пользователю
                await websocket.send_text(json.dumps({"type": "all_chats", "data": chats}))
                # Для каждого чата получаем все сообщения
                for chat in chats:
                    chat_id = chat["_id"]
                    messages_path = f"/messages/{chat_id}"
                    messages_response = await request_with_retry('GET', 'message_service', messages_path)
                    if messages_response and messages_response.status_code == 200:
                        messages = messages_response.json()
                        if messages:
                            # Отправляем сообщения пользователю
                            await websocket.send_text(json.dumps({"type": "all_messages", "chat_id": chat_id, "data": messages}))
                            # Обновляем статус сообщений на "delivered" для пользователя
                            for message in messages:
                                if message["sender_id"] != user_id:
                                    message_id = message["_id"]
                                    await update_message_status(message_id, user_id, status="delivered")
                logger.info(f"Чаты и сообщения отправлены пользователю {user_id}")
        else:
            logger.error(f"Не удалось получить чаты для пользователя {user_id}: {response.text if response else 'No response'}")
    except Exception as e:
        logger.error(f"Ошибка при отправке чатов и сообщений: {e}")


async def update_chat_status(chat_id: str, user_id: str, status: str):
    """
    Обновляет статус чата для определенного пользователя.

    :param chat_id: Идентификатор чата.
    :param user_id: Идентификатор пользователя.
    :param status: Новый статус чата (например, 'delivered' или 'read').
    """
    print(f"Updating chat status for chat {chat_id} to {status} for user {user_id}")
    try:
        status_data = {
            "receiver_id": user_id,
            "status": status
        }
        path = f"/chats/{chat_id}/status"
        response = await request_with_retry('PUT', 'message_service', path, json=status_data)
        if response and response.status_code == 200:
            logger.info(f"Статус чата {chat_id} для пользователя {user_id} обновлен на {status}")
        else:
            logger.error(f"Не удалось обновить статус чата: {response.text if response else 'No response'}")
    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса чата: {e}")


@app.post("/forward_message")
async def forward_message_endpoint(message_data: Dict):
    """
    Эндпоинт для получения пересылаемых сообщений от других обработчиков.

    :param message_data: Данные сообщения, включая recipient_id и content.
    :return: Статус доставки сообщения.
    """
    print(f"Received forwarded message: {message_data}")
    recipient_id = message_data.get('recipient_id')
    recipient_websocket = connected_users.get(recipient_id)
    if recipient_websocket:
        await deliver_message(recipient_websocket, message_data)
        # Обновление статуса сообщения через Message Service
        await update_message_status(message_data.get('message_id'), recipient_id, status="delivered")
        return {"status": "delivered"}
    else:
        logger.warning(f"Получатель {recipient_id} не подключен к этому обработчику.")
        return {"status": "not_delivered"}


async def deliver_message(websocket: WebSocket, message_data: Dict):
    """
    Доставляет сообщение получателю через WebSocket.

    :param websocket: WebSocket соединение с получателем.
    :param message_data: Данные сообщения для отправки.
    """
    print(f"Delivering message to user {message_data.get('recipient_id')}: {message_data}")
    await websocket.send_text(json.dumps(message_data))
    logger.info(f"Сообщение доставлено пользователю {message_data.get('recipient_id')}")
    # Обновляем статус сообщения на "delivered"
    await update_message_status(message_data.get('message_id'), message_data.get('recipient_id'), status="delivered")


async def handle_offline_recipient(recipient_id: str, message_id: str):
    """
    Обрабатывает сценарий, когда получатель сообщения оффлайн.

    :param recipient_id: Идентификатор оффлайн-получателя.
    :param message_id: Идентификатор сообщения.
    """
    print(f"Handling offline recipient {recipient_id} for message {message_id}")
    logger.info(f"Обработка оффлайн-получателя {recipient_id} для сообщения {message_id}.")
    # Здесь вы можете добавить логику для отправки уведомления через Push Notification Service


async def check_token(user_id: str, token: str) -> bool:
    """
    Проверяет токен пользователя через API Gateway (Auth Service).

    :param user_id: Идентификатор пользователя.
    :param token: Токен пользователя.
    :return: True, если токен действителен, иначе False.
    """
    params = {"uid": user_id, "token": token}
    response = await request_with_retry('GET', 'auth_service', '/token_check', params=params)
    if response and response.status_code == 200:
        return True
    else:
        logger.error(f"Неверный или просроченный токен для пользователя {user_id}")
        return False


@app.get("/")
async def health():
    """
    Эндпоинт для проверки состояния сервиса.

    :return: Сообщение о том, что сервис работает.
    """
    return {"status": "WebSocket handler is work!"}


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
                    <h1>WebSocket handler Logs</h1>
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


@app.get("/test_client")
async def test_client():
    """
    Эндпоинт для проверки работы сервера и демонстрационного клиента.
    (Сейчас не работает так как был написан для более старых версий микро-сервисов)

    :return: HTML страница с клиентским интерфейсом.
    """
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>WebSocket Messenger</title>
        <style>
            body { font-family: Arial, sans-serif; }
            #login, #messenger { max-width: 600px; margin: auto; }
            #login { margin-top: 50px; text-align: center; }
            #messenger { display: none; }
            #chat-list { list-style-type: none; padding: 0; }
            #chat-list li { padding: 10px; border-bottom: 1px solid #ccc; cursor: pointer; }
            #messages { border: 1px solid #ccc; padding: 10px; height: 300px; overflow-y: scroll; }
            #newMessage { width: calc(100% - 100px); }
            .button { padding: 5px 10px; cursor: pointer; }
        </style>
    </head>
    <body>
        <div id="login">
            <h2>Добро пожаловать в мессенджер</h2>
            <input id="username" type="text" placeholder="Введите ваше имя" />
            <button onclick="connect()">Подключиться</button>
        </div>
        <div id="messenger">
            <div>
                <button onclick="disconnect()">Отключиться</button>
                <button onclick="createChat()">Создать чат</button>
            </div>
            <h3>Список чатов</h3>
            <ul id="chat-list"></ul>
            <div id="chat-window" style="display: none;">
                <button onclick="backToChatList()">Назад к списку чатов</button>
                <h3 id="chat-recipient">Чат с: </h3>
                <div id="messages"></div>
                <input id="newMessage" type="text" placeholder="Введите сообщение" />
                <button onclick="sendMessage()">Отправить</button>
            </div>
        </div>
        <script>
            let ws;  // Переменная для хранения WebSocket соединения
            let username;  // Имя пользователя, введенное при подключении
            let currentChatId;  // Идентификатор текущего открытого чата
            let currentRecipientId;  // Идентификатор текущего собеседника
            let chats = {};  // Объект для хранения чатов и сообщений

            // Функция для подключения к WebSocket серверу
            function connect() {
                username = document.getElementById('username').value;
                if (!username) {
                    alert('Пожалуйста, введите ваше имя.');
                    return;
                }
                // Создание нового WebSocket соединения
                ws = new WebSocket(`ws://${window.location.host}/ws/${username}`);

                // Обработчик события открытия соединения
                ws.onopen = function() {
                    document.getElementById('login').style.display = 'none';
                    document.getElementById('messenger').style.display = 'block';
                };

                // Обработчик события получения сообщения
                ws.onmessage = function(event) {
                    let data = JSON.parse(event.data);
                    console.log('Received message:', data);

                    // Обработка получения списка чатов
                    if (data.type === 'all_chats' || data.type === 'new_chats') {
                        data.data.forEach(chat => {
                            let chatId = chat._id;
                            chats[chatId] = chat;
                            chats[chatId].messages = chats[chatId].messages || [];
                        });
                        displayChats();
                    } 
                    // Обработка получения сообщений из чата
                    else if (data.type === 'all_messages' || data.type === 'new_messages') {
                        let chatId = data.chat_id;
                        if (!chats[chatId]) {
                            chats[chatId] = {messages: []};
                        }
                        chats[chatId].messages = chats[chatId].messages || [];
                        chats[chatId].messages.push(...data.data);
                        if (currentChatId === chatId) {
                            displayMessages(chatId);
                        }
                    } 
                    // Обработка получения нового сообщения
                    else if (data.type === 'message') {
                        let chatId = data.chat_id;
                        if (!chats[chatId]) {
                            chats[chatId] = {messages: []};
                            fetchChats();  // Обновляем список чатов
                        }
                        chats[chatId].messages.push(data);
                        if (currentChatId === chatId) {
                            displayMessages(chatId);
                        }
                    } 
                    // Обработка ответа на пинг
                    else if (data.type === 'pong') {
                        console.log('Received pong');
                    }
                };

                // Обработчик события закрытия соединения
                ws.onclose = function() {
                    document.getElementById('login').style.display = 'block';
                    document.getElementById('messenger').style.display = 'none';
                    document.getElementById('chat-window').style.display = 'none';
                };

                // Обработчик ошибки соединения
                ws.onerror = function(error) {
                    console.error('WebSocket error: ', error);
                };
            }

            // Функция для отключения от WebSocket сервера
            function disconnect() {
                if (ws) {
                    ws.close();
                }
            }

            // Функция для запроса всех чатов и сообщений
            function fetchChats() {
                ws.send(JSON.stringify({type: 'fetch_chats'}));
            }

            // Функция для отображения списка чатов
            function displayChats() {
                let chatList = document.getElementById('chat-list');
                chatList.innerHTML = '';
                for (let chatId in chats) {
                    let chat = chats[chatId];
                    let recipientId = chat.participants.find(p => p !== username);
                    let li = document.createElement('li');
                    li.textContent = `Чат с ${recipientId}`;
                    li.onclick = function() {
                        openChat(chatId, recipientId);
                    };
                    chatList.appendChild(li);
                }
            }

            // Функция для создания нового чата
            function createChat() {
                let recipientId = prompt('Введите имя пользователя для создания чата:');
                if (!recipientId || recipientId === username) {
                    alert('Некорректное имя пользователя.');
                    return;
                }
                ws.send(JSON.stringify({type: 'create_chat', recipient_id: recipientId}));
            }

            // Функция для открытия чата
            function openChat(chatId, recipientId) {
                currentChatId = chatId;
                currentRecipientId = recipientId;
                document.getElementById('chat-window').style.display = 'block';
                document.getElementById('chat-recipient').textContent = `Чат с: ${recipientId}`;
                displayMessages(chatId);
            }

            // Функция для отображения сообщений в чате
            function displayMessages(chatId) {
                let messagesDiv = document.getElementById('messages');
                messagesDiv.innerHTML = '';
                let chat = chats[chatId];
                if (chat && chat.messages) {
                    chat.messages.forEach(msg => {
                        let msgDiv = document.createElement('div');
                        msgDiv.textContent = `${msg.sender_id}: ${msg.content}`;
                        messagesDiv.appendChild(msgDiv);
                    });
                }
            }

            // Функция для отправки сообщения
            function sendMessage() {
                let content = document.getElementById('newMessage').value;
                if (!content) {
                    alert('Введите сообщение.');
                    return;
                }
                let message = {
                    type: 'send_message',
                    recipient_id: currentRecipientId,
                    content: content,
                    chat_id: currentChatId
                };
                ws.send(JSON.stringify(message));
                // Добавляем сообщение в чат
                let chat = chats[currentChatId];
                chat.messages.push({sender_id: username, content: content});
                displayMessages(currentChatId);
                document.getElementById('newMessage').value = '';
            }

            // Функция для возврата к списку чатов
            function backToChatList() {
                document.getElementById('chat-window').style.display = 'none';
                currentChatId = null;
                currentRecipientId = null;
            }

            // Функция для поддержания соединения
            setInterval(function() {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({type: 'ping'}));
                }
            }, 30000);  // Отправляем ping каждые 30 секунд
        </script>
    </body>
    </html>
    """)
