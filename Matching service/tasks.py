import celery
import redis
import requests

redis_client = redis.StrictRedis(host='localhost', port=6379, decode_responses=True)

celery_app = celery.Celery(
    'tasks',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/1'
)

celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='UTC',
    enable_utc=True
)

db_settings = {
    'user': "postgres",
    'password': "admin",
    'dbname': "auth_service",
    'host': "localhost",
    'port': "5435"
}

url = "http://localhost:8000"


def age_gap(age_frames):
    age_frames = age_frames.split('-')
    minimal_age, maximal_age = int(age_frames[0]), int(age_frames[1])
    ages = [age for age in (minimal_age, minimal_age + (maximal_age - minimal_age))]
    return ages


@celery_app.task
def add_user_to_queue(uid, queue_key):
    redis_client.lpush(queue_key, uid)
    return f"user {uid} added to queue"


@celery_app.task
def match_user(uid):
    payload = {'uid': uid}
    userdata = requests.post(url + '/matching_info', json=payload)
    userdata = userdata.json()
    queue_key = f"queue: {userdata['age'], userdata['sex']}"

    for age_ in age_gap(userdata['preferred_age']):
        search_key = f"queue: {age_, userdata['preferred_sex']}"

        matched_user_id = redis_client.rpop(search_key)
        if matched_user_id:
            if matched_user_id != uid:
                return matched_user_id

    return add_user_to_queue(uid, queue_key)