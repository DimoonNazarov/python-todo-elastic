# ToDo App

## Запуск

```bash
sudo docker compose -f docker-compose.yml build

sudo docker compose -f docker-compose.yml up
```

## Тесты

```bash
sudo docker compose -f docker-compose-test.yml build

sudo docker compose -f docker-compose-test.yml up

sudo docker compose exec test /bin/bash
```

```bash
pytest -v tests/test_todos.py # запуск всех тестов

pytest -v tests/test_todos.py::test_add_todo_success # запуск конкретного теста
```