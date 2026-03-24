"""Генератор 20 случайных todo через HTTP API приложения."""

import os
import random
import sys

import requests

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else os.getenv("TODO_BASE_URL", "http://localhost:8000")
LOGIN_PATH = "/auth/token"
ADD_PATH = "/todo/add/"
COUNT = 20
EMAIL = os.getenv("TODO_GENERATOR_EMAIL")
PASSWORD = os.getenv("TODO_GENERATOR_PASSWORD")

TITLES = [
    "Купить продукты", "Сделать домашнее задание", "Позвонить маме",
    "Почитать книгу", "Сходить в спортзал", "Приготовить ужин",
    "Написать отчёт", "Изучить Python", "Посмотреть лекцию",
    "Починить велосипед", "Убраться в комнате", "Оплатить счета",
    "Записаться к врачу", "Составить план на неделю", "Полить цветы",
    "Обновить резюме", "Ответить на письма", "Настроить Docker",
    "Сделать бэкап данных", "Пройти онлайн-курс", "Написать тесты",
    "Отрефакторить код", "Прочитать документацию", "Сходить на прогулку",
    "Проверить почту", "Сделать презентацию", "Изучить Elasticsearch",
    "Запустить миграции", "Обновить зависимости", "Написать README"
]

DETAILS = [
    "Не забыть сделать это сегодня",
    "Важная задача, требует внимания",
    "Запланировано на эту неделю",
    "Низкий приоритет, но нужно сделать",
    "Срочно, дедлайн скоро",
    "Обсудить с командой перед выполнением",
    "Требует дополнительных ресурсов",
    "Можно делегировать при необходимости",
    "",
    "",
]

TAGS = ["Учёба", "Личное", "Планы"]
SOURCES = ["Сгенерированная"]


def generate_todo() -> dict:
    title = random.choice(TITLES)
    suffix = random.randint(1, 9999)
    return {
        "title": f"{title} #{suffix}",
        "details": random.choice(DETAILS),
        "tag": random.choice(TAGS),
        "source": random.choice(SOURCES),
    }


def _build_session() -> requests.Session:
    if not EMAIL or not PASSWORD:
        raise SystemExit(
            "Нужно задать TODO_GENERATOR_EMAIL и TODO_GENERATOR_PASSWORD."
        )

    session = requests.Session()
    response = session.post(
        f"{BASE_URL}{LOGIN_PATH}",
        json={"email": EMAIL, "password": PASSWORD},
        allow_redirects=False,
        timeout=15,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            "Не удалось войти перед генерацией todo. "
            f"Статус: {response.status_code}. Ответ сервера: {response.text}"
        )

    if "access_token" not in session.cookies:
        raise RuntimeError("Не удалось получить access_token cookie после логина.")

    return session


def main():
    try:
        session = _build_session()
    except Exception as e:
        print(f"Ошибка авторизации: {e}")
        return

    print(f"Генерация {COUNT} тудушек на {BASE_URL}{ADD_PATH}...")
    success = 0
    failed = 0

    for i in range(1, COUNT + 1):
        todo = generate_todo()
        try:
            response = session.post(
                f"{BASE_URL}{ADD_PATH}",
                data=todo,
                timeout=15,
            )

            if response.status_code == 201:
                print(f"  [{i:02d}] ✅ Создана: {todo['title']}")
                success += 1
            else:
                print(
                    f"  [{i:02d}] ❌ Ошибка {response.status_code}: "
                    f"{todo['title']} — {response.text}"
                )
                failed += 1
        except requests.Timeout:
            print(f"  [{i:02d}] ❌ Таймаут запроса для: {todo['title']}")
            failed += 1
        except requests.ConnectionError:
            print(f"  [{i:02d}] ❌ Нет соединения с {BASE_URL}")
            failed += 1
            break
        except requests.RequestException as e:
            print(f"  [{i:02d}] ❌ Ошибка сети: {e}")
            failed += 1
            break

    print(f"\nГотово: {success} создано, {failed} ошибок.")


if __name__ == "__main__":
    main()
