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

## Архитектура приложения

### Структура (Layered Architecture)

```
app/
├── main.py                 # Точка входа, настройка FastAPI
├── config.py              # Настройки через Pydantic Settings
├── core/                  # Ядро приложения
│   ├── database.py        # Подключение к PostgreSQL и Elasticsearch
│   ├── uow.py            # Unit of Work паттерн
│   └── logging_config.py  # Loguru настройка
├── models/               # SQLAlchemy модели (БД слой)
│   ├── user.py          # User, UserRole
│   ├── todo.py          # Todo
│   ├── todo_edit_history.py
│   └── refresh_token.py
├── schemas/             # Pydantic схемы (валидация)
│   ├── schemas.py       # TodoSource, SUserInfo и др.
│   └── user.py
├── repository/          # Слой доступа к данным
│   ├── todo_repository.py      # CRUD для Todo (PostgreSQL)
│   ├── elastic_repository.py   # Работа с Elasticsearch
│   ├── auth_repository.py      # Работа с User
│   └── token_repository.py     # Refresh токены
├── services/            # Бизнес-логика
│   ├── todo.py         # TodoService - основная логика задач
│   ├── auth.py         # AuthService - аутентификация
│   ├── search_index.py # Индексирование в ES, поиск
│   ├── summary.py      # Суммаризация (spacy + LLM)
│   ├── clustering.py   # KMeans кластеризация
│   ├── openrouter.py   # Интеграция с LLM API
│   ├── telegram.py     # Telegram Bot API: отправка заметок, коды привязки
│   └── telegram_polling.py  # Фоновый getUpdates-поллинг (/start <код>)
├── routers/            # HTTP endpoints (FastAPI роутеры)
│   ├── api/
│   │   ├── todo_router.py  # /todo/* endpoints
│   │   ├── auth_router.py  # /auth/* endpoints
│   │   └── telegram_router.py  # /telegram/* endpoints
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
- telegram_chat_id: int | None  # привязанный Telegram-чат (BigInteger)
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
- due_at: datetime | None
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

### 6. Сохранение заметок в Telegram
- Кнопка «В Telegram» в карточке задачи на странице списка (todos.html, макрос
  `todo_item`, класс `sendTelegramButton`)
- Привязка чата: `GET /telegram/link/` выдаёт deep-link `t.me/<bot>?start=<код>`;
  код — компактный HMAC (`user_id_expires_подпись`, ≤64 символов — лимит Telegram
  на start-параметр, JWT не влезает), подписан `JWT_SECRET_KEY`, TTL из
  `TELEGRAM_LINK_TTL_MINUTES`
- Фоновый поллинг `getUpdates` (запускается в lifespan, только если задан
  `TELEGRAM_BOT_TOKEN`) ловит `/start <код>` и сохраняет `chat_id` в `users.telegram_chat_id`
- Команда бота `/tasks`: inline-клавиатура с активными пользователями
  (callback_data `tasks:<user_id>`), по нажатию — карточки невыполненных задач
  выбранного пользователя (`TodoRepository.get_pending_todos_by_author_id`,
  сортировка по due_at, максимум 10 карточек). Карточка: заголовок, реферат
  (llm/spacy) или укороченный текст, тег, срок, статус + кнопка
  «✅ Отметить выполненной» (callback_data `done:<todo_id>`)
- Подтверждение выполнения из бота идёт через `TodoService.update` от имени
  владельца чата: те же права (автор или админ), история изменений и синхронизация
  с Elasticsearch, что и в приложении; карточка редактируется через
  `editMessageText`: статус «Выполнена», кнопка меняется на индикатор
  «🎉 Задача выполнена» (callback_data `noop`). Доступно только из привязанных
  чатов; один чат привязан ровно к одному аккаунту (при `/start` привязка
  с других снимается)
- Живое обновление списка задач: при выполнении из бота событие
  `{"type": "todo_completed", ...}` рассылается в WebSocket-канал `/ws/todos/`
  (`TODOS_FEED_CHANNEL = 0` в websocket_manager), страница todos.html помечает
  карточку выполненной без перезагрузки
- Отправка: `POST /telegram/send/{todo_id}/` — форматирует заметку (заголовок, описание,
  рефераты spaCy/LLM при наличии, тег, срок, статус; HTML parse_mode, экранирование)
  и шлёт через `sendMessage`
- Исключения: `TelegramConfigurationException` (503), `TelegramServiceException` (502),
  `TelegramNotLinkedException` (400 — фронт в ответ показывает ссылку привязки)
- Юнит-тесты: `tests/test_telegram.py` (коды привязки, формат сообщения; без сети)

### 7. Импорт/экспорт (app/utils/utils.py + todo_router.py)
- **Экспорт** (`export_todos`): Todo ORM → Excel (15 колонок)
- **Импорт** (`import_todos`): Excel → `list[dict]`, роутер создаёт ORM с `author_id`
- 15 колонок Excel: `title, details, completed, tag, created_at, completed_at, due_at, updated_at, updated_by, source, spacy_summary, llm_summary, image_path, image_hash, details_hash`
- Импорт ставит `source=TodoSource.imported`, `author_id=current_user.id`
- Файлы загрузок сохраняются в `./files/` (доступны на `/todo/import-log`)
- Endpoint импорта: `POST /todo/import` → JSON `{"status":"success",...}` (не redirect)
- Генерация случайных TODO: `POST /todo/generate/` или скрипт `generate_todos.py`

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

### Репозитории
- `app/repository/todo_repository.py` - CRUD для Todo (PostgreSQL)
- `app/repository/elastic_repository.py` (~600 строк) - все операции с ES
- `app/repository/auth_repository.py` - работа с User
- `app/repository/token_repository.py` - refresh токены

### Роутеры
- `app/routers/api/todo_router.py` - все endpoints для задач
- `app/routers/api/auth_router.py` - регистрация, вход, выход

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

### Telegram
- GET `/telegram/link/` - статус привязки + deep-link для подключения чата
- POST `/telegram/unlink/` - отвязать чат
- POST `/telegram/send/{todo_id}/` - отправить заметку в привязанный чат

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

### Volumes
- `postgres_data_8` - данные PostgreSQL
- `./data/elasticsearch` - данные ES
- `./files` → `/code/files` — загруженные файлы импорта
- Bind mounts для hot reload: `./app`, `./scripts`, etc.

### Сеть
- `app-network` (bridge)

## Скрипты

- `docker_scripts/app.sh` - запуск uvicorn в контейнере
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

# Telegram (сохранение заметок в бота)
TELEGRAM_BOT_TOKEN=  # токен от @BotFather; пусто = функция выключена
TELEGRAM_BOT_USERNAME=  # опционально, иначе берётся через getMe
TELEGRAM_LINK_TTL_MINUTES=15
# env_file читается при создании контейнера — после изменения токена
# нужен `docker compose up -d web` (hot reload кода это не подхватит)
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