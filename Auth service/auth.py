import random
import hashlib
import datetime
import jwt
import asyncpg
import json
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

CFG_FILE = 'config.json'
if not CFG_FILE:
    raise FileNotFoundError(f"Файл конфигурации {CFG_FILE} не найден.")

with open(CFG_FILE, 'r') as file:
    config = json.load(file)

PRIVATE_JWT_KEY = config['jwt_key']
PASSWORD_ENCRYPTION_KEY = config['password_key']
API_GATEWAY_URL = config.get('api_gateway_url', 'http://localhost:8300')
MAX_ATTEMPTS = config.get('max_attempts', 5)

app = FastAPI()

async def get_db_connection():
    return await asyncpg.connect(
        user=config['user'],
        password=config['password'],
        database=config['database'],
        host=config['db_host'],
        port=config['db_port']
    )

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
    salt = PASSWORD_ENCRYPTION_KEY
    return hashlib.sha256((password + salt).encode()).hexdigest()

async def uid_generator(db) -> str:
    """
    Генерирует уникальный идентификатор пользователя.

    :param db: Подключение к базе данных.
    :return: Уникальный идентификатор пользователя.
    """
    while True:
        created_uid = ''.join(str(random.randint(0, 9)) for _ in range(12))
        query = "SELECT uid FROM users2 WHERE uid = $1"
        checker = await db.fetchval(query, created_uid)
        if not checker:
            return created_uid

def token_generator(user_data: str, token_type: str) -> str:
    """
    Генерирует JWT токен.

    :param user_data: Данные пользователя для включения в токен.
    :param token_type: Тип токена ('access' или 'refresh').
    :return: Сгенерированный JWT токен.
    """
    lifetime = 96 if token_type == 'refresh' else 12
    payload = {
        "iss": 'Random_chats auth service',
        "token_type": token_type,
        "sub": user_data,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=lifetime)
    }
    token = jwt.encode(payload, PRIVATE_JWT_KEY, algorithm="HS256")
    return token

@app.post("/register")
async def registration(request: RegistrationRequest, db=Depends(get_db_connection)):
    """
    Регистрирует нового пользователя.

    :param request: Данные для регистрации.
    :param db: Подключение к базе данных.
    :return: Статус регистрации.
    """
    query = "SELECT email FROM users2 WHERE email = $1"
    existing_user = await db.fetchval(query, request.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email is already used")

    hashed_password = custom_hasher(request.password)
    uid = await uid_generator(db)
    avatar = random.randint(0, 100)

    insert_query = """
        INSERT INTO users2 (uid, email, password, username, sex, age, preffered_age, preffered_sex, avatar_code, access_token, refresh_token)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    """
    await db.execute(insert_query, uid, request.email, hashed_password, request.username, request.sex,
                     request.age, request.preferred_age, request.preferred_sex, avatar, None, None)

    return {"status": "success", "message": "User registered successfully", "avatar_code": avatar}

@app.post("/login")
async def login(request: LoginRequest, db=Depends(get_db_connection)):
    """
    Авторизует пользователя и выдает токены.

    :param request: Данные для авторизации.
    :param db: Подключение к базе данных.
    :return: Токены доступа и обновления.
    """
    query = "SELECT * FROM users2 WHERE email = $1"
    user = await db.fetchrow(query, request.email)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    stored_password = user['password']
    supposed_password = custom_hasher(request.password)
    if stored_password != supposed_password:
        raise HTTPException(status_code=400, detail="Incorrect password")

    uid = user['uid']
    access_token = token_generator(uid, 'access')
    refresh_token = token_generator(uid, 'refresh')

    update_query = """
        UPDATE users2 SET access_token = $1, refresh_token = $2 WHERE uid = $3
    """
    await db.execute(update_query, access_token, refresh_token, uid)
    return {"status": "success", "access_token": access_token, "refresh_token": refresh_token, "uid": uid}

@app.post("/token_login")
async def authentification(request: TokenAuthentification, db=Depends(get_db_connection)):
    """
    Аутентифицирует пользователя по токену.

    :param request: Токен для аутентификации.
    :param db: Подключение к базе данных.
    :return: Статус аутентификации.
    """
    try:
        dec_token = jwt.decode(request.token, PRIVATE_JWT_KEY,
                               algorithms='HS256', options={'verify_iss': True}, issuer='Random_chats auth service')

        query = "SELECT * FROM users2 WHERE uid = $1"
        user = await db.fetchrow(query, dec_token['sub'])
        if user is None:
            raise HTTPException(status_code=400, detail="Invalid token. Relogin is required")

        if request.token != user['access_token'] and request.token != user['refresh_token']:
            raise InvalidTokenValue('Token is not found')

        if dec_token['token_type'] == 'access':
            return {"status": "success", "message": "Access token is up to date"}

        if dec_token['token_type'] == 'refresh':
            uid = user['uid']
            new_access_token = token_generator(uid, 'access')
            query = "UPDATE users2 SET access_token = $1 WHERE uid = $2"
            await db.execute(query, new_access_token, uid)
            return {"status": "success", "message": "New token is sent", "access token": new_access_token}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Token is expired. Relogin is required")
    except jwt.InvalidIssuerError:
        raise HTTPException(status_code=400, detail="Invalid issuer. Relogin is required")
    except InvalidTokenValue:
        raise HTTPException(status_code=400, detail="Invalid token. Relogin is required")

@app.get("/token_check")
async def token_validity_check(request: ServiceCheckToken, db=Depends(get_db_connection)):
    """
    Проверяет валидность токена.

    :param request: Токен и UID для проверки.
    :param db: Подключение к базе данных.
    :return: Статус валидности токена.
    """
    try:
        query = "SELECT * FROM users2 WHERE uid = $1"
        user = await db.fetchrow(query, request.uid)
        if user is None:
            raise HTTPException(status_code=400, detail="User not found")

        if request.token != user['access_token'] and request.token != user['refresh_token']:
            raise InvalidTokenValue('Invalid token')

        return {"status": "success", "message": "Token is up to date, user submitted"}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Token is expired")
    except jwt.InvalidIssuerError:
        raise HTTPException(status_code=400, detail="Invalid issuer")
    except InvalidTokenValue:
        raise HTTPException(status_code=400, detail="Invalid token")

@app.get("/matching_info")
async def get_info_by_url(request: MatchingGetInfo, db=Depends(get_db_connection)):
    """
    Получает информацию о пользователе для сервиса Matching.

    :param request: UID пользователя.
    :param db: Подключение к базе данных.
    :return: Информация о пользователе.
    """
    try:
        query = "SELECT * FROM users2 WHERE uid = $1"
        user = await db.fetchrow(query, request.uid)
        if user is None:
            raise HTTPException(status_code=400, detail="User not found")
        else:
            return {"sex": user['sex'], "age": user['age'],
                    "preferred_age": user['preffered_age'], "preferred_sex": user['preffered_sex']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/get_info_by_id')
async def get_name(request: MatchingGetInfo, db=Depends(get_db_connection)):
    """
    Получает имя пользователя по его UID.

    :param request: UID пользователя.
    :param db: Подключение к базе данных.
    :return: Имя пользователя.
    """
    try:
        query = "SELECT * FROM users2 WHERE uid = $1"
        user = await db.fetchrow(query, request.uid)
        if user is None:
            raise HTTPException(status_code=400, detail="User not found")
        else:
            return {"username": user['username']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host=config['server_host'], port=config['server_port'])
