import random
import hashlib
import datetime
import jwt
import asyncpg
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel

PRIVATE_JWT_KEY = "Mortira Moraxa"
PASSWORD_ENCRYPTION_KEY = 'pushkatanka'

app = FastAPI()


async def get_db_connection():
    return await asyncpg.connect(
        user="postgres",
        password="admin",
        database="auth_service",
        host="localhost",
        port="5435"
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


def custom_hasher(password):
    salt = PASSWORD_ENCRYPTION_KEY
    return hashlib.sha256((password + salt).encode()).hexdigest()


async def uid_generator(db):
    while True:
        created_uid = ''.join(str(random.randint(0, 9)) for _ in range(12))
        query = "SELECT uid FROM users2 WHERE uid = $1"
        checker = await db.fetchval(query, created_uid)
        if not checker:
            return created_uid


def token_generator(user_data, token_type):
    if token_type == 'refresh':
        lifetime = 96
    else:
        lifetime = 12
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
    query = "SELECT email FROM users2 WHERE email = $1"
    existing_user = await db.fetchval(query, request.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email is already used")

    hashed_password = custom_hasher(request.password)
    uid = await uid_generator(db)
    avatar = random.randint(0, 100)

    insert_query = """
            INSERT INTO users2 (uid, email, password,
             username, sex, age, preffered_age, preffered_sex, avatar_code,
              access_token, refresh_token)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """
    await db.execute(insert_query, uid, request.email, hashed_password, request.username, request.sex,
                     request.age, request.preferred_age, request.preferred_sex, avatar, None, None)

    return {"status": "success", "message": "User registrated successfully", "avatar_code": avatar}


@app.post("/login")
async def login(request: LoginRequest, db=Depends(get_db_connection)):
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
    return {"status": "success", "access_token": access_token, "refresh_token": refresh_token}


@app.post("/token_login")
async def authentification(request: TokenAuthentification, db=Depends(get_db_connection)):
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
async def TokenValidityCheck(request: ServiceCheckToken, db=Depends(get_db_connection)):
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
async def GetInfoByUrl(request: MatchingGetInfo, db=Depends(get_db_connection)):
    try:
        query = "SELECT * FROM users2 WHERE uid = $1"
        user = await db.fetchrow(query, request.uid)
        if user is None:
            raise HTTPException(status_code=400, detail="User not found")
        else:
            return {"sex": user['sex'], "age": user['age'],
                    "preferred_age": user['preffered_age'], "preferred_sex": user['preffered_sex']}
    except Exception as E:
        raise HTTPException(status_code=500, detail=E)

if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8000)
