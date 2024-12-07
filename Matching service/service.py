import asyncpg
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from tasks import match_user

app = FastAPI()


async def get_db_connection():
    return await asyncpg.connect(
        user="postgres",
        password="admin",
        database="auth_service",
        host="localhost",
        port="5435"
    )


class CreateRequest(BaseModel):
    uid: str


class CheckRequest(BaseModel):
    task_id: str

@app.post('/create_match_request')
async def create_match_request(request: CreateRequest):
    task = match_user.delay(request.uid)
    return {'task_id': task.id}


@app.get('/check_match_result')
async def check_match_result(request: CheckRequest):
    from celery.result import AsyncResult
    result = AsyncResult(request.task_id)
    if result.state == 'PENDING':
        return {'status': 'PENDING'}
    elif result.state == 'FAILURE':
        raise HTTPException(status_code=400, detail=str(result.result))
    else:
        return {'status': result.state, 'result': result.result}


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8001)