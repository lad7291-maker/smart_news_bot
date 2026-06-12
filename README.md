# Smart News Bot

> Автоматический новостной агрегатор с AI-анализом для Telegram-канала. Собирает новости из 15+ RSS-источников, переводит, анализирует через LLM и публикует с умной политикой задержек.

---

## Возможности

### Ядро
- **Агрегация новостей** из 15+ RSS-источников (русскоязычные и англоязычные)
- **AI-анализ** новостей через RouterAI (DeepSeek / Kimi) с fallback на YandexGPT
- **Перевод** иностранных новостей на русский через Yandex Translate API (асинхронный, с кэшем)
- **Дедупликация** — удаление дублей одной новости из разных источников
- **Поиск изображений** через SearXNG self-hosted с проверкой релевантности, транслитерацией и фильтрацией нерелевантных тем
- **SQLite-кэш** обработанных ссылок с защитой от повторной публикации

### Политика публикаций
- **Трёхуровневая система скорости**: red (8-10) / orange (5-7) / yellow (1-4)
- **Тихие часы** — отложенная публикация ночью (23:00-07:00 МСК)
- **Storm Mode** — агрессивная публикация при потоке важных новостей
- **Circuit Breaker** для RSS-источников — защита от каскадных сбоев

### Аналитика и UX
- **Реакции пользователей** — inline-кнопки 👍/👎/💾, команда `/top`
- **A/B тестирование** — 4 варианта формата постов, CTR и save rate
- **Аналитика** — статистика публикаций, реакций, AI-затрат (`/ai_cost`)
- **Автообновление контекста лидеров** — парсинг Wikipedia, обновление раз в 7 дней

---

## Архитектура

```
smart_news_bot/
├── ai_core/                  # AI-провайдеры и анализ
│   ├── ai_provider.py        # YandexGPT провайдер
│   ├── routerai_provider.py  # RouterAI (DeepSeek/Kimi)
│   ├── analyzer.py           # Синхронный анализ (legacy)
│   ├── analyzer_yandex.py    # Yandex-специфичный анализ
│   ├── leaders_updater.py    # Автообновление лидеров из Wikipedia
│   └── world_leaders_context.py  # Контекст мировых лидеров
├── core/                     # Ядро бота (scheduler, фильтры, скоринг)
│   ├── scheduler_jobs.py     # Задачи планировщика
│   ├── filters.py            # Фильтры контента
│   └── scoring.py            # Скоринг новостей
├── models/
│   └── article.py            # Pydantic-модели статей
├── parsers/                  # Парсеры
│   ├── rss_parser.py         # RSS-парсер с обработкой ошибок
│   └── image_extractor.py    # Извлечение изображений из RSS/HTML/OG
├── telegram_bot/             # Telegram-интеграция
│   ├── core.py               # Инициализация бота
│   ├── formatter.py          # Форматирование постов, A/B варианты
│   ├── poster.py             # Отправка постов в канал
│   └── handlers.py           # Обработчики команд
├── storage/                  # Хранилище SQLite
│   ├── cache.py              # Кэш ссылок и статей
│   ├── analytics.py          # Аналитика и AI-cost трекинг
│   ├── reactions.py          # Реакции пользователей
│   └── ab_testing.py         # A/B тестирование форматов
├── utils/                    # Утилиты
│   ├── deduplicator.py       # Дедупликация статей
│   ├── image_search.py       # Фасад поиска изображений
│   ├── image_relevance_checker.py  # Проверка релевантности фото
│   ├── searxng_client.py     # Клиент для SearXNG (async)
│   ├── publish_policy.py     # Политика публикаций
│   ├── circuit_breaker.py    # Circuit Breaker для RSS
│   ├── rate_limiter.py       # Rate limiting
│   ├── text_utils.py         # DRY-утилиты для текста
│   ├── health.py             # Health-check
│   └── logger.py             # Настройка логирования
├── tests/                    # 437 тестов pytest
│   ├── test_bot_runner.py    # Интеграционные тесты
│   ├── test_ab_testing.py
│   ├── test_leaders_updater.py
│   ├── test_image_extractor.py
│   ├── test_searxng_client.py
│   └── ... (20+ файлов)
├── bot_runner.py             # Основной запуск с polling + scheduler
├── main.py                   # Одноразовый запуск (для cron)
├── config.py                 # Конфигурация и источники
├── translator.py             # Асинхронный перевод
├── start.sh / stop.sh        # Скрипты запуска/остановки
└── requirements.txt          # Зависимости
```

**Итого:** ~9000 строк кода + ~3000 строк тестов.

---

## Установка

### Требования

- Python 3.10+
- 512 MB RAM минимум, 1 GB рекомендуется
- Доступ к Telegram Bot API
- Docker (для SearXNG image search)
- API-ключи (опционально, см. раздел "API-ключи")

### 1. Клонирование и зависимости

```bash
git clone <repo-url>
cd smart_news_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Зависимости:**
| Пакет | Версия | Назначение |
|-------|--------|------------|
| aiogram | 3.6.0 | Telegram Bot API |
| httpx | 0.27.0 | Асинхронный HTTP-клиент |
| feedparser | 6.0.11 | Парсинг RSS |
| apscheduler | 3.10.4 | Планировщик задач |
| beautifulsoup4 | 4.12.3 | HTML-парсинг |
| openai | 1.12.0 | OpenAI-совместимые API |
| python-dotenv | 1.0.1 | Переменные окружения |
| pytest | 7.4.4 | Тестирование |

### 2. SearXNG (self-hosted image search)

```bash
# Запуск SearXNG через Docker
cd searxng
docker-compose up -d

# Проверка
curl http://localhost:8888/search?q=test&categories=images&format=json
```

SearXNG используется для поиска изображений к новостям, когда RSS/OG не дают картинку. Поддерживает Google, Bing, DuckDuckGo image engines.

### 3. Переменные окружения

Создайте файл `.env` в корне проекта:

```env
# ========== Обязательные ==========
# Telegram Bot (получить у @BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL_ID=@your_channel_id

# ========== Опциональные: AI-анализ ==========
# RouterAI (DeepSeek / Kimi) — рекомендуется
ROUTERAI_API_KEY=your_routerai_key
ROUTERAI_MODEL=qwen/qwen3-max

# YandexGPT — fallback если RouterAI недоступен
YANDEX_API_KEY=your_yandex_key
YANDEX_FOLDER_ID=your_folder_id

# ========== Опциональные: Перевод ==========
# Yandex Translate API (для перевода англоязычных новостей)
YANDEX_API_KEY=your_yandex_key  # Можно использовать тот же ключ

# ========== Настройки ==========
LOG_LEVEL=INFO                    # DEBUG | INFO | WARNING | ERROR
REQUEST_TIMEOUT=10                # Таймаут HTTP-запросов (сек)
CACHE_DURATION_DAYS=7             # Срок хранения кэша
PUBLISH_INTERVAL_MINUTES=60       # Интервал сбора RSS (мин)
USER_AGENT=Mozilla/5.0 ...        # User-Agent для RSS-запросов

# ========== SearXNG ==========
SEARXNG_URL=http://localhost:8888

# ========== Webhook (опционально) ==========
# Если задан — используется webhook вместо polling
WEBHOOK_URL=https://your-domain.com/webhook
WEBHOOK_PORT=8080
WEBHOOK_PATH=/webhook
WEBHOOK_SECRET=your_secret_token

# ========== Администратор ==========
ADMIN_TELEGRAM_ID=123456789       # ID админа для команд /post_now и др.
```

### 4. API-ключи

| Сервис | Зачем нужен | Где получить |
|--------|-------------|--------------|
| **Telegram Bot Token** | Отправка постов | [@BotFather](https://t.me/BotFather) |
| **RouterAI API Key** | AI-анализ (DeepSeek/Kimi) | [routerai.net](https://routerai.net) |
| **Yandex API Key** | Fallback AI + Перевод | [Yandex Cloud](https://cloud.yandex.ru) |
| **Yandex Folder ID** | YandexGPT | В консоли Yandex Cloud |

Бот работает и без AI-ключей — в этом случае публикует новости без AI-комментариев.

### 5. Запуск

```bash
# Основной режим: polling + планировщик + команды бота
python bot_runner.py

# Одноразовый запуск (для cron — каждый час)
python main.py

# Через скрипты
./start.sh   # запуск в фоне
./stop.sh    # остановка
```

**Важно:** Используйте `python bot_runner.py` напрямую, без `nohup` обёртки — иначе PID-файл может конфликтовать.

**systemd сервис** (опционально):
```ini
# /etc/systemd/system/smartnews.service
[Unit]
Description=Smart News Bot
After=network.target

[Service]
Type=simple
User=newsbot
WorkingDirectory=/opt/smart_news_bot
ExecStart=/opt/smart_news_bot/venv/bin/python bot_runner.py
Restart=always
RestartSec=10
PIDFile=/tmp/smart_news_bot.pid

[Install]
WantedBy=multi-user.target
```

---

## Команды бота

| Команда | Доступ | Описание |
|---------|--------|----------|
| `/start` | Все | Информация о боте |
| `/help` | Все | Список команд |
| `/post_now` | Админ | Внеочередной сбор и публикация новостей |
| `/stats` | Админ | Статистика кэша, очереди и публикаций |
| `/analytics` | Админ | Глубокая аналитика: посты, реакции, CTR |
| `/top` | Админ | Топ сохранённых новостей |
| `/ab_results` | Админ | Результаты A/B тестирования форматов |
| `/ai_cost` | Админ | Затраты на AI за последние N дней |
| `/health` | Админ | Health-check всех компонентов |

**Inline-кнопки** под каждым постом: 👍 👎 💾 — для сбора реакций аудитории.

---

## Источники новостей

### Русскоязычные
| Источник | Тег | URL |
|----------|-----|-----|
| VC.ru | VC | `vc.ru/rss` |
| N+1 | Science | `nplus1.ru/rss` |
| SecurityLab | Security | `securitylab.ru/rss` |
| Interfax | Interfax | `interfax.ru/rss` |
| RT | RT | `russian.rt.com/rss` |
| RIA | RIA | `ria.ru/rss` |

### Англоязычные
| Источник | Тег | Тематика |
|----------|-----|----------|
| CoinDesk | CoinDesk | Криптовалюты |
| CoinTelegraph | CoinTelegraph | Криптовалюты |
| Investing.com | Investing | Финансы |
| CNBC | CNBC_World | Мировые новости |
| NYT Business | NYT_Business | Бизнес |
| NYT Economy | NYT_Economy | Экономика |
| NYT Tech | NYT_Tech | Технологии |
| NYT DealBook | NYT_DealBook | M&A, инвестиции |

---

## Поиск изображений

Бот использует многоуровневую систему извлечения изображений:

1. **RSS-нативные** — `enclosure`, `media:content`, `media:thumbnail` (с фильтрацией соц-карточек)
2. **Первое фото из статьи** — `<img>` внутри `<article>` / `<main>` / `.article-content`
3. **Open Graph** — `og:image`, `twitter:image` (с фильтрацией соц-карточек RT, RIA, Interfax, Lenta)
4. **SearXNG self-hosted** — поиск по ключевым словам с релевантностью
5. **Fallback** — флаг страны или логотип источника

### Фильтрация нерелевантных изображений
- **Соц-карточки** — блокируются URL-паттерны `/sharing/`, `/social/`, `og-image` и др.
- **Тематическая блокировка** — птицы, пляж, еда, футбол, мемы (когда не в заголовке)
- **Транслитерация** — 100+ слов (молдавия→moldova, израиль→israel, фрг→germany)
- **Минимальный score** — 30 баллов для SearXNG-результатов
- **Проверка по заголовку** — RSS-изображение должно содержать ключевые слова из заголовка

---

## Политика публикаций

| Уровень | Балл | Задержка | Поведение |
|---------|------|----------|-----------|
| 🔴 Red | 8-10 | 0-30 сек | Немедленная публикация |
| 🟠 Orange | 5-7 | 15-30 мин | Публикация с задержкой |
| 🟡 Yellow | 1-4 | 2-4 часа / дайджест | Отложенная публикация или дайджест |

**Факторы оценки:**
- Упоминание мировых лидеров (+2-3 балла)
- Геополитические ключевые слова (+2 балла)
- Финансовые события (+1-2 балла)
- Свежесть (< 1 часа: +1 балл)
- Реакции аудитории на похожие темы (+0.5-1 балл)
- Штраф за рекламный/clickbait контент (−3 балла)

---

## Тесты

```bash
# Запуск всех тестов (437 штук)
pytest tests/ -v

# Быстрый запуск
pytest tests/ -q

# Конкретный модуль
pytest tests/test_bot_runner.py -v
pytest tests/test_leaders_updater.py -v
pytest tests/test_image_extractor.py -v
pytest tests/test_searxng_client.py -v
```

**Покрытие по модулям:**
| Модуль | Тесты | Файл |
|--------|-------|------|
| Bot Runner (интеграционные) | 40 | `test_bot_runner.py` |
| A/B тестирование | 17 | `test_ab_testing.py` |
| Автообновление лидеров | 12 | `test_leaders_updater.py` |
| Circuit Breaker | 10 | `test_circuit_breaker.py` |
| Реакции | 10 | `test_reactions.py` |
| AI провайдеры | 9 | `test_ai_provider.py` |
| Аналитика | 9 | `test_analytics.py` |
| Перевод | 7 | `test_translator.py` |
| AI-сессии | 8 | `test_ai_sessions.py` |
| AI-cost | 8 | `test_ai_cost.py` |
| Rate Limiter | 8 | `test_rate_limiter.py` |
| Публикации | 7 | `test_publish_policy.py` |
| Greylist изображений | 13 | `test_image_greylist.py` |
| Дедупликация | 8 | `test_deduplicator.py` |
| Pydantic модели | 17 | `test_article_model.py` |
| Извлечение изображений | 28 | `test_image_extractor.py` |
| SearXNG клиент | 11 | `test_searxng_client.py` |
| Webhook security | 10 | `test_webhook_security.py` |

---

## Мониторинг

### Логи
- `logs/bot.log` — основной лог
- `logs/errors.log` — ошибки и исключения
- `logs/bot_runner.out` — stdout/stderr запуска

### Метрики
- **AI-cost трекинг** — таблица `ai_usage` в SQLite, алерт при $10/день
- **Health-check** — `utils/health.py` проверяет доступность RSS и API
- **Pidfile** — `/tmp/smart_news_bot.pid`

### Алерты
При превышении дневного бюджета на AI ($10 по умолчанию) бот отправляет уведомление администратору.

---

## Лицензия

MIT
# GitHub Actions CI/CD
