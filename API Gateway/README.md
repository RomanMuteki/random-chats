### Общая информация

API Gateway служит центральной точкой входа для всех клиентских запросов и обеспечивает маршрутизацию и балансировку нагрузки между различными микросервисами. Он обрабатывает аутентификацию, взаимодействие с сервисами и предоставляет единый интерфейс для взаимодействия с системой.

### Эндпоинты API Gateway

#### 1. Регистрация пользователя

- Метод: `POST`
- URL: `/register`
- Описание: Проксирует запрос на регистрацию нового пользователя в Auth Service.
- Формат запроса:
  ```json
  {
      "email": "user@example.com",
      "username": "username",
      "password": "password",
      "sex": "male",
      "age": 25,
      "preferred_age": "20-30",
      "preferred_sex": "female"
  }
  ```
- Ответ:
  ```json
  {
      "status": "success",
      "message": "User registered successfully",
      "avatar_code": 42
  }
  ```

#### 2. Авторизация пользователя

- Метод: `POST`
- URL: `/login`
- Описание: Проксирует запрос на авторизацию пользователя в Auth Service.
- Формат запроса:
  ```json
  {
      "email": "user@example.com",
      "password": "password"
  }
  ```
- Ответ:
  ```json
  {
      "status": "success",
      "access_token": "access_token_value",
      "refresh_token": "refresh_token_value",
      "uid": "user_id"
  }
  ```

#### 3. Аутентификация по токену

- Метод: `POST`
- URL: `/token_login`
- Описание: Проксирует запрос на аутентификацию пользователя по токену в Auth Service.
- Формат запроса:
  ```json
  {
      "token": "access_token_value"
  }
  ```
- Ответ:
  ```json
  {
      "status": "success",
      "message": "Access token is up to date"
  }
  ```

#### 4. Проверка токена

- Метод: `GET`
- URL: `/token_check`
- Описание: Проксирует запрос на проверку валидности токена в Auth Service.
- Параметры запроса:
  - token: Токен пользователя.
  - uid: Идентификатор пользователя.
- Ответ:
  ```json
  {
      "status": "success",
      "message": "Token is up to date, user submitted"
  }
  ```

#### 5. Получение WebSocket Handler

- Метод: `GET`
- URL: `/get_websocket_handler`
- Описание: Предоставляет доступный WebSocket Handler клиенту.
- Заголовки:
  - token: Токен пользователя.
  - uid: Идентификатор пользователя.
- Ответ:
  ```json
  {
      "websocket_handler_url": "http://localhost:8001",
      "handler_id": "WSH1"
  }
  ```

#### 6. Подбор пары (Matching)

- Метод: `POST`
- URL: `/matching`
- Описание: Проксирует запрос на подбор пары в Matching Service.
- Заголовки:
  - token: Токен пользователя.
  - uid: Идентификатор пользователя.
- Формат запроса:
  ```json
  {
      "uid": "user_id"
  }
  ```
- Ответ:
  ```json
  {
      "status": "success",
      "message": "user found",
      "uid": "matched_user_id"
  }
  ```

#### 7. Получение экземпляра сервиса

- Метод: `GET`
- URL: `/get_service_instance`
- Описание: Предоставляет другой экземпляр сервиса микросервису.
- Параметры запроса:
  - service_name: Название сервиса.
- Ответ:
  ```json
  {
      "instance": {
          "url": "http://localhost:8300"
      }
  }
  ```

#### 8. Проверка работоспособности

- Метод: `GET`
- URL: `/ping`
- Описание: Эндпоинт для проверки работоспособности API Gateway.
- Ответ:
  ```json
  {
      "message": "API Gateway работает"
  }
  ```

### Примечания

- Аутентификация: Для всех эндпоинтов, требующих аутентификации, необходимо передавать token и uid в заголовках.
- Балансировка нагрузки: API Gateway автоматически распределяет запросы между доступными экземплярами сервисов.
- Повторные попытки: В случае недоступности сервиса, API Gateway выполняет повторные попытки обращения к другим экземплярам.
