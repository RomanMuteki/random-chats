import celery
import redis

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


def age_gap(age_frames):
    age_frames = age_frames.split('-')
    minimal_age, maximal_age = int(age_frames[0]), int(age_frames[1])
    ages = [age for age in range(minimal_age, minimal_age + (maximal_age - minimal_age) + 1)]
    return ages


@celery_app.task
def add_user_to_queue(uid, queue_key):
    redis_client.lpush(queue_key, uid)
    return f"user {uid} added to queue"


@celery_app.task
def match_user(uid, userdata1):
    userdata1 = dict(userdata1)
    queue_key = f"queue:{userdata1['age']}-{userdata1['sex']}"

    for age_ in age_gap(userdata1['preferred_age']):
        search_key = f"queue:{age_}-{userdata1['preferred_sex']}"
        print(age_)
        matched_user_id = redis_client.rpop(search_key)
        if matched_user_id:
            print('found')
            if matched_user_id != uid:
                print('foundd')
                return matched_user_id

    task = add_user_to_queue.delay(uid, queue_key)
    return task


if __name__ == "__main__":
    import celery.result
    userdata1 = {
        "age": 23,
        "sex": "female",
        "preferred_age": "21-24",
        "preferred_sex": "female",
    }
    b = match_user("403574114475", userdata1)
    print(b)
    print(celery.result.AsyncResult(b))