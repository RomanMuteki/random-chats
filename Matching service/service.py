import uvicorn
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
import httpx
import redis.asyncio as redis
import json
from typing import List, Optional
import logging
from fastapi.responses import HTMLResponse

log_file = "service.log"

CFG_FILE = 'config.json'
if not CFG_FILE:
    raise FileNotFoundError(f"Файл конфигурации {CFG_FILE} не найден.")

with open(CFG_FILE, 'r') as file:
    config = json.load(file)

redis_client = redis.StrictRedis(host=config['redis_host'], port=config['redis_port'], db=0, decode_responses=True)
app = FastAPI(title="Matching Service")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[
                        logging.StreamHandler(),
                        logging.FileHandler(log_file, mode='a')
                    ])
logger = logging.getLogger("Matching Service")

API_GATEWAY_URL = config.get('api_gateway_url', 'http://localhost:8500')
MAX_ATTEMPTS = config.get('max_attempts', 5)


class CreateRequest(BaseModel):
    uid: str


def age_gap(age_frames):
    """
        Возвращает список возрастов в заданном диапазоне.

        :param age_frames: Строка с диапазоном возрастов, например, "18-25".
        :return: Список возрастов в диапазоне.
    """
    logger.info(f"Определение возрастного диапазона для: {age_frames}")
    age_frames = age_frames.split('-')
    minimal_age, maximal_age = int(age_frames[0]), int(age_frames[1])
    ages = [age for age in range(minimal_age, minimal_age + (maximal_age - minimal_age) + 1)]
    logger.info(f"Возрастной диапазон сформирован: {ages}")
    return ages


async def add_user_to_queue(uid: str, queue_key: str) -> bool:
    """
    Добавляет пользователя в очередь Redis.

    :param uid: Идентификатор пользователя.
    :param queue_key: Ключ очереди в Redis.
    :return: True, если пользователь успешно добавлен в очередь.
    """
    logger.info(f"Добавление пользователя {uid} в очередь {queue_key}")
    try:
        await redis_client.lpush(queue_key, uid)
        logger.info(f"Пользователь {uid} успешно добавлен в очередь {queue_key}")
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления пользователя в очередь: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
            logger.info(f"Попытка обращения к {service_name}: {attempts + 1}")
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                if response.status_code == 200:
                    instance = response.json().get('instance')
                    service_url = instance['url']
                    full_url = f"{service_url}{path}"
                    response = await client.request(method, full_url, **kwargs)
                    if response.status_code == 200:
                        logger.info(f"Успешный запрос для {service_name} на {full_url}")
                        return response
                    else:
                        logger.warning(f"Неудачный ответ от сервиса {service_name}: {response.status_code}")
                        attempts += 1
                else:
                    logger.warning(f"Не удалось получить URL сервиса {service_name}: статус код {response.status_code}")
                    attempts += 1
        except Exception as e:
            logger.error(f"Ошибка при обращении к сервису {service_name}: попытка {attempts + 1} - {e}")
            attempts += 1
    logger.error(f"Не удалось связаться с {service_name} после {MAX_ATTEMPTS} попыток")
    raise HTTPException(status_code=503, detail=f"Не удалось связаться с {service_name} после {MAX_ATTEMPTS} попыток")


@app.post('/matching')
async def check_match_result(request: CreateRequest):
    """
    Проверяет наличие подходящего пользователя для матча.

    :param request: Запрос с идентификатором пользователя.
    :return: Статус и сообщение о результате.
    """
    logger.info(f"Проверка подходящего пользователя для матча для uid {request.uid}")
    payload = {'uid': request.uid}
    response = await request_with_retry('GET', 'auth_service', '/matching_info', json=payload)
    if not response:
        logger.error(f"Ошибка при получении информации о пользователе для uid {request.uid}")
        raise HTTPException(status_code=500, detail="Ошибка при получении информации о пользователе")
    userdata1 = response.json()

    for pref_age in age_gap(userdata1['preferred_age']):
        search_key = f"queue:{pref_age}-{userdata1['preferred_sex']}"
        logger.info(f"Поиск пользователя в очереди {search_key}")
        matched_user_id = await redis_client.rpop(search_key)
        if matched_user_id:
            logger.info(f"Найден пользователь для матча uid {matched_user_id}")
            if matched_user_id != request.uid:
                chat_data = {"participants": [request.uid, matched_user_id]}
                response = await request_with_retry('POST', 'message_service', '/chats/', json=chat_data)
                if response.status_code == 400:
                    logger.warning(f"Ошибка создания чата, добавление в очередь обратно для uid {request.uid}")
                    queue_key = f"queue:{userdata1['age']}-{userdata1['sex']}"
                    await add_user_to_queue(request.uid, queue_key)
                    # Возврат второго пользователя в очередь
                    payload = {'uid': matched_user_id}
                    response = await request_with_retry('GET', 'auth_service', '/matching_info', json=payload)
                    if not response:
                        logger.error(f"Ошибка при получении информации о втором пользователе для uid {matched_user_id}")
                        raise HTTPException(status_code=500, detail="Ошибка при получении информации о пользователе")
                    userdata2 = response.json()
                    queue_key = f"queue:{userdata2['age']}-{userdata2['sex']}"
                    await add_user_to_queue(matched_user_id, queue_key)
                else:
                    logger.info(f"Чат успешно создан между {request.uid} и {matched_user_id}")
                    return {'status': 'success', 'message': 'new chat created'}

    queue_key = f"queue:{userdata1['age']}-{userdata1['sex']}"
    if add_user_to_queue(request.uid, queue_key):
        logger.info(f"Пользователь {request.uid} добавлен в очередь {queue_key}")
        return {'status': 'success', 'message': 'user added to queue'}


@app.get("/")
async def health():
    """
    Эндпоинт для проверки состояния сервиса.

    :return: Сообщение о том, что сервис работает.
    """
    logger.info("Проверка состояния сервиса")
    return {"status": "Matching Service is work!"}


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
                    <h1>Matching Service Logs</h1>
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


if __name__ == '__main__':
    logger.info(f"Запуск сервиса Matching Service на {config['server_url']}:{config['server_port']}")
    uvicorn.run(app, host=config['server_url'], port=config['server_port'])
