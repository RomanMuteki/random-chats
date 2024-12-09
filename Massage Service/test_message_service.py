import pytest
from httpx import AsyncClient
from main import app
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import pytest_asyncio

MONGODB_URL = "mongodb://localhost:27017"
DATABASE_NAME = "random_chats_db_test"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    # Настройка тестовой базы данных
    client = AsyncIOMotorClient(MONGODB_URL)
    test_db = client[DATABASE_NAME]
    # Очищаем коллекции
    await test_db["messages"].delete_many({})
    await test_db["chats"].delete_many({})
    # Присваиваем тестовую БД приложению
    app.db = test_db
    app.client = client
    yield
    # Очистка после тестов
    await client.drop_database(DATABASE_NAME)
    client.close()


@pytest_asyncio.fixture(scope="function")
async def async_client():
    async with AsyncClient(base_url="http://localhost:8200") as ac:
        yield ac


class TestMessageService:
    chat_id = None
    message_id = None

    @pytest.mark.asyncio
    async def test_create_chat(self, async_client):
        # Тест создания чата
        payload = {
            "participants": ["user1", "user2"]
        }
        response = await async_client.post("/chats/", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "_id" in data
        assert "participants" in data
        assert data["participants"] == ["user1", "user2"]
        TestMessageService.chat_id = data["_id"]

    @pytest.mark.asyncio
    async def test_create_message(self, async_client):
        # Тест создания сообщения
        payload = {
            "chat_id": TestMessageService.chat_id,
            "sender_id": "user1",
            "content": "Hello user2!"
        }
        response = await async_client.post("/messages/", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["chat_id"] == TestMessageService.chat_id
        assert data["sender_id"] == "user1"
        assert data["content"] == "Hello user2!"
        TestMessageService.message_id = data["_id"]

    @pytest.mark.asyncio
    async def test_get_chat_messages(self, async_client):
        # Тест получения сообщений из чата
        response = await async_client.get(f"/messages/{TestMessageService.chat_id}")
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) == 1
        message = messages[0]
        assert message["_id"] == TestMessageService.message_id
        assert message["content"] == "Hello user2!"

    @pytest.mark.asyncio
    async def test_update_message_status(self, async_client):
        # Тест обновления статуса сообщения
        payload = {
            "receiver_id": "user2",
            "status": "delivered"
        }
        response = await async_client.put(f"/messages/{TestMessageService.message_id}/status", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Статус сообщения обновлен"

        # Проверяем, что статус обновлен
        response = await async_client.get(f"/messages/{TestMessageService.chat_id}")
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) == 1
        message = messages[0]
        assert "status" in message
        assert "user2" in message["status"]
        assert message["status"]["user2"]["status"] == "delivered"

    @pytest.mark.asyncio
    async def test_get_new_messages_for_user(self, async_client):
        # Тест получения новых сообщений для user2
        response = await async_client.get(f"/messages/{TestMessageService.chat_id}/new/user2")
        assert response.status_code == 200
        messages = response.json()
        # Поскольку статус обновлен на 'delivered', новых сообщений не должно быть
        assert len(messages) == 0

        # Отправляем еще одно сообщение
        payload = {
            "chat_id": TestMessageService.chat_id,
            "sender_id": "user1",
            "content": "How are you?"
        }
        response = await async_client.post("/messages/", json=payload)
        assert response.status_code == 200
        data = response.json()
        new_message_id = data["_id"]
        # Получаем новые сообщения для user2
        response = await async_client.get(f"/messages/{TestMessageService.chat_id}/new/user2")
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) == 1
        message = messages[0]
        assert message["_id"] == new_message_id
        assert message["content"] == "How are you?"

    @pytest.mark.asyncio
    async def test_get_user_chats(self, async_client):
        # Тест получения чатов пользователя
        response = await async_client.get(f"/chats/user1")
        assert response.status_code == 200
        chats = response.json()
        assert len(chats) >= 1  # Может быть больше, если тесты запускались несколько раз
        chat_ids = [chat["_id"] for chat in chats]
        assert TestMessageService.chat_id in chat_ids

    @pytest.mark.asyncio
    async def test_update_chat_status(self, async_client):
        # Тест обновления статуса чата
        payload = {
            "receiver_id": "user1",
            "status": "delivered"
        }
        response = await async_client.put(f"/chats/{TestMessageService.chat_id}/status", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Статус чата обновлен"

        # Получаем новые чаты для user1
        response = await async_client.get(f"/chats/user1/new")
        assert response.status_code == 200
        new_chats = response.json()
        # Поскольку статус обновлен на 'delivered', чата не должно быть в новых
        chat_ids = [chat["_id"] for chat in new_chats]
        assert TestMessageService.chat_id not in chat_ids

    @pytest.mark.asyncio
    async def test_get_new_chats(self, async_client):
        # Создаем новый чат и проверяем
        payload = {
            "participants": ["user1", "user3"]
        }
        response = await async_client.post("/chats/", json=payload)
        assert response.status_code == 200
        data = response.json()
        new_chat_id = data["_id"]

        # Получаем новые чаты для user1
        response = await async_client.get(f"/chats/user1/new")
        assert response.status_code == 200
        new_chats = response.json()
        chat_ids = [chat["_id"] for chat in new_chats]
        assert new_chat_id in chat_ids

    @pytest.mark.asyncio
    async def test_error_handling_create_message_invalid_chat(self, async_client):
        # Тест создания сообщения с неверным chat_id
        payload = {
            "chat_id": "invalid_chat_id",
            "sender_id": "user1",
            "content": "Hello!"
        }
        response = await async_client.post("/messages/", json=payload)
        assert response.status_code == 422  # Неверный ввод

    @pytest.mark.asyncio
    async def test_error_handling_update_message_status_invalid_message(self, async_client):
        # Тест обновления статуса несуществующего сообщения
        payload = {
            "receiver_id": "user2",
            "status": "delivered"
        }
        invalid_message_id = str(ObjectId())
        response = await async_client.put(f"/messages/{invalid_message_id}/status", json=payload)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_new_messages_with_last_message_id(self, async_client):
        # Тест получения новых сообщений после указанного сообщения
        # Отправляем новое сообщение
        payload = {
            "chat_id": TestMessageService.chat_id,
            "sender_id": "user1",
            "content": "Third message"
        }
        response = await async_client.post("/messages/", json=payload)
        assert response.status_code == 200
        data = response.json()
        last_message_id = data["_id"]

        # Отправляем еще одно сообщение
        payload = {
            "chat_id": TestMessageService.chat_id,
            "sender_id": "user1",
            "content": "Fourth message"
        }
        response = await async_client.post("/messages/", json=payload)
        assert response.status_code == 200

        # Получаем новые сообщения после last_message_id
        response = await async_client.get(f"/messages/{TestMessageService.chat_id}/new?last_message_id={last_message_id}")
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) == 1
        assert messages[0]["content"] == "Fourth message"

    @pytest.mark.asyncio
    async def test_get_new_messages_invalid_last_message_id(self, async_client):
        # Тест получения новых сообщений с неверным last_message_id
        invalid_message_id = "invalid_id"
        response = await async_client.get(f"/messages/{TestMessageService.chat_id}/new?last_message_id={invalid_message_id}")
        assert response.status_code == 422  # Неверный ввод

    @pytest.mark.asyncio
    async def test_get_messages_invalid_chat_id(self, async_client):
        # Тест получения сообщений с неверным chat_id
        response = await async_client.get(f"/messages/invalid_chat_id")
        assert response.status_code == 422  # Неверный ввод

    @pytest.mark.asyncio
    async def test_update_chat_status_invalid_chat(self, async_client):
        # Тест обновления статуса несуществующего чата
        payload = {
            "receiver_id": "user1",
            "status": "delivered"
        }
        invalid_chat_id = str(ObjectId())
        response = await async_client.put(f"/chats/{invalid_chat_id}/status", json=payload)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_chat_missing_participants(self, async_client):
        # Тест создания чата без участников
        payload = {}
        response = await async_client.post("/chats/", json=payload)
        assert response.status_code == 422
