#!/bin/bash
cd /root/smart_news_bot

# Kill any existing bot instances
pkill -9 -f "bot_runner.py" 2>/dev/null
sleep 2

# Remove stale PID file
rm -f /tmp/smart_news_bot.pid

# Start bot
exec venv/bin/python3 bot_runner.py > logs/bot_runner.out 2>&1
