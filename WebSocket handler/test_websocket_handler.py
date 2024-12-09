import pytest
import asyncio
from unittest.mock import AsyncMock, patch, ANY
from fastapi import WebSocket
from httpx import AsyncClient
import pytest_asyncio
import websockets
from websockets import connect
from websockets.exceptions import ConnectionClosedOK
import json

# Configuration
WEBSOCKET_MANAGER_URL = "http://localhost:8000"
MESSAGE_SERVICE_URL = "http://localhost:8200"
HANDLER_URL = "http://localhost:8001"

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_services():
    async with AsyncClient() as client:
        try:
            response = await client.get(WEBSOCKET_MANAGER_URL)
            assert response.status_code == 200
        except Exception as e:
            pytest.fail(f"Cannot reach WebSocket Manager at {WEBSOCKET_MANAGER_URL}: {e}")

        try:
            response = await client.get(f"{MESSAGE_SERVICE_URL}/")
            assert response.status_code == 200
        except Exception as e:
            pytest.fail(f"Cannot reach Message Service at {MESSAGE_SERVICE_URL}: {e}")

@pytest_asyncio.fixture(scope="function")
async def async_client():
    async with AsyncClient(base_url=HANDLER_URL) as client:
        yield client

@pytest.fixture(scope="function")
def anyio_backend():
    return 'asyncio'

import main

class TestWebSocketHandlerUnit:
    @pytest.mark.asyncio
    async def test_register_user_success(self):
        user_id = 'user123'
        with patch('main.http_client.post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200
            await main.register_user(user_id)
            mock_post.assert_awaited_once()
            mock_post.assert_awaited_with(f"{WEBSOCKET_MANAGER_URL}/connect", json={
                "user_id": user_id,
                "websocket_handler_id": main.HANDLER_ID
            })

    @pytest.mark.asyncio
    async def test_register_user_failure(self):
        user_id = 'user123'
        with patch('main.http_client.post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 500
            with pytest.raises(Exception):
                await main.register_user(user_id)
            mock_post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_incoming_message_online_recipient(self):
        sender_id = 'user1'
        message_data = {
            'recipient_id': 'user2',
            'content': 'Hello!',
            'chat_id': 'chat123'
        }
        with patch('main.save_message', new_callable=AsyncMock) as mock_save_message, \
             patch('main.deliver_message', new_callable=AsyncMock) as mock_deliver_message:

            mock_save_message.return_value = 'message123'
            main.connected_users = {'user2': AsyncMock(spec=WebSocket)}

            await main.handle_incoming_message(sender_id, message_data)

            mock_save_message.assert_awaited_once()
            mock_deliver_message.assert_awaited_once_with(
                main.connected_users['user2'],
                {
                    'type': 'message',
                    'chat_id': 'chat123',
                    'sender_id': sender_id,
                    'recipient_id': 'user2',
                    'content': 'Hello!',
                    'message_id': 'message123',
                    'timestamp': ANY,
                }
            )

    @pytest.mark.asyncio
    async def test_handle_incoming_message_online_recipient(self):
        sender_id = 'user1'
        message_data = {
            'recipient_id': 'user2',
            'content': 'Hello!',
            'chat_id': 'chat123'
        }
        mock_websocket = AsyncMock(spec=WebSocket)

        with patch('main.save_message', new_callable=AsyncMock) as mock_save_message, \
             patch('main.deliver_message', new_callable=AsyncMock) as mock_deliver_message, \
             patch.dict('main.connected_users', {'user2': mock_websocket}, clear=True):

            mock_save_message.return_value = 'message123'

            await main.handle_incoming_message(sender_id, message_data)

            mock_save_message.assert_awaited_once()
            mock_deliver_message.assert_awaited_once_with(
                mock_websocket,
                {
                    'type': 'message',
                    'chat_id': 'chat123',
                    'sender_id': sender_id,
                    'recipient_id': 'user2',
                    'content': 'Hello!',
                    'message_id': 'message123',
                    'timestamp': ANY,
                }
            )


class TestWebSocketHandlerIntegration:
    @pytest.mark.asyncio
    async def test_websocket_connection_and_message_flow(self):
        user1_id = 'user1'
        user2_id = 'user2'

        ws_user2 = await connect(f"{HANDLER_URL.replace('http', 'ws')}/ws/{user2_id}")
        ws_user1 = await connect(f"{HANDLER_URL.replace('http', 'ws')}/ws/{user1_id}")

        message = {
            'recipient_id': user2_id,
            'content': 'Hello User2!',
            'chat_id': None
        }
        await ws_user1.send(json.dumps(message))

        received_message = None
        for _ in range(5):
            response = await ws_user2.recv()
            data = json.loads(response)
            if data.get('type') == 'message':
                received_message = data
                break
        assert received_message is not None, "Did not receive 'message' type"
        assert received_message['content'] == 'Hello User2!'
        assert received_message['sender_id'] == user1_id

        await ws_user1.close()
        await ws_user2.close()

    @pytest.mark.asyncio
    async def test_websocket_offline_recipient(self):
        user1_id = 'user1'
        recipient_id = 'user3'

        ws_user1 = await connect(f"{HANDLER_URL.replace('http', 'ws')}/ws/{user1_id}")

        message = {
            'recipient_id': recipient_id,
            'content': 'Hello Offline User!',
            'chat_id': None
        }
        await ws_user1.send(json.dumps(message))

        async with AsyncClient() as client:
            response = await client.get(f"{MESSAGE_SERVICE_URL}/chats/{user1_id}")
            assert response.status_code == 200
            chats = response.json()
            chat = next((chat for chat in chats if recipient_id in chat['participants']), None)
            assert chat is not None
            chat_id = chat['_id']

            response = await client.get(f"{MESSAGE_SERVICE_URL}/messages/{chat_id}")
            assert response.status_code == 200
            messages = response.json()
            assert any(msg['content'] == 'Hello Offline User!' for msg in messages)

        await ws_user1.close()

    @pytest.mark.asyncio
    async def test_websocket_reconnect(self):
        user1_id = 'user1'
        user2_id = 'user2'

        ws_user1 = await connect(f"{HANDLER_URL.replace('http', 'ws')}/ws/{user1_id}")
        message = {
            'recipient_id': user2_id,
            'content': 'Hello User2!',
            'chat_id': None
        }
        await ws_user1.send(json.dumps(message))
        await ws_user1.close()

        # Добавим небольшую задержку перед подключением user2
        await asyncio.sleep(0.1)

        ws_user2 = await connect(f"{HANDLER_URL.replace('http', 'ws')}/ws/{user2_id}")

        # Добавим задержку после подключения
        await asyncio.sleep(0.1)

        received_message = None
        for _ in range(5):
            try:
                response = await asyncio.wait_for(ws_user2.recv(), timeout=1)
                data = json.loads(response)
                if data.get('type') == 'message':
                    received_message = data
                    break
            except asyncio.TimeoutError:
                break

        assert received_message is not None, "Did not receive 'message' type"
        assert received_message['content'] == 'Hello User2!'
        assert received_message['sender_id'] == user1_id

        await ws_user2.close()

    @pytest.mark.asyncio
    async def test_chat_creation(self):
        user1_id = 'user1'
        user2_id = 'user_new'

        ws_user1 = await connect(f"{HANDLER_URL.replace('http', 'ws')}/ws/{user1_id}")
        ws_user2 = await connect(f"{HANDLER_URL.replace('http', 'ws')}/ws/{user2_id}")

        message = {
            'recipient_id': user2_id,
            'content': 'Hello New User!',
            'chat_id': None
        }
        await ws_user1.send(json.dumps(message))

        received_message = None
        for _ in range(5):
            response = await ws_user2.recv()
            data = json.loads(response)
            if data.get('type') == 'message':
                received_message = data
                break
        assert received_message is not None, "Did not receive 'message' type"
        assert received_message['content'] == 'Hello New User!'
        assert received_message['sender_id'] == user1_id
        chat_id = received_message['chat_id']
        assert chat_id is not None

        async with AsyncClient() as client:
            response = await client.get(f"{MESSAGE_SERVICE_URL}/chats/{user1_id}")
            assert response.status_code == 200
            chats = response.json()
            chat = next((chat for chat in chats if chat['_id'] == chat_id), None)
            assert chat is not None
            assert user1_id in chat['participants']
            assert user2_id in chat['participants']

        await ws_user1.close()
        await ws_user2.close()

    @pytest.mark.asyncio
    async def test_fetch_chats_and_messages_on_connect(self):
        user_id = 'user_fetch'

        ws_user = await connect(f"{HANDLER_URL.replace('http', 'ws')}/ws/{user_id}")

        ws_other = await connect(f"{HANDLER_URL.replace('http', 'ws')}/ws/other_user")
        message = {
            'recipient_id': user_id,
            'content': 'Hello Fetch User!',
            'chat_id': None
        }
        await ws_other.send(json.dumps(message))
        await ws_other.close()

        response = await ws_user.recv()
        data = json.loads(response)
        assert data['type'] == 'new_chats' or data['type'] == 'message'

        await ws_user.close()
