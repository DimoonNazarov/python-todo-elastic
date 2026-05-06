#!/bin/bash
# Скрипт демонстрации кластера Elasticsearch

ES="http://localhost:9200"
ES2="http://localhost:9201"
ES3="http://localhost:9202"
INDEX="demo"

echo "========================================"
echo " 1. Состав кластера и текущий мастер"
echo "========================================"
echo "--- Узлы кластера ---"
curl -s "$ES/_cat/nodes?v&h=ip,name,master,role,heap.percent,ram.percent"
echo ""
echo "--- Текущий мастер-узел ---"
curl -s "$ES/_cat/master?v"
echo ""

echo "========================================"
echo " 2. Создать индекс: 3 шарда, 1 реплика"
echo "========================================"
curl -s -X DELETE "$ES/$INDEX" > /dev/null 2>&1
curl -s -X PUT "$ES/$INDEX" -H 'Content-Type: application/json' -d '{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1
  }
}' | python3 -m json.tool
echo ""

echo "========================================"
echo " 3. Добавить документ (через es01:9200)"
echo "========================================"
curl -s -X POST "$ES/$INDEX/_doc/1" -H 'Content-Type: application/json' -d '{
  "title": "Демо задача",
  "description": "Документ для демонстрации шардирования и репликации",
  "status": "active",
  "created_at": "2026-03-30"
}' | python3 -m json.tool
echo ""

echo "========================================"
echo " 4. Прочитать документ ЧЕРЕЗ ДРУГОЙ УЗЕЛ (es02:9201)"
echo "========================================"
curl -s "$ES2/$INDEX/_doc/1" | python3 -m json.tool
echo ""

echo "========================================"
echo " 5. Распределение шардов по узлам"
echo "========================================"
curl -s "$ES/_cat/shards/$INDEX?v&h=index,shard,prirep,state,node,docs"
echo ""

echo "========================================"
echo " 6. Где физически находится наш документ"
echo "========================================"
echo "--- Первичные шарды (p) и реплики (r) индекса $INDEX ---"
curl -s "$ES/_cat/shards/$INDEX?v"
echo ""

echo "========================================"
echo " 7. Здоровье кластера"
echo "========================================"
curl -s "$ES/_cluster/health?pretty"
echo ""

echo "========================================"
echo " ДЛЯ ДЕМО ПАДЕНИЯ МАСТЕРА выполни:"
echo "========================================"
MASTER=$(curl -s "$ES/_cat/master?h=node" | tr -d '[:space:]')
echo "  Текущий мастер: $MASTER"
echo ""
echo "  Остановить мастер:"
echo "    sudo docker stop $MASTER"
echo ""
echo "  После остановки проверить переизбрание:"
echo "    curl -s http://localhost:9201/_cat/master?v"
echo "    curl -s http://localhost:9201/_cat/nodes?v"
echo ""
echo "  Прочитать документ после падения мастера (через другой узел):"
echo "    curl -s http://localhost:9201/$INDEX/_doc/1"
echo ""
echo "  Вернуть узел:"
echo "    sudo docker start $MASTER"
echo ""
