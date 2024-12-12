from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
import httpx
import redis.asyncio as redis
import json
from typing import List, Optional

CFG_FILE = 'config.json'
if not CFG_FILE:
    raise FileNotFoundError(f"Файл конфигурации {CFG_FILE} не найден.")

with open(CFG_FILE, 'r') as file:
    config = json.load(file)


redis_client = redis.StrictRedis(host=config['redis_host'], port=config['redis_port'], db=0, decode_responses=True)
app = FastAPI()
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
    age_frames = age_frames.split('-')
    minimal_age, maximal_age = int(age_frames[0]), int(age_frames[1])
    ages = [age for age in range(minimal_age, minimal_age + (maximal_age - minimal_age) + 1)]
    return ages


def add_user_to_queue(uid: str, queue_key: str) -> bool:
    """
    Добавляет пользователя в очередь Redis.

    :param uid: Идентификатор пользователя.
    :param queue_key: Ключ очереди в Redis.
    :return: True, если пользователь успешно добавлен в очередь.
    """
    try:
        await redis_client.lpush(queue_key, uid)
        return True
    except Exception as E:
        raise HTTPException(status_code=500, detail=str(E))


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
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                if response.status_code == 200:
                    instance = response.json().get('instance')
                    service_url = instance['url']
                    full_url = f"{service_url}{path}"
                    response = await client.request(method, full_url, **kwargs)
                    if response.status_code == 200:
                        return response
                    else:
                        attempts += 1
                else:
                    attempts += 1
        except Exception as e:
            attempts += 1
    raise HTTPException(status_code=503, detail=f"Не удалось связаться с {service_name} после {MAX_ATTEMPTS} попыток")


@app.post('/matching')
async def check_match_result(request: CreateRequest):
    """
    Проверяет наличие подходящего пользователя для матча.

    :param request: Запрос с идентификатором пользователя.
    :return: Статус и сообщение о результате.
    """
    payload = {'uid': request.uid}
    response = await request_with_retry('GET', 'auth_service', '/matching_info', json=payload)
    if not response:
        raise HTTPException(status_code=500, detail="Ошибка при получении информации о пользователе")
    userdata1 = response.json()

    for pref_age in age_gap(userdata1['preferred_age']):
        search_key = f"queue:{pref_age}-{userdata1['preferred_sex']}"
        matched_user_id = await redis_client.rpop(search_key)
        if matched_user_id:
            if matched_user_id != request.uid:
                """return {'status': 'success',
                        'message': 'user found', 'uid': matched_user_id}"""
                chat_data = {"participants": [request.uid, matched_user_id]}
                response = await request_with_retry('POST', 'message_service', '/chats/', json=chat_data)
                if response.status_code == 400:
                    queue_key = f"queue:{userdata1['age']}-{userdata1['sex']}"
                    add_user_to_queue(request.uid, queue_key)
                    # Возврат второго пользователя в очередь
                    payload = {'uid': matched_user_id}
                    response = await request_with_retry('GET', 'auth_service', '/matching_info', json=payload)
                    if not response:
                        raise HTTPException(status_code=500, detail="Ошибка при получении информации о пользователе")
                    userdata2 = response.json()
                    queue_key = f"queue:{userdata2['age']}-{userdata2['sex']}"
                    add_user_to_queue(matched_user_id, queue_key)
                else:
                    return {'status': 'success', 'message': 'new chat created'}

    queue_key = f"queue:{userdata1['age']}-{userdata1['sex']}"
    if add_user_to_queue(request.uid, queue_key):
        return {'status': 'success', 'message': 'user added to queue'}


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host=config['server_url'], port=config['server_port'])