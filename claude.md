# Python TODO Elastic - Документация для Claude

## Обзор проекта

Веб-приложение для управления задачами (TODO) с расширенной функциональностью поиска, аналитики и интеграцией с LLM. Разработано в рамках учебных лабораторных работ по изучению Elasticsearch.

## Стек технологий

### Backend
- **FastAPI 0.115.0** - асинхронный веб-фреймворк
- **Python 3.x** - язык программирования
- **SQLAlchemy 2.0.35** - async ORM для работы с PostgreSQL
- **Alembic 1.13.2** - система миграций БД
- **Pydantic 2.9.2** - валидация данных и настройки

### Базы данных
- **PostgreSQL 16** - основная реляционная БД (через asyncpg)
- **Elasticsearch 9.3.0** - поисковый движок и аналитика
- **Kibana 9.3.0** - визуализация данных Elasticsearch

### Аутентификация и безопасность
- **JWT** (python-jose) - токены доступа и обновления
- **bcrypt** - хеширование паролей
- **passlib** - работа с паролями

### ML и NLP
- **spacy 3.8.7** - NLP для суммаризации текстов (русская модель)
- **scikit-learn 1.5.2** - кластеризация (KMeans)
- **OpenRouter API** - интеграция с LLM для генерации заголовков и суммаризации

### Визуализация
- **matplotlib 3.9.2** - графики
- **seaborn 0.13.2** - статистические визуализации
- **pandas 2.2.3** - обработка данных для графиков

### DevOps
- **Docker & Docker Compose** - контейнеризация
- **pytest 8.3.3** - тестирование
- **GitHub Actions** - CI/CD (`.github/workflows/ci.yml`)
- **Celery 5.4.0 + Redis 7** - отложенные задачи (напоминания о дедлайнах), брокер и Pub/Sub

## Архитектура приложения

### Структура (Layered Architecture)

```
app/
├── main.py                 # Точка входа, настройка FastAPI
├── config.py              # Настройки через Pydantic Settings
├── core/                  # Ядро приложения
│   ├── database.py        # Подключение к PostgreSQL и Elasticsearch
│   ├── uow.py            # Unit of Work паттерн
│   ├── celery_app.py     # Настройка Celery (брокер/backend Redis, beat_schedule)
│   └── logging_config.py  # Loguru настройка
├── models/               # SQLAlchemy модели (БД слой)
│   ├── user.py          # User, UserRole
│   ├── todo.py          # Todo (включая due_at, reminder_sent)
│   ├── todo_edit_history.py
│   ├── comment.py       # Comment (с ответами через parent_id)
│   ├── notification.py  # Notification (mention/reply/deadline)
│   └── refresh_token.py
├── schemas/             # Pydantic схемы (валидация)
│   ├── schemas.py       # TodoSource, SUserInfo и др.
│   ├── comment.py       # CommentCreate/Response, NotificationResponse
│   └── user.py
├── repository/          # Слой доступа к данным
│   ├── todo_repository.py      # CRUD для Todo (PostgreSQL)
│   ├── elastic_repository.py   # Работа с Elasticsearch
│   ├── auth_repository.py      # Работа с User
│   ├── comment_repository.py   # CRUD для Comment
│   ├── notification_repository.py  # CRUD для Notification
│   └── token_repository.py     # Refresh токены
├── services/            # Бизнес-логика
│   ├── todo.py         # TodoService - основная логика задач
│   ├── auth.py         # AuthService - аутентификация
│   ├── search_index.py # Индексирование в ES, поиск
│   ├── summary.py      # Суммаризация (spacy + LLM)
│   ├── clustering.py   # KMeans кластеризация
│   ├── openrouter.py   # Интеграция с LLM API
│   ├── comment.py      # CommentService - комментарии и их уведомления
│   ├── reminder.py     # ReminderService - напоминания о дедлайнах (для Celery)
│   ├── notification_bus.py  # Redis Pub/Sub мост Celery-воркер -> WebSocket FastAPI
│   └── websocket_manager.py  # ConnectionManager (комнаты по todo_id и по user_id)
├── tasks/               # Celery-задачи
│   └── reminders.py     # check_due_reminders — периодическая проверка дедлайнов
├── routers/            # HTTP endpoints (FastAPI роутеры)
│   ├── api/
│   │   ├── todo_router.py     # /todo/* endpoints
│   │   ├── auth_router.py     # /auth/* endpoints
│   │   └── comment_router.py  # /todo/{id}/comments/*, /api/notifications/*, /ws/*
│   ├── dependencies.py      # JWT auth dependencies
│   └── exception_handlers.py
├── middleware/
│   └── jwt_auth_middleware.py  # Middleware для JWT
├── utils/              # Вспомогательные функции
│   ├── jwt_utils.py    # Работа с JWT
│   ├── security.py     # Хеширование паролей
│   └── utils.py        # Общие утилиты
├── static/             # CSS, JS
└── templates/          # Jinja2 HTML шаблоны
```

### Паттерны

1. **Unit of Work (UoW)** - управление транзакциями и репозиториями
   - `app/core/uow.py` - координирует работу с БД и ES
   - Все репозитории доступны через `uow.todo`, `uow.auth`, `uow.elastic`

2. **Repository Pattern** - абстракция доступа к данным
   - Отдельные репозитории для PostgreSQL и Elasticsearch
   - Асинхронные методы

3. **Dependency Injection** - через FastAPI Depends
   - `get_async_uow_session()` - получение UoW
   - `get_current_active_user()` - получение текущего пользователя
   - `get_todo_service()`, `get_auth_service()` - сервисы

## Модели данных

### User (PostgreSQL)
```python
- id: int (PK)
- email: str (unique)
- hashed_password: str
- first_name: str
- last_name: str
- role: UserRole (ADMIN, EDITOR, VIEWER)
- is_active: bool
- created_at: datetime
- updated_at: datetime
# Relationships:
- todos: List[Todo] (созданные задачи)
- updated_todos: List[Todo] (измененные задачи)
- refresh_tokens: List[RefreshToken]
- todo_edit_history: List[TodoEditHistory]
```

### Todo (PostgreSQL)
```python
- id: int (PK)
- title: str
- details: str
- completed: bool
- tag: str | None
- author_id: int (FK -> users.id)
- created_at: datetime
- completed_at: datetime | None
- updated_at: datetime | None
- updated_by: int | None (FK -> users.id)
- due_at: datetime | None  # дедлайн, редактируется при создании и в форме edit.html
- reminder_sent: bool  # сброшен в False при любом изменении due_at (см. TodoService.update)
- source: str (created/imported/edited)
- image_path: str | None
- image_hash: str | None  # для поиска дубликатов
- details_hash: str | None
- spacy_summary: str | None  # суммаризация через spacy
- llm_summary: str | None    # суммаризация через LLM
# Relationships:
- author: User
- updated_by_user: User
- edit_history: List[TodoEditHistory]
```

### TodoEditHistory (PostgreSQL)
```python
- id: int (PK)
- todo_id: int (FK)
- editor_id: int (FK)
- edited_at: datetime
- changes: JSON  # что изменилось
```

### RefreshToken (PostgreSQL)
```python
- id: int (PK)
- user_id: int (FK)
- token: str (unique)
- device_info: str
- expires_at: datetime
- created_at: datetime
```

### Comment (PostgreSQL)
```python
- id: int (PK)
- todo_id: int (FK -> todos.id)
- author_id: int (FK -> users.id)
- parent_id: int | None (FK -> comments.id)  # для ответов на комментарии
- content: str
- created_at: datetime
- updated_at: datetime | None
- is_deleted: bool  # soft delete
```

### Notification (PostgreSQL)
```python
- id: int (PK)
- recipient_id: int (FK -> users.id)
- todo_id: int (FK -> todos.id)
- comment_id: int | None (FK -> comments.id)  # None для type="deadline"
- type: str  # "mention" | "reply" | "deadline"
- is_read: bool
- created_at: datetime
```

### Todo в Elasticsearch
```json
{
  "todo_id": 1,
  "title": "...",
  "details": "...",
  "tag": "...",
  "created_at": "2024-01-01T12:00:00",
  "completed": false,
  "author_id": 1
}
```

## Основные возможности

### 1. Управление задачами
- CRUD операции с TODO
- Привязка к пользователям (автор и редактор)
- История изменений (кто, когда, что изменил)
- Теги (произвольные, с автодополнением)
- Загрузка изображений к задачам
- Дубликаты (определение через хеши)

### 2. Поиск и фильтрация (Elasticsearch)
- Полнотекстовый поиск по title и details
- Фильтр по тегам
- Фильтр по дате создания (created_from, created_to)
- Топ-10 самых популярных слов
- Поиск дубликатов

### 3. Аналитика
- Агрегация задач по дням/неделям/месяцам
- Визуализация активности пользователей (графики через matplotlib/seaborn)
- Количество заметок в день от пользователя

### 4. ML и AI
- **Суммаризация текста**:
  - Через spacy (русская модель)
  - Через OpenRouter LLM API
- **Кластеризация**: sklearn KMeans для группировки задач
- **Генерация заголовков**: LLM генерирует заголовки по описанию
- **Предложение тегов**: на основе кластеризации/LLM

### 5. Аутентификация и авторизация
- Регистрация/вход через JWT
- Access token (30 мин) + Refresh token (30 дней)
- Роли:
  - **ADMIN** - полный доступ, управление пользователями
  - **EDITOR** - создание/редактирование своих задач
  - **VIEWER** - только просмотр (была удалена в миграции)
- Middleware для проверки JWT в cookies

### 6. Импорт/экспорт (app/utils/utils.py + todo_router.py)
- **Экспорт** (`export_todos`): Todo ORM → Excel (15 колонок)
- **Импорт** (`import_todos`): Excel → `list[dict]`, роутер создаёт ORM с `author_id`
- 15 колонок Excel: `title, details, completed, tag, created_at, completed_at, due_at, updated_at, updated_by, source, spacy_summary, llm_summary, image_path, image_hash, details_hash`
- Импорт ставит `source=TodoSource.imported`, `author_id=current_user.id`
- Файлы загрузок сохраняются в `./files/` (доступны на `/todo/import-log`)
- Endpoint импорта: `POST /todo/import` → JSON `{"status":"success",...}` (не redirect)
- Генерация случайных TODO: `POST /todo/generate/` или скрипт `generate_todos.py`

### 7. Комментарии и упоминания
- Комментарии к задаче с ответами (`parent_id`), soft delete
- `@email` в тексте комментария → уведомление упомянутому пользователю
- Ответ на комментарий → уведомление автору родительского комментария
- Реалтайм через WebSocket `/ws/todo/{todo_id}/` (новый/удалённый комментарий)

### 8. Напоминания о дедлайнах
- Дедлайн (`due_at`) задаётся при создании и редактируется в `edit.html`
- Celery beat каждые `DEADLINE_REMINDER_CHECK_INTERVAL_SECONDS` (по умолчанию 60 сек)
  запускает `reminders.check_due_reminders`, который ищет незавершённые задачи
  с `due_at` в пределах ближайших `DEADLINE_REMINDER_BEFORE_MINUTES` минут (по умолчанию 60)
  и ещё не уведомлённые (`reminder_sent=False`)
- Для каждой находит создаётся `Notification(type="deadline")`, `reminder_sent` ставится в `True`
- Изменение `due_at` в `TodoService.update()` сбрасывает `reminder_sent` обратно в `False`
- Доставка на фронт — только через WebSocket, без Telegram (см. раздел ниже)

## Ключевые файлы

### Конфигурация
- `app/config.py` - все настройки (через .env)
- `.env` - переменные окружения (POSTGRES_*, JWT_*, OPENROUTER_*)
- `docker-compose.yml` - dev окружение (single-node ES)
- `docker-compose-cluster.yml` - prod кластер ES (3 узла)

### База данных
- `app/core/database.py` - подключения к PostgreSQL и ES
- `migrations/versions/` - Alembic миграции
- `alembic.ini` - настройка Alembic

### Сервисы (бизнес-логика)
- `app/services/todo.py` (~800 строк) - основной сервис задач
- `app/services/search_index.py` - индексирование и поиск в ES
- `app/services/auth.py` - регистрация, вход, refresh токенов
- `app/services/summary.py` - суммаризация текста
- `app/services/clustering.py` - кластеризация задач
- `app/services/openrouter.py` - работа с LLM API
- `app/services/comment.py` - комментарии, @mention/reply уведомления
- `app/services/reminder.py` - `ReminderService.notify_due_soon()`, вызывается из Celery-задачи
- `app/services/notification_bus.py` - Redis Pub/Sub мост Celery-воркер → WebSocket FastAPI
- `app/services/websocket_manager.py` - `ConnectionManager` (`manager` для комнат todo, `user_manager` для личных уведомлений)

### Репозитории
- `app/repository/todo_repository.py` - CRUD для Todo (PostgreSQL), включая `get_todos_due_soon`/`mark_reminder_sent`
- `app/repository/elastic_repository.py` (~600 строк) - все операции с ES
- `app/repository/auth_repository.py` - работа с User
- `app/repository/comment_repository.py` - CRUD для Comment
- `app/repository/notification_repository.py` - CRUD для Notification
- `app/repository/token_repository.py` - refresh токены

### Роутеры
- `app/routers/api/todo_router.py` - все endpoints для задач
- `app/routers/api/auth_router.py` - регистрация, вход, выход
- `app/routers/api/comment_router.py` - комментарии, `/api/notifications/*`, `/ws/todo/{id}/`, `/ws/notifications/`

### Celery
- `app/core/celery_app.py` - инстанс Celery (broker/backend = Redis), `beat_schedule`
- `app/tasks/reminders.py` - задача `reminders.check_due_reminders` (регистрируется через `include=` в celery_app)
- `docker_scripts/celery_worker.sh`, `docker_scripts/celery_beat.sh` - точки входа контейнеров

## Важные концепты

### Elasticsearch индекс "todos_index"
- Создается автоматически при старте (`ElasticRepository.ensure_index_exists()`)
- Маппинг:
  - `title`, `details` - text с русским анализатором
  - `tag` - keyword для фильтрации
  - `created_at` - date для агрегаций
  - Фильтры: стоп-слова русского языка + кастомные имена

### JWT Authentication Flow
1. User -> POST /auth/token (email, password)
2. Server проверяет credentials
3. Server генерирует access + refresh токены
4. Токены сохраняются в httponly cookies
5. Middleware проверяет access_token в каждом запросе
6. При истечении access_token -> POST /auth/refresh (refresh_token)

### Unit of Work — паттерн использования
```python
# uow.start() — context manager (app/core/uow.py)
# Автоматически: commit при успехе, rollback + compensations при исключении
# НЕ вызывать commit() вручную — он вызывается при выходе из контекста

async with uow_session.start():
    await uow_session.todo.add(todo)
    await uow_session.flush()          # flush чтобы получить todo.id (для ES)

    # Индексация в Elasticsearch (паттерн из TodoService.create):
    from app.services.search_index import build_search_document
    document = build_search_document(todo)
    await uow_session.elastic.ensure_index_exists()
    await uow_session.elastic.index_document(todo.id, document)
    uow_session.add_compensation(uow_session.elastic.delete_todo, todo.id)
    # ^ compensation откатит ES-документ при rollback транзакции

# ВАЖНО: без `async with uow_session.start()` репозитории НЕ работают
# (нет сессии БД), и данные НЕ сохраняются (нет commit)
```

### Синхронизация PostgreSQL ↔ Elasticsearch
- При создании TODO: `TodoRepository.add()` + `ElasticRepository.index_todo()`
- При обновлении: обновление в PostgreSQL + реиндексация в ES
- При удалении: удаление из обеих БД

### Напоминания о дедлайнах: Celery → Redis Pub/Sub → WebSocket
Celery-воркер работает в отдельном процессе/контейнере и не имеет доступа
к in-memory `ConnectionManager` внутри процесса FastAPI, поэтому события
передаются через Redis Pub/Sub, а не напрямую:

```
[celery beat]  каждые DEADLINE_REMINDER_CHECK_INTERVAL_SECONDS
      │  отправляет task "reminders.check_due_reminders"
      ▼
[celery worker]  app/tasks/reminders.py: check_due_reminders()
      │  1. asyncio.run(...) → ReminderService.notify_due_soon(uow, before_minutes=...)
      │     - TodoRepository.get_todos_due_soon(now, threshold): due_at в пределах
      │       DEADLINE_REMINDER_BEFORE_MINUTES, completed=False, reminder_sent=False
      │     - создаёт Notification(type="deadline"), TodoRepository.mark_reminder_sent()
      │  2. publish_notification_sync(payload) → Redis PUBLISH "ws:notifications"
      ▼
[Redis Pub/Sub канал "ws:notifications"]
      ▼
[FastAPI процесс]  app/services/notification_bus.listen_for_notifications()
      │  фоновая asyncio-задача, запущена в lifespan (app/main.py)
      │  SUBSCRIBE "ws:notifications" → на каждое сообщение:
      │  user_manager.broadcast(recipient_id, {"type": "deadline", ...})
      ▼
[Браузер]  WebSocket /ws/notifications/ (base.html) → loadNotifications() обновляет колокольчик
```

- `/ws/notifications/` аутентифицирует по cookie `access_token` (тот же формат
  `"Bearer <jwt>"`, что и HTTP-middleware), закрывает соединение с
  `WS_1008_POLICY_VIOLATION`, если токен невалиден
- Изменение `due_at` в `TodoService.update()` сбрасывает `reminder_sent=False`,
  иначе задача с новым сроком не попадёт повторно в `get_todos_due_soon`
- Telegram сознательно не используется — только WebSocket, по требованию задачи

## Endpoints (основные)

### Auth
- GET `/auth/login` - форма входа
- POST `/auth/token` - вход (получение токенов)
- POST `/auth/register` - регистрация
- POST `/auth/refresh` - обновление access token
- POST `/auth/logout` - выход

### Todo
- GET `/todo/home/` - список всех задач (с пагинацией)
- POST `/todo/add/` - создание задачи
- GET `/todo/{id}` - просмотр задачи
- POST `/todo/update/{id}` - обновление задачи
- POST `/todo/delete/{id}` - удаление задачи
- GET `/todo/search/` - поиск (query, tag, date_from)
- GET `/todo/analytics/` - страница аналитики
- POST `/todo/generate/` - генерация N случайных задач
- POST `/todo/summarize/{id}` - суммаризация задачи
- GET `/todo/suggest-tags/{id}` - предложение тегов

### Комментарии и уведомления
- GET/POST `/todo/{todo_id}/comments/` - список / создание комментария
- DELETE `/todo/{todo_id}/comments/{comment_id}/` - soft delete
- GET `/api/notifications/`, GET `/api/notifications/count/` - список / счётчик непрочитанных
- POST `/api/notifications/{id}/read/`, POST `/api/notifications/read-all/`
- WS `/ws/todo/{todo_id}/` - реалтайм комментариев
- WS `/ws/notifications/` - личный канал (mention/reply/deadline), авторизация по cookie `access_token`

## Тестирование

```bash
# Запуск тестов в Docker
sudo docker compose -f docker-compose-test.yml build
sudo docker compose -f docker-compose-test.yml up
sudo docker compose exec test /bin/bash
pytest -v tests/test_todos.py
```

## Elasticsearch кластер

### Архитектура (docker-compose-cluster.yml)
- 3 узла Elasticsearch (es01:9200, es02:9201, es03:9202)
- 1 Kibana (5601)
- Кворум: 2 из 3 (выдерживает падение 1 узла)
- Каждый узел: master-eligible + data node

### Важные команды
```bash
# Здоровье кластера
curl http://localhost:9200/_cluster/health?pretty

# Узлы и мастер
curl http://localhost:9200/_cat/nodes?v
curl http://localhost:9200/_cat/master?v

# Шарды индекса
curl http://localhost:9200/_cat/shards/todos_index?v
```

## Docker окружение

### Сервисы
1. **db** (postgres:16-alpine) - порт 5433
2. **web** (FastAPI app) - порт 8000
3. **elasticsearch** - порты 9200, 9300
4. **kibana** - порт 5601
5. **redis** (redis:7-alpine) - порт 6379 — брокер/backend Celery и Pub/Sub для WebSocket-уведомлений
6. **celery_worker** - выполняет задачу `reminders.check_due_reminders`
7. **celery_beat** - планировщик, шлёт задачу каждые `DEADLINE_REMINDER_CHECK_INTERVAL_SECONDS`

### Volumes
- `postgres_data_8` - данные PostgreSQL
- `./data/elasticsearch` - данные ES
- `./files` → `/code/files` — загруженные файлы импорта
- Bind mounts для hot reload: `./app`, `./scripts`, etc.

### Сеть
- `app-network` (bridge)

## Скрипты

- `docker_scripts/app.sh` - запуск uvicorn в контейнере
- `docker_scripts/celery_worker.sh` - запуск Celery worker
- `docker_scripts/celery_beat.sh` - запуск Celery beat (планировщик)
- `scripts/generate_todos.py` - генерация тестовых данных (20 TODO)
- `scripts/demo_cluster.sh` - демонстрация работы кластера ES

## Миграции (Alembic)

```bash
# Создание миграции
alembic revision --autogenerate -m "description"

# Применение миграций
alembic upgrade head

# Откат
alembic downgrade -1
```

### История миграций
- `62553a9ed760` - init (базовая структура Todo)
- `2957b9671fe3` - добавлен image_path
- `2488d2f9e026` - добавлена таблица User
- `e392813ea43d` - добавлено поле disabled в User
- `767190600c0e` - добавлен image_hash
- `e50af0fcd9cc` - изменен столбец source
- `796573c30868` - новые таблицы (TodoEditHistory, RefreshToken)
- `7b7f031af7af` - связь todos с user
- `881c1dc3854d` - удалена роль VIEWER
- `e2f3a4b5c6d7` - таблицы Comment и Notification
- `f3a4b5c6d7e8` - добавлен file_path в todo_edit_history
- `a1b2c3d4e5f6` - добавлен reminder_sent в todos, comment_id в notifications стал nullable

## Тестирование через curl/python

```bash
# Порты: web=8000, postgres=5433 (на хосте), ES=9200, kibana=5601
# Пользователь: max@mail.ru (ADMIN)
# Docker-доступ требует sudo (пользователь не в группе docker)

# Авторизация — через python requests (cookie-based JWT):
import requests
s = requests.Session()
s.post("http://localhost:8000/auth/token",
       json={"email":"max@mail.ru","password":"..."}, allow_redirects=False)
# Далее s автоматически передаёт cookies access_token/refresh_token

# Прямой доступ к БД:
import psycopg2
conn = psycopg2.connect(host='localhost', port=5433, dbname='python_ddz',
                         user='postgres', password='postgres')
```

## Известные особенности

1. **Безопасность ES отключена** (`xpack.security.enabled=false`) - для dev окружения
2. **Первый пользователь** всегда получает роль ADMIN
3. **Hot reload** в Docker через bind mounts (изменения кода применяются автоматически)
4. **OpenRouter API** требует ключ в .env (`OPENROUTER_API_KEY`)
5. **Русский язык** - анализаторы и стоп-слова настроены для русского
6. **Логирование** через loguru (файлы в каталоге логов)
7. **create_dirs()** в `app/utils/utils.py` создаёт `data/`, `images/`, `files/` при старте
8. **Фронтенд** вызывает API через `fetchWithAuth` (AJAX) — endpoints должны возвращать JSON, не RedirectResponse
9. **Exceptions**: `app/exceptions.py` — `AppException`, `SearchSyncException` и др.
10. **Celery-воркер не шарит память с FastAPI** — доставка WebSocket-уведомлений из Celery-задачи идёт только через Redis Pub/Sub (`app/services/notification_bus.py`), напрямую вызвать `ConnectionManager.broadcast` из таска нельзя
11. **`UnitOfWork(async_session_maker, es_client=None)`** — так создаётся UoW внутри Celery-задачи, т.к. Elasticsearch там не нужен и `AsyncElasticsearch` нельзя переиспользовать между вызовами `asyncio.run()` (разные event loop'ы)

## Переменные окружения (.env)

```bash
# PostgreSQL
POSTGRES_HOST=todo-db
POSTGRES_PORT=5432
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# JWT
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=30

# OpenRouter (LLM)
OPENROUTER_API_KEY=sk-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openrouter/free
OPENROUTER_TIMEOUT_SECONDS=60

# Redis / Celery (напоминания о дедлайнах)
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
DEADLINE_REMINDER_BEFORE_MINUTES=60
DEADLINE_REMINDER_CHECK_INTERVAL_SECONDS=60
```

## Учебный контекст (из LR.md)

Проект создан для изучения:
- Работы с Elasticsearch (индексация, поиск, агрегации)
- Кластеризации и шардирования
- Интеграции PostgreSQL + Elasticsearch
- JWT аутентификации
- ML/NLP (spacy, sklearn)
- LLM интеграции
- Docker/Docker Compose
- CI/CD через GitHub Actions

Выполнены ЛР №1-4 по применению Elasticsearch.