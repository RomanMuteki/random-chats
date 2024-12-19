import uvicorn
import random
import hashlib
import datetime
import jwt
import asyncpg
import json
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from fastapi.responses import HTMLResponse
import logging

log_file = "service.log"

CFG_FILE = 'config.json'
if not CFG_FILE:
    raise FileNotFoundError(f"Файл конфигурации {CFG_FILE} не найден.")

with open(CFG_FILE, 'r') as file:
    config = json.load(file)

PRIVATE_JWT_KEY = config['jwt_key']
PASSWORD_ENCRYPTION_KEY = config['password_key']
API_GATEWAY_URL = config.get('api_gateway_url', 'http://localhost:8300')
MAX_ATTEMPTS = config.get('max_attempts', 5)

app = FastAPI(title="Auth Service")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    handlers=[
                        logging.StreamHandler(),
                        logging.FileHandler(log_file, mode='a')
                    ])
logger = logging.getLogger("Auth Service")


async def get_db_connection():
    try:
        logger.info(f"Подключение к базе данных с параметрами пользователя {config['user']}")
        return await asyncpg.connect(
            user=config['user'],
            password=config['password'],
            database=config['database'],
            host=config['db_host'],
            port=config['db_port']
        )
    except Exception as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
        raise


class RegistrationRequest(BaseModel):
    email: str
    username: str
    password: str
    sex: str
    age: int
    preferred_age: str
    preferred_sex: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenAuthentification(BaseModel):
    token: str


class ServiceCheckToken(BaseModel):
    token: str
    uid: str


class MatchingGetInfo(BaseModel):
    uid: str


class InvalidTokenValue(Exception):
    pass


def custom_hasher(password: str) -> str:
    """
    Хеширует пароль с использованием SHA-256 и соли.

    :param password: Пароль для хеширования.
    :return: Хешированный пароль.
    """
    logger.info("Хеширование пароля")
    salt = PASSWORD_ENCRYPTION_KEY
    return hashlib.sha256((password + salt).encode()).hexdigest()


async def uid_generator(db) -> str:
    """
    Генерирует уникальный идентификатор пользователя.

    :param db: Подключение к базе данных.
    :return: Уникальный идентификатор пользователя.
    """
    try:
        while True:
            created_uid = ''.join(str(random.randint(0, 9)) for _ in range(12))
            logger.info(f"Сгенерирован UID: {created_uid}")
            query = "SELECT uid FROM users2 WHERE uid = $1"
            checker = await db.fetchval(query, created_uid)
            if not checker:
                logger.info(f"Уникальный UID подтверждён: {created_uid}")
                return created_uid
    except Exception as e:
        logger.error(f"Ошибка генерации UID: {e}")
        raise


def token_generator(user_data: str, token_type: str) -> str:
    """
    Генерирует JWT токен.

    :param user_data: Данные пользователя для включения в токен.
    :param token_type: Тип токена ('access' или 'refresh').
    :return: Сгенерированный JWT токен.
    """
    try:
        lifetime = 96 if token_type == 'refresh' else 12
        logger.info(f"Генерация {token_type} токена для пользователя {user_data}")
        payload = {
            "iss": 'Random_chats auth service',
            "token_type": token_type,
            "sub": user_data,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=lifetime)
        }
        token = jwt.encode(payload, PRIVATE_JWT_KEY, algorithm="HS256")
        return token
    except Exception as e:
        logger.error(f"Ошибка генерации токена: {e}")
        raise


@app.post("/register")
async def registration(request: RegistrationRequest, db=Depends(get_db_connection)):
    """
    Регистрирует нового пользователя.

    :param request: Данные для регистрации.
    :param db: Подключение к базе данных.
    :return: Статус регистрации.
    """
    try:
        logger.info(f"Регистрация нового пользователя с email: {request.email}")
        query = "SELECT email FROM users2 WHERE email = $1"
        existing_user = await db.fetchval(query, request.email)
        if existing_user:
            logger.error(f"Попытка регистрации с существующим email: {request.email}")
            raise HTTPException(status_code=400, detail="Email is already used")

        hashed_password = custom_hasher(request.password)
        uid = await uid_generator(db)
        avatar = random.randint(0, 100)

        insert_query = """
            INSERT INTO users2 (uid, email, password, username, sex, age, preffered_age, preffered_sex, avatar_code, access_token, refresh_token)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """
        await db.execute(insert_query, uid, request.email, hashed_password, request.username1, request.sex,
                         request.age, request.preferred_age, request.preferred_sex, avatar, None, None)

        logger.info(f"Пользователь зарегистрирован: {request.email}")
        return {"status": "success", "message": "User registered successfully", "avatar_code": avatar}
    except Exception as e:
        logger.error(f"Ошибка регистрации пользователя: {e}")
        raise


@app.post("/login")
async def login(request: LoginRequest, db=Depends(get_db_connection)):
    """
    Авторизует пользователя и выдает токены.

    :param request: Данные для авторизации.
    :param db: Подключение к базе данных.
    :return: Токены доступа и обновления.
    """
    try:
        logger.info(f"Авторизация пользователя с email: {request.email}")
        query = "SELECT * FROM users2 WHERE email = $1"
        user = await db.fetchrow(query, request.email)
        if not user:
            logger.error(f"Пользователь не найден: {request.email}")
            raise HTTPException(status_code=400, detail="User not found")

        stored_password = user['password']
        supposed_password = custom_hasher(request.password)
        if stored_password != supposed_password:
            logger.error(f"Неправильный пароль для пользователя: {request.email}")
            raise HTTPException(status_code=400, detail="Incorrect password")

        uid = user['uid']
        access_token = token_generator(uid, 'access')
        refresh_token = token_generator(uid, 'refresh')

        update_query = """
            UPDATE users2 SET access_token = $1, refresh_token = $2 WHERE uid = $3
        """
        await db.execute(update_query, access_token, refresh_token, uid)
        logger.info(f"Успешная авторизация пользователя: {request.email}")
        return {"status": "success", "access_token": access_token, "refresh_token": refresh_token, "uid": uid}
    except Exception as e:
        logger.error(f"Ошибка авторизации пользователя: {e}")
        raise


@app.post("/token_login")
async def authentification(request: TokenAuthentification, db=Depends(get_db_connection)):
    """
    Аутентифицирует пользователя по токену.

    :param request: Токен для аутентификации.
    :param db: Подключение к базе данных.
    :return: Статус аутентификации.
    """
    logger.info("Аутентификация пользователя с токеном")
    try:
        dec_token = jwt.decode(request.token, PRIVATE_JWT_KEY,
                               algorithms='HS256', options={'verify_iss': True}, issuer='Random_chats auth service')

        query = "SELECT * FROM users2 WHERE uid = $1"
        user = await db.fetchrow(query, dec_token['sub'])
        if user is None:
            logger.error("Неверный токен, требуется повторная авторизация")
            raise HTTPException(status_code=400, detail="Invalid token. Relogin is required")

        if request.token != user['access_token'] and request.token != user['refresh_token']:
            logger.error(f"Неизвестный токен для пользователя с uid: {dec_token['sub']}")
            raise InvalidTokenValue('Token is not found')

        if dec_token['token_type'] == 'access':
            logger.info(f"Access токен действителен для пользователя с uid: {dec_token['sub']}")
            return {"status": "success", "message": "Access token is up to date"}

        if dec_token['token_type'] == 'refresh':
            uid = user['uid']
            new_access_token = token_generator(uid, 'access')
            query = "UPDATE users2 SET access_token = $1 WHERE uid = $2"
            await db.execute(query, new_access_token, uid)
            logger.info(f"Обновление access токена для пользователя с uid: {uid}")
            return {"status": "success", "message": "New token is sent", "access token": new_access_token}
    except jwt.ExpiredSignatureError:
        logger.error("Срок действия токена истек, требуется повторная авторизация")
        raise HTTPException(status_code=400, detail="Token is expired. Relogin is required")
    except jwt.InvalidIssuerError:
        logger.error("Неверный издатель токена, требуется повторная авторизация")
        raise HTTPException(status_code=400, detail="Invalid issuer. Relogin is required")
    except InvalidTokenValue:
        logger.error("Неверный токен, требуется повторная авторизация")
        raise HTTPException(status_code=400, detail="Invalid token. Relogin is required")


@app.post("/token_check")
async def token_validity_check(request: ServiceCheckToken, db=Depends(get_db_connection)):
    """
    Проверяет валидность токена.

    :param request: Токен и UID для проверки.
    :param db: Подключение к базе данных.
    :return: Статус валидности токена.
    """
    logger.info(f"Проверка валидности токена для пользователя с uid: {request.uid}")
    try:
        query = "SELECT * FROM users2 WHERE uid = $1"
        user = await db.fetchrow(query, request.uid)
        if user is None:
            logger.error(f"Пользователь не найден по uid: {request.uid}")
            raise HTTPException(status_code=400, detail="User not found")

        if request.token != user['access_token'] and request.token != user['refresh_token']:
            logger.error(f"Недействительный токен для пользователя с uid: {request.uid}")
            raise InvalidTokenValue('Invalid token')

        logger.info(f"Токен действителен для пользователя с uid: {request.uid}")
        return {"status": "success", "message": "Token is up to date, user submitted"}
    except jwt.ExpiredSignatureError:
        logger.error("Срок действия токена истек")
        raise HTTPException(status_code=400, detail="Token is expired")
    except jwt.InvalidIssuerError:
        logger.error("Неверный издатель токена")
        raise HTTPException(status_code=400, detail="Invalid issuer")
    except InvalidTokenValue:
        logger.error("Неверный токен")
        raise HTTPException(status_code=400, detail="Invalid token")


@app.get("/matching_info")
async def get_info_by_url(request: MatchingGetInfo, db=Depends(get_db_connection)):
    """
    Получает информацию о пользователе для сервиса Matching.

    :param request: UID пользователя.
    :param db: Подключение к базе данных.
    :return: Информация о пользователе.
    """
    logger.info(f"Получение информации о пользователе для uid: {request.uid}")
    try:
        query = "SELECT * FROM users2 WHERE uid = $1"
        user = await db.fetchrow(query, request.uid)
        if user is None:
            logger.error(f"Пользователь не найден по uid: {request.uid}")
            raise HTTPException(status_code=400, detail="User not found")
        else:
            logger.info(f"Информация о пользователе успешно получена для uid: {request.uid}")
            return {"sex": user['sex'], "age": user['age'],
                    "preferred_age": user['preffered_age'], "preferred_sex": user['preffered_sex']}
    except Exception as e:
        logger.error(f"Ошибка при получении информации о пользователе: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/get_info_by_id')
async def get_name(request: MatchingGetInfo, db=Depends(get_db_connection)):
    """
    Получает имя пользователя по его UID.

    :param request: UID пользователя.
    :param db: Подключение к базе данных.
    :return: Имя пользователя.
    """
    logger.info(f"Получение имени пользователя для uid: {request.uid}")

    try:
        query = "SELECT * FROM users2 WHERE uid = $1"
        user = await db.fetchrow(query, request.uid)
        if user is None:
            logger.error(f"Пользователь не найден по uid: {request.uid}")
            raise HTTPException(status_code=400, detail="User not found")
        else:
            logger.info(f"Имя пользователя успешно получено для uid: {request.uid}")
            return {"username": user['username']}
    except Exception as e:
        logger.error(f"Ошибка при получении имени пользователя: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def health():
    """
    Эндпоинт для проверки состояния сервиса.

    :return: Сообщение о том, что сервис работает.
    """
    logger.info("Проверка состояния сервиса")
    return {"status": "Auth Service is work!"}


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
                    <h1>Auth Service Logs</h1>
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
    logger.info("Запуск сервиса")
    uvicorn.run(app, host=config['server_host'], port=config['server_port'])
