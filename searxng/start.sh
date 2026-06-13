#!/bin/bash
# Запуск SearXNG

cd "$(dirname "$0")"
echo "🚀 Запуск SearXNG..."
docker compose up -d
echo "✅ SearXNG запущен на http://localhost:8888"
echo "   Проверка: curl -s 'http://localhost:8888/search?q=test&categories=images&format=json'"
