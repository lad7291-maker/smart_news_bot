#!/bin/bash
PIDFILE=/var/run/newsbot.pid
if [ -f "$PIDFILE" ]; then
    kill $(cat "$PIDFILE") 2>/dev/null
    rm -f "$PIDFILE"
    echo "Остановлен"
else
    pkill -f "bot_runner.py"
    echo "Остановлен (fallback)"
fi
