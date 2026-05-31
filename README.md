# Smart News Bot

> Автоматический новостной агрегатор с AI-анализом для Telegram-канала.

## Возможности

- **Агрегация новостей** из 15+ RSS-источников (русскоязычные и англоязычные)
- **AI-анализ** новостей через RouterAI (DeepSeek/Kimi) с fallback на YandexGPT
- **Перевод** иностранных новостей на русский через Yandex Translate API
- **Дедупликация** — удаление дублей одной новости из разных источников
- **Поиск изображений** через DuckDuckGo с проверкой релевантности
- **Трёхуровневая система скорости**: red (8-10) / orange (5-7) / yellow (1-4)
- **Тихие часы** — отложенная публикация ночью (23:00-07:00 МСК)
- **SQLite-кэш** обработанных ссылок с защитой от повторной публикации

## Архитектура

```
smart_news_bot/
├── ai_core/              # AI-провайдеры (RouterAI, YandexGPT)
├── parsers/              # RSS-парсер
├── telegram_bot/         # Отправка постов в Telegram
├── storage/              # SQLite-кэш
├── utils/                # Дедупликация, поиск фото, политика публикаций
├── scheduler/            # Планировщик задач (APScheduler)
├── tests/                # Тесты pytest
├── bot_runner.py         # Основной запуск с polling
├── main.py               # Одноразовый запуск (для cron)
└── config.py             # Конфигурация и источники
```

## Установка

### 1. Клонирование и зависимости

```bash
git clone <repo-url>
cd smart_news_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Переменные окружения

Создайте файл `.env`:

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL_ID=@your_channel

# Yandex Cloud
YANDEX_API_KEY=your_yandex_key
YANDEX_FOLDER_ID=your_folder_id

# RouterAI (опционально, для AI-анализа)
ROUTERAI_API_KEY=your_routerai_key
ROUTERAI_MODEL=deepseek/deepseek-chat

# Настройки
LOG_LEVEL=INFO
REQUEST_TIMEOUT=10
CACHE_DURATION_DAYS=7
```

### 3. Запуск

```bash
# Основной режим (polling + планировщик)
python bot_runner.py

# Одноразовый запуск (для cron)
python main.py
```

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | Информация о боте |
| `/post_now` | Внеочередной сбор новостей |
| `/stats` | Статистика кэша и очереди |
| `/help` | Помощь |

## Источники новостей

### Русскоязычные
- Habr, VC.ru, N+1, SecurityLab
- Interfax, RT, RIA

### Англоязычные
- CoinDesk, CoinTelegraph, Investing.com
- CNBC, NYT (Business, Economy, Tech, DealBook)

## Политика публикаций

| Уровень | Балл | Задержка | Поведение |
|---|---|---|---|
| 🔴 Red | 8-10 | 0-30 сек | Немедленная публикация |
| 🟠 Orange | 5-7 | 15-30 мин | Публикация с задержкой |
| 🟡 Yellow | 1-4 | 2-4 часа / дайджест | Отложенная публикация или дайджест |

## Тесты

```bash
pytest tests/ -v
```

## Мониторинг

- Логи: `logs/bot.log`, `logs/errors.log`
- Pidfile: `/tmp/smart_news_bot.pid`
- Health-check: `utils/health.py` (в разработке)

## Лицензия

MIT
