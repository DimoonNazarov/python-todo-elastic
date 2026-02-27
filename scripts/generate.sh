#!/bin/bash

COUNT=${1:-20}

details=("Купить молоко" "Починить кран" "Сделать домашку" "Пойти на пробежку"
           "Позвонить другу" "Записаться на курсы" "Сделать уборку" "Сходить в магазин"
           "Приготовить ужин" "Почитать книгу" "Посмотреть фильм" "Написать статью"
           "Выучить новый язык" "Сделать вещи на благотворительность" "Погулять с собакой"
           "Сделать фотографии" "Составить план на неделю" "Попробовать новый рецепт"
           "Пробежать марафон" "Отдохнуть")

tags=("Учёба" "Личное" "Планы")

echo "Generating $COUNT todos"

for ((i=1; i <= COUNT; i++)); do
    title="Задача ${i}"

    random_index_details=$(( RANDOM % ${#details[@]} ))
    detail="${details[$random_index_details]}"

    random_index_tags=$(( RANDOM % ${#tags[@]} ))
    tag="${tags[$random_index_tags]}"

    curl -X POST 'http://localhost:8000/todo/add/' \
        -F "title=${title}" \
        -F "details=${detail}" \
        -F "tag=${tag}" \
        -F "source=Сгенерированная"
done