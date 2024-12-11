import os
import json
import threading
from fastapi import FastAPI, Request, HTTPException, Depends, Response, Header
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
from typing import Dict, List, Optional
from urllib.parse import urljoin

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


def get_next_instance(service_name: str) -> Dict:
    """
    Получает следующий доступный экземпляр сервиса с использованием балансировки нагрузки Round Robin.

    :param service_name: Название сервиса.
    :return: Словарь с информацией об экземпляре сервиса.
    :raises HTTPException: Если нет доступных экземпляров для сервиса.
    """
    service = services.get(service_name)
    if not service or not service['instances']:
        raise HTTPException(status_code=503, detail=f"Нет доступных экземпляров для {service_name}")

    with service['lock']:
        pointer = service['pointer']
        instance = service['instances'][pointer]
        service['pointer'] = (pointer + 1) % len(service['instances'])
    return instance

# Зависимость для проверки токена
async def validate_token(token: str, uid: str) -> bool:
    """
    Проверяет токен, перенаправляя его в Auth Service.

    :param token: Токен пользователя.
    :param uid: Уникальный идентификатор пользователя.
    :return: True, если токен действителен, иначе False.
    """
    service_name = 'auth_service'
    attempts = 0
    max_attempts = len(services[service_name]['instances'])
    while attempts < max_attempts:
        instance = get_next_instance(service_name)
        url = urljoin(instance['url'], '/token_check')
        params = {'token': token, 'uid': uid}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=5)
                if response.status_code == 200:
                    return True
                else:
                    # Токен недействителен или другая ошибка
                    return False
        except Exception:
            attempts += 1
    return False


# Эндпоинт для клиентов, чтобы получить доступный WebSocket Handler
@app.get("/get_websocket_handler")
async def get_websocket_handler(token: str = Header(None), uid: str = Header(None)):
    """
    Предоставляет доступный WebSocket Handler клиенту.

    :param token: Токен пользователя, передается в заголовках.
    :param uid: Уникальный идентификатор пользователя, передается в заголовках.
    :return: JSON с URL и ID обработчика.
    :raises HTTPException: Если аутентификация не удалась.
    """
    if not token or not uid:
        raise HTTPException(status_code=401, detail="Необходима аутентификация. Должны быть предоставлены токен и UID.")

    is_valid = await validate_token(token, uid)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Неверный или истекший токен")

    handler = get_next_instance('websocket_handlers')
    handler_url = handler['url']
    handler_id = handler.get('id')
    return {'websocket_handler_url': handler_url, 'handler_id': handler_id}


# Прокси-эндпоинты для Auth Service
@app.post("/register")
async def register(request: Request):
    """
    Проксирует запрос на регистрацию в Auth Service.

    :param request: Объект запроса FastAPI.
    :return: Ответ от Auth Service.
    """
    response = await proxy_request(request, 'auth_service')
    return response


@app.post("/login")
async def login(request: Request):
    """
    Проксирует запрос на вход в систему в Auth Service.

    :param request: Объект запроса FastAPI.
    :return: Ответ от Auth Service.
    """
    response = await proxy_request(request, 'auth_service')
    return response


@app.post("/token_login")
async def token_login(request: Request):
    """
    Проксирует запрос на вход по токену в Auth Service.

    :param request: Объект запроса FastAPI.
    :return: Ответ от Auth Service.
    """
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
    service_name = 'auth_service'
    attempts = 0
    max_attempts = len(services[service_name]['instances'])
    while attempts < max_attempts:
        instance = get_next_instance(service_name)
        url = urljoin(instance['url'], '/token_check')
        params = {'token': token, 'uid': uid}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=5)
                return Response(
                    status_code=response.status_code,
                    content=response.content,
                    headers={k: v for k, v in response.headers.items() if k.lower() != 'content-encoding'}
                )
        except Exception:
            attempts +=1
    raise HTTPException(status_code=503, detail=f"Все экземпляры {service_name} недоступны")


# Прокси-эндпоинты для Matching Service
@app.post("/matching")
async def matching(request: Request, token: str = Header(None), uid: str = Header(None)):
    """
    Проксирует запрос на подбор пары в Matching Service после аутентификации пользователя.

    :param request: Объект запроса FastAPI.
    :param token: Токен пользователя, передается в заголовках.
    :param uid: Уникальный идентификатор пользователя, передается в заголовках.
    :return: Ответ от Matching Service.
    :raises HTTPException: Если аутентификация не удалась.
    """
    if not token or not uid:
        raise HTTPException(status_code=401, detail="Необходима аутентификация. Должны быть предоставлены токен и UID.")

    is_valid = await validate_token(token, uid)
    if not is_valid:
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
    max_attempts = min(MAX_ATTEMPTS, len(services[service_name]['instances']))
    attempts = 0
    # Извлечение пути и параметров запроса
    path = request.url.path
    query = str(request.url.query)
    while attempts < max_attempts:
        instance = get_next_instance(service_name)
        instance_url = instance['url']
        url = urljoin(instance_url, path)
        if query:
            url = f"{url}?{query}"
        headers = dict(request.headers)
        method = request.method
        content = await request.body()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(method, url, headers=headers, content=content, timeout=15)
                return Response(
                    status_code=response.status_code,
                    content=response.content,
                    headers={k: v for k, v in response.headers.items() if k.lower() != 'content-encoding'}
                )
        except Exception:
            attempts += 1
    raise HTTPException(status_code=503, detail=f"Все экземпляры {service_name} недоступны")


# Эндпоинт для микросервисов, чтобы получить другой экземпляр сервиса
@app.get("/get_service_instance")
async def get_service_instance(service_name: str):
    """
    Предоставляет другой экземпляр сервиса микросервису.

    :param service_name: Название сервиса.
    :return: JSON с информацией об экземпляре.
    :raises HTTPException: Если сервис не найден.
    """
    if service_name not in services:
        raise HTTPException(status_code=404, detail=f"Сервис {service_name} не найден")
    instance = get_next_instance(service_name)
    return {'instance': instance}


# Эндпоинт проверки работоспособности API Gateway
@app.get("/ping")
async def ping():
    """
    Эндпоинт для проверки работоспособности.

    :return: Простое сообщение JSON, указывающее, что API Gateway работает.
    """
    return {"message": "API Gateway работает"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
