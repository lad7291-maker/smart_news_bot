#!/bin/bash
PIDFILE=/var/run/newsbot.pid

# Проверяем, не запущен ли уже
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "ERROR: Бот уже запущен (PID $OLD_PID)"
        exit 1
    fi
fi

# Запускаем
cd /root/smart_news_bot
source venv/bin/activate
exec python3 bot_runner.py &
echo $! > "$PIDFILE"
echo "Запущен (PID $!)"
