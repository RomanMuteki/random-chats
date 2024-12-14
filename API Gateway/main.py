import uvicorn
import os
import json
import threading
from fastapi import FastAPI, Request, HTTPException, Response, Header
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
from typing import Dict, List, Optional
from urllib.parse import urljoin
from fastapi.responses import HTMLResponse
import logging
from pydantic import BaseModel


log_file = "service.log"

CONFIG_FILE = 'config.json'

if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"Файл конфигурации {CONFIG_FILE} не найден.")

with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

HOST = config.get('host', '0.0.0.0')
PORT = config.get('port', 8500)
MAX_ATTEMPTS = config.get('max_attempts', 5)

# Инициализация экземпляров сервисов и указателей
services = {
    'auth_service': {
        'instances': config.get('auth_service_instances', []),
        'pointer': 0,
        'lock': threading.Lock()
    },
    'matching_service': {
        'instances': config.get('matching_service_instances', []),
        'pointer': 0,
        'lock': threading.Lock()
    },
    'websocket_handlers': {
        'instances': config.get('websocket_handlers', []),
        'pointer': 0,
        'lock': threading.Lock()
    },
    'websocket_manager': {
        'instances': config.get('websocket_manager_instances', []),
        'pointer': 0,
        'lock': threading.Lock()
    },
    'message_service': {
        'instances': config.get('message_service_instances', []),
        'pointer': 0,
        'lock': threading.Lock()
    }
}

app = FastAPI(title="API Gateway")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[
                        logging.StreamHandler(),
                        logging.FileHandler(log_file, mode='a')
                    ])
logger = logging.getLogger("API Gateway")


class CreateRequest(BaseModel):
    token: str
    uid: str


async def get_work_instance(service_name: str) -> Dict or None:
    """
    Получает рабочий экземпляр сервиса с использованием балансировки нагрузки, проверяя доступность каждого экземпляра.

    :param service_name: Название сервиса.
    :return: Словарь с информацией об рабочем экземпляре сервиса или None, если все сервисы не работают.
    """
    logger.info(f"Получение рабочего экземпляра для сервиса {service_name}")
    service = services.get(service_name)
    if not service or not service['instances']:
        logger.error(f"Нет доступных экземпляров для {service_name}")
        raise HTTPException(status_code=503, detail=f"Нет доступных экземпляров для {service_name}")

    start_pointer = service['pointer']
    attempts = 0
    num_instances = len(service['instances'])

    while attempts < num_instances:
        instance = service['instances'][(start_pointer + attempts) % num_instances]
        url = urljoin(instance['url'], "/")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=1.0)
                if response.status_code == 200:
                    # Если сервис отвечает статусом 200, возвращаем его
                    service['pointer'] = (start_pointer + attempts + 1) % num_instances
                    logger.info(f"Экземпляр {instance['url']} сервиса {service_name} доступен")
                    return instance
        except Exception as e:
            attempts += 1
            # logger.error(f"Ошибка при проверке экземпляра {instance['url']} сервиса {service_name}: {e}")
            continue  # Если ошибка (например, сервис не доступен), продолжаем попытки
        attempts += 1

    logger.error(f"Ни один экземпляр сервиса {service_name} не работает")
    return None  # Если ни один экземпляр не работает


async def validate_token(token: str, uid: str) -> bool:
    """
    Проверяет токен, перенаправляя его в Auth Service.
    """
    logger.info(f"Валидация токена для пользователя {uid} с токеном {token}")
    service_name = 'auth_service'
    attempts = 0
    max_attempts = len(services[service_name]['instances'])
    while attempts < max_attempts:
        instance = await get_work_instance(service_name)
        url = urljoin(instance['url'], '/token_check')
        json_data = {'token': token, 'uid': uid}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=json_data)
                if response.status_code == 200:
                    logger.info(f"Токен пользователя {uid} действителен")
                    return True
                else:
                    logger.warning(f"Токен пользователя {uid} недействителен. Детали: {response.json().get('detail')}")
                    return False
        except Exception as e:
            logger.error(f"Ошибка при валидации токена пользователя {uid}: {e}")
            attempts += 1
    logger.error(f"Не удалось валидировать токен пользователя {uid} после {MAX_ATTEMPTS} попыток")
    return False


@app.post("/get_websocket_handler")
async def get_websocket_handler(request: Request):
    """
    Предоставляет доступный WebSocket Handler клиенту.

    :param request: :param request: Объект запроса FastAPI.
    :return: JSON с URL и ID обработчика.
    :raises HTTPException: Если аутентификация не удалась.
    """
    try:
        request_body = await request.json()

        token = request_body.get('token')
        uid = request_body.get('uid')
    except json.JSONDecodeError:
        logger.error("Ошибка при декодировании JSON тела запроса")
        raise HTTPException(status_code=400, detail="Неправильный формат JSON тела запроса")

    logger.info(f"Получение доступного WebSocket Handler для пользователя {uid}")
    if not token or not uid:
        logger.error("Отсутствуют токен или UID в запросе для получения WebSocket Handler")
        raise HTTPException(status_code=401, detail="Необходима аутентификация. Должны быть предоставлены токен и UID.")

    is_valid = await validate_token(token, uid)
    if not is_valid:
        logger.error(f"Неверный или истекший токен для пользователя {uid}")
        raise HTTPException(status_code=401, detail="Неверный или истекший токен")

    handler = await get_work_instance('websocket_handlers')
    handler_url = handler['url']
    handler_id = handler.get('id')
    logger.info(f"Доступный WebSocket Handler для пользователя {uid}: URL {handler_url}, ID {handler_id}")
    return {'websocket_handler_url': handler_url, 'handler_id': handler_id}


# Прокси-эндпоинты для Auth Service
@app.post("/register")
async def register(request: Request):
    """
    Проксирует запрос на регистрацию в Auth Service.

    :param request: Объект запроса FastAPI.
    :return: Ответ от Auth Service.
    """
    logger.info("Проксирование запроса на регистрацию в Auth Service")
    response = await proxy_request(request, 'auth_service')
    return response


@app.post("/login")
async def login(request: Request):
    """
    Проксирует запрос на вход в систему в Auth Service.

    :param request: Объект запроса FastAPI.
    :return: Ответ от Auth Service.
    """
    logger.info("Проксирование запроса на вход в Auth Service")
    response = await proxy_request(request, 'auth_service')
    return response


@app.post("/token_login")
async def token_login(request: Request):
    """
    Проксирует запрос на вход по токену в Auth Service.

    :param request: Объект запроса FastAPI.
    :return: Ответ от Auth Service.
    """
    logger.info("Проксирование запроса на вход по токену в Auth Service")
    response = await proxy_request(request, 'auth_service')
    return response


@app.get("/token_check")
async def token_check(token: str, uid: str):
    """
    Проксирует запрос на проверку токена в Auth Service.

    :param token: Токен пользователя.
    :param uid: UID пользователя.
    :return: Ответ от Auth Service.
    """
    logger.info(f"Проксирование запроса на проверку токена для пользователя {uid}")
    service_name = 'auth_service'
    attempts = 0
    max_attempts = len(services[service_name]['instances'])
    while attempts < max_attempts:
        instance = await get_work_instance(service_name)
        url = urljoin(instance['url'], '/token_check')
        params = {'token': token, 'uid': uid}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=5)
                logger.info(f"Ответ от Auth Service для проверки токена: {response.status_code}")
                return Response(
                    status_code=response.status_code,
                    content=response.content,
                    headers={k: v for k, v in response.headers.items() if k.lower() != 'content-encoding'}
                )
        except Exception as e:
            logger.error(f"Ошибка при проксировании запроса на проверку токена для {uid}: {e}")
            attempts += 1
    logger.error(f"Все экземпляры {service_name} недоступны для проверки токена {uid}")
    raise HTTPException(status_code=503, detail=f"Все экземпляры {service_name} недоступны")


# Прокси-эндпоинты для Matching Service
@app.post("/matching")
async def matching(request: Request):
    """
    Проксирует запрос на подбор пары в Matching Service после аутентификации пользователя.

    :param request: Объект запроса FastAPI.
    :return: Ответ от Matching Service.
    :raises HTTPException: Если аутентификация не удалась.
    """
    try:
        request_body = await request.json()

        token = request_body.get('token')
        uid = request_body.get('uid')
    except json.JSONDecodeError:
        logger.error("Ошибка при декодировании JSON тела запроса")
        raise HTTPException(status_code=400, detail="Неправильный формат JSON тела запроса")

    logger.info(f"Запрос на подбор пары для пользователя {uid}")
    if not token or not uid:
        logger.error("Отсутствуют токен или UID при подборе пары")
        raise HTTPException(status_code=401, detail="Необходима аутентификация. Должны быть предоставлены токен и UID.")

    is_valid = await validate_token(token, uid)
    if not is_valid:
        logger.error(f"Неверный или истекший токен для подбора пары у пользователя {uid}")
        raise HTTPException(status_code=401, detail="Неверный или истекший токен")

    response = await proxy_request(request, 'matching_service')
    return response


# Функция для проксирования запросов к соответствующему сервису
async def proxy_request(request: Request, service_name: str):
    """
    Проксирует входящий запрос в указанный сервис с использованием балансировки нагрузки и логики повторных попыток.

    :param request: Объект запроса FastAPI.
    :param service_name: Название сервиса, которому нужно проксировать запрос.
    :return: Ответ от сервиса.
    :raises HTTPException: Если все экземпляры сервиса недоступны.
    """
    logger.info(f"Проксирование входящего запроса в {service_name}")
    max_attempts = min(MAX_ATTEMPTS, len(services[service_name]['instances']))
    attempts = 0
    # Извлечение пути и параметров запроса
    path = request.url.path
    query = str(request.url.query)
    while attempts < max_attempts:
        instance = await get_work_instance(service_name)
        instance_url = instance['url']
        url = urljoin(instance_url, path)
        if query:
            url = f"{url}?{query}"
        headers = dict(request.headers)
        method = request.method
        content = await request.body()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(method, url, headers=headers, content=content, timeout=4)
                logger.info(f"Успешный проксируемый запрос в {service_name} на {url} завершен")
                return Response(
                    status_code=response.status_code,
                    content=response.content,
                    headers={k: v for k, v in response.headers.items() if k.lower() != 'content-encoding'}
                )
        except Exception as e:
            logger.error(f"Ошибка проксирования для {service_name} на попытке {attempts+1}: {e}")
            attempts += 1
    logger.error(f"Все экземпляры {service_name} недоступны для проксирования")
    raise HTTPException(status_code=503, detail=f"Все экземпляры {service_name} недоступны")


@app.get("/get_service_instance")
async def get_service_instance(service_name: str):
    """
    Предоставляет другой-рабочий экземпляр сервиса микросервису.

    :param service_name: Название сервиса.
    :return: JSON с информацией об экземпляре.
    :raises HTTPException: Если сервис не найден.
    """
    logger.info(f"Получение рабочего экземпляра для {service_name}")
    if service_name not in services:
        logger.error(f"Рабочий сервис {service_name} не найден")
        raise HTTPException(status_code=404, detail=f"Рабочий сервис {service_name} не найден")
    instance = await get_work_instance(service_name)
    logger.info(f"Предоставление экземпляра {instance['url']} для сервиса {service_name}")
    return {'instance': instance}


@app.get("/")
async def health():
    """
    Эндпоинт для проверки состояния сервиса.

    :return: Сообщение о том, что сервис работает.
    """
    logger.info("Проверка состояния API Gateway")
    return {"status": "API Gateway is work!"}


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
                    <h1>API Gateway Logs</h1>
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


if __name__ == "__main__":
    logger.info(f"Запуск API Gateway на {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)
