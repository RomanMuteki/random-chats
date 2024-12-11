from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
import requests, redis

redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)
app = FastAPI()
url = "http://127.0.0.1:8000"


class CreateRequest(BaseModel):
    uid: str


def age_gap(age_frames):
    age_frames = age_frames.split('-')
    minimal_age, maximal_age = int(age_frames[0]), int(age_frames[1])
    ages = [age for age in range(minimal_age, minimal_age + (maximal_age - minimal_age) + 1)]
    return ages


def add_user_to_queue(uid, queue_kye):
    try:
        redis_client.lpush(queue_kye, uid)
        return True
    except Exception as E:
        raise HTTPException(status_code=500, detail=E)



@app.post('/matching')
async def check_match_result(request: CreateRequest):
    payload = {'uid': request.uid}
    userdata = requests.get(url + '/matching_info', json=payload)
    userdata1 = userdata.json()

    for pref_age in age_gap(userdata1['preferred_age']):
        search_key = f"queue:{pref_age}-{userdata1['preferred_sex']}"
        matched_user_id = redis_client.rpop(search_key)
        if matched_user_id:
            if matched_user_id != request.uid:
                return {'status': 'success',
                        'message': 'user found', 'uid': matched_user_id}

    queue_key = f"queue:{userdata1['age']}-{userdata1['sex']}"
    if add_user_to_queue(request.uid, queue_key):
        return {'status': 'success', 'message': 'user added to queue'}


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8001)