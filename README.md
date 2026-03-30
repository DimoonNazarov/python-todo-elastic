# ToDo App

## Запуск

```bash
sudo docker compose -f docker-compose.yml build

sudo docker compose -f docker-compose.yml up
```

## Генерация 20 todo через Docker

Скрипт [generate_todos.py](/home/max/Документы/python-todo-elastic/scripts/generate_todos.py) написан на Python и создаёт 20 случайных задач через ручку `POST /todo/add/`.

Перед запуском генератора:
- приложение должно быть поднято через `docker compose`
- в системе должен существовать пользователь
- нужно передать его email и пароль через переменные окружения

Сборка образа генератора:

```bash
sudo docker build -f Dockerfile_generate -t todo-generator .
```

Запуск генератора в сети docker compose:

```bash
sudo docker run --rm \
  --network python-todo-elastic_app-network \
  -e TODO_GENERATOR_EMAIL="user@example.com" \
  -e TODO_GENERATOR_PASSWORD="your_password" \
  todo-generator
```

Если имя docker-сети у вас отличается, посмотрите его через:

```bash
sudo docker network ls
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

---

## Кластер Elasticsearch

### Архитектура

Файл `docker-compose-cluster.yml` поднимает три узла Elasticsearch и Kibana на одной машине.
Каждый узел является master-eligible и data-узлом одновременно.

```
es01  →  порт 9200  (основная точка входа)
es02  →  порт 9201
es03  →  порт 9202
Kibana → порт 5601
```

Кворум для выбора мастера: **2 из 3** узлов (потеря одного не останавливает кластер).

### Требование к системе

Перед запуском кластера необходимо увеличить лимит виртуальной памяти на хосте:

```bash
sudo sysctl -w vm.max_map_count=262144
```

Чтобы настройка сохранялась после перезагрузки:

```bash
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
```

### Развёртывание С интернетом

```bash
sudo docker compose -f docker-compose-cluster.yml up -d
```

Проверить готовность (подождать ~60 секунд):

```bash
curl http://localhost:9200/_cluster/health?pretty
```

Ожидаемый результат: `"status": "green"` и `"number_of_nodes": 3`.

### Развёртывание БЕЗ интернета

Сохранить образы на машине с интернетом:

```bash
sudo docker pull elasticsearch:9.3.0
sudo docker pull kibana:9.3.0

sudo docker save elasticsearch:9.3.0 | gzip > elasticsearch-9.3.0.tar.gz
sudo docker save kibana:9.3.0        | gzip > kibana-9.3.0.tar.gz
```

Перенести архивы на целевую машину (флешка, scp, rsync) и загрузить:

```bash
sudo docker load < elasticsearch-9.3.0.tar.gz
sudo docker load < kibana-9.3.0.tar.gz
```

После загрузки запуск стандартный — интернет больше не нужен:

```bash
sudo docker compose -f docker-compose-cluster.yml up -d
```
