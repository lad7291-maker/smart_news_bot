#!/bin/bash
# Остановка SearXNG

cd "$(dirname "$0")"
echo "🛑 Остановка SearXNG..."
docker compose down
echo "✅ SearXNG остановлен"
