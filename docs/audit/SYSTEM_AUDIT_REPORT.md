# Системный аудит Smart News Bot

**Дата аудита:** 2026-06-04
**Аудитор:** Principal Software Architect / Lead Backend Engineer
**Объём кодовой базы:** ~5 500 LOC (без тестов), 237 тестов (~2 600 LOC)
**Стек:** Python 3.10+, aiogram 3.6, APScheduler 3.10, SQLite, aiohttp, httpx

---

## 1. Резюме текущего уровня качества

### 1.1 Архитектура

| Критерий | Оценка | Комментарий |
|----------|--------|-------------|
| Модульность | ⚠️ Средняя | Есть разделение по пакетам, но `bot_runner.py` (1 765 LOC) — чистый God Object |
| Ответственность модулей | ⚠️ Средняя | `telegram_bot/`, `ai_core/`, `storage/` выделены, но логика скоринга, фильтрации, планирования всё в `bot_runner.py` |
| Связанность | ⚠️ Высокая | `bot_runner.py` импортирует напрямую ~20 модулей, содержит глобальные переменные (`scheduler`, `_yellow_digest_queue`) |
| Pydantic-модели | ✅ Хорошо | `Article` с валидацией, но используется как `dict` из-за `.get()` / `[]` совместимости |

**Ключевые архитектурные проблемы:**

1. **`bot_runner.py` — God Object (1 765 строк):** содержит логику скоринга, фильтрации, планирования публикаций, inline-клавиатур, callback-обработчиков, health-check интеграции, дайджестов. Это нарушает SRP и делает код практически невозможным для юнит-тестирования в изоляции.
2. **Глобальное состояние:** `scheduler`, `_yellow_digest_queue`, `bot`, `dp`, `parser` — глобальные переменные, что блокирует горизонтальное масштабирование и усложняет тестирование.
3. **Дублирование `bot`/`dp`:** создаются в `telegram_bot/core.py` и повторно в `bot_runner.py` (строка 234).
4. **Синхронный RSS-парсинг в async-контексте:** `asyncio.to_thread(parser.parse_feed, ...)` — корректно, но `feedparser.parse()` внутри делает синхронные HTTP-запросы, а `time.sleep()` в retry-логике блокирует поток (строка 90 `rss_parser.py`).

### 1.2 Асинхронность и производительность

| Критерий | Оценка | Комментарий |
|----------|--------|-------------|
| aiogram 3.x | ✅ Корректно | Используется `Dispatcher`, `DefaultBotProperties`, `ParseMode.HTML` |
| httpx | ✅ Корректно | Переиспользуется в `translator.py` |
| aiohttp | ⚠️ Проблемы | `analyzer_yandex.py` создаёт сессию на каждый запрос (строки 75–81) |
| APScheduler | ⚠️ Проблемы | `AsyncIOScheduler` корректен, но задачи `publish_` накапливаются и очищаются грубо |
| Блокирующие операции | ⚠️ Есть | `time.sleep()` в `rss_parser.py`, `requests.get()` в `image_extractor.py` и `searxng_client.py` |

**Критичные проблемы async:**

- `searxng_client.py` использует синхронный `requests.get()` — вызывается из `find_news_image()` внутри `asyncio.gather()` в `bot_runner.py`, но сам по себе блокирует event loop, если SearXNG медленный.
- `image_extractor.py` — `requests.get()` для парсинга HTML статей, тоже блокирующий.
- `RSSParser.parse_feed()` — `time.sleep(wait)` в retry-логике блокирует worker thread, но не весь loop. Приемлемо, но не идеально.

### 1.3 Надёжность и отказоустойчивость

| Критерий | Оценка | Комментарий |
|----------|--------|-------------|
| Обработка ошибок RSS | ✅ Хорошо | Circuit Breaker + retry + exponential backoff |
| Fallback AI | ✅ Есть | RouterAI → YandexGPT |
| Retry Telegram | ✅ Есть | `_send_with_retry()` с обработкой `FLOOD_WAIT` |
| Health-check | ⚠️ Базовый | Только silence + error count, нет проверки внешних API |
| Graceful shutdown | ✅ Есть | Закрытие сессий, БД, webhook в `finally` |

**Проблемы надёжности:**

1. **Health-check не проверяет внешние зависимости:** нет probe для RouterAI, Yandex Translate, SearXNG, Telegram API.
2. **Circuit Breaker только для RSS:** нет CB для AI-провайдеров, переводчика, SearXNG.
3. **AI fallback возвращает мёртвый текст:** `"AI analysis temporarily unavailable."` — нет сигнала вызывающему коду, что произошла ошибка. Пост публикуется с бесполезным текстом.
4. **Отсутствие timeout на `feedparser.parse()`:** передаётся `request_headers={"timeout": str(self.timeout)}`, но `feedparser` может игнорировать это при некоторых сценариях.

### 1.4 Тесты

| Критерий | Оценка | Комментарий |
|----------|--------|-------------|
| Покрытие ключевых модулей | ✅ Хорошее | analytics, reactions, circuit breaker, rate limiter, publish policy, deduplicator, A/B testing |
| Тесты `bot_runner.py` | ⚠️ Частичные | Только `detect_score`, `filter_article`, `get_delay_for_score` — нет тестов на `publish_single_article`, `job_collect_news`, callback-обработчики |
| Интеграционные тесты | ❌ Нет | Нет end-to-end тестов с моками aiogram Bot |
| Тесты безопасности | ❌ Нет | Нет тестов на проверку admin rights, валидацию входных данных |
| Тесты на блокирующие операции | ❌ Нет | Нет тестов, проверяющих, что нет `requests.get()` в async пути |

**Чего не хватает в тестах:**
- Тесты на `publish_single_article()` (сложно из-за глобальных зависимостей).
- Тесты на webhook-режим.
- Тесты на Storm Mode (бурст публикаций).
- Тесты на concurrent SQLite access.
- Тесты на утечку секретов в логах.

---

## 2. Аудит безопасности

### 2.1 Токены и API-ключи

| Проверка | Результат | Комментарий |
|----------|-----------|-------------|
| Хардкод секретов | ✅ Нет | Все через `os.getenv()` |
| `.env` загрузка | ✅ Есть | `python-dotenv` в `config.py` |
| Логирование ключей | ⚠️ Частично | `translator.py` строка 27–29: логирует первые 8 символов `YANDEX_API_KEY` и `YANDEX_FOLDER_ID` |
| Логирование AI prompt | ✅ Нет | Prompt не логируется целиком |
| Логирование заголовков | ✅ Безопасно | Обрезаются до 40–80 символов |

**Проблема:** `translator.py` логирует `YANDEX_API_KEY[:8]` и `YANDEX_FOLDER_ID[:8]`. Хотя это не полный ключ, первые 8 символов API-ключа снижают энтропию для брутфорса. **Рекомендация:** не логировать ни одного символа ключа.

### 2.2 Веб-хуки

| Проверка | Результат | Комментарий |
|----------|-----------|-------------|
| HTTPS | ⚠️ Зависит от конфигурации | `WEBHOOK_URL` задаётся в `.env`, нет принудительной проверки `https://` |
| Проверка источника запроса | ❌ Нет | Нет проверки `X-Telegram-Bot-Api-Secret-Token`, IP whitelist, или signature |
| Защита от spoofing | ❌ Нет | Любой POST на `/webhook` будет обработан как Update |

**Критично:** webhook endpoint (`handle_webhook`) не проверяет:
- `X-Telegram-Bot-Api-Secret-Token`
- IP-адрес источника (должен быть из диапазона Telegram)
- Content-Type

Это позволяет любому злоумышленнику отправить фейковый Update и, например, вызвать callback-обработчики (хотя admin check защищает большинство команд).

### 2.3 Валидация входящих данных

| Проверка | Результат | Комментарий |
|----------|-----------|-------------|
| RSS-валидация | ⚠️ Частичная | `Article` валидирует `link` и `title`, но `feedparser` может вернуть произвольный HTML |
| HTML-парсинг | ⚠️ Нет защиты | `BeautifulSoup` парсит любой HTML, нет ограничения на размер |
| AI-ответы | ⚠️ Базовая | `_validate_output()` убирает markdown и торговые термины, но не проверяет на инъекции |
| SearXNG-ответы | ⚠️ Нет | `resp.json()` без валидации схемы |
| Пользовательские команды | ✅ Есть | Проверка `ADMIN_TELEGRAM_ID` на всех админ-командах |

**XSS-риск через HTML-разметку:**
- `format_news_post()` использует `ParseMode.HTML`. Заголовок новости (`title`) вставляется напрямую в HTML без экранирования: `<b>{title}</b>`.
- Если RSS-источник вернёт заголовок с HTML-тегами (`<script>`, `<a href="evil">`), они будут переданы в Telegram.
- **Telegram API фильтрует опасные теги**, но это defense in depth — лучше экранировать самостоятельно.

### 2.4 Доступ к админ-командам

| Проверка | Результат |
|----------|-----------|
| `ADMIN_TELEGRAM_ID` | ✅ Проверяется на всех командах и callback-ах |
| Rate limiting на команды | ✅ Есть (`@rate_limit`) |
| Защита от подбора ID | ⚠️ Нет | Логируется попытка доступа, но нет бана после N попыток |

### 2.5 Логи

| Проверка | Результат | Комментарий |
|----------|-----------|-------------|
| Ротация логов | ✅ Есть | `RotatingFileHandler`, 10 МБ, 5 бэкапов |
| Логи ошибок | ✅ Есть | Отдельный `errors.log` |
| Логи токенов | ⚠️ Частично | `translator.py` логирует префикс ключа |
| Логи полных AI-запросов | ✅ Нет | Только title[:40] и метаданные |

---

## 3. Аудит надёжности и эксплуатации

### 3.1 Сценарии отказа

| Сценарий | Оценка защиты | Комментарий |
|----------|---------------|-------------|
| Падение RouterAI | ✅ Fallback на YandexGPT | Но fallback-ответ не сигнализирует об ошибке |
| Падение YandexGPT | ⚠️ Мёртвый текст | `"AI analysis temporarily unavailable."` |
| Недоступность SearXNG | ✅ Fallback-изображение | Флаг или логотип источника |
| Проблемы с SQLite | ⚠️ Частично | `check_same_thread=False` позволяет доступ из разных потоков, но не из разных процессов |
| Сетевые проблемы RSS | ✅ Circuit Breaker | Источник отключается после 3 ошибок |

**SQLite — критичные проблемы:**

1. **Один файл БД, 6+ модулей:** `news_cache.db` используется `CacheManager`, `AnalyticsManager`, `ReactionsManager`, `RateLimiter`, `SourceHealthTracker`, `ABTestingManager`. Все открывают своё соединение с `check_same_thread=False`.
2. **Нет WAL-режима:** SQLite по умолчанию в режиме DELETE journal. При одновременной записи из нескольких потоков возможны `DATABASE IS LOCKED` ошибки.
3. **Рост базы:** нет автоматической очистки старых записей. Таблицы `message_stats`, `delivery_errors`, `user_sessions`, `ab_tests` будут расти бесконечно.
4. **Нет backup-стратегии:** единственный `.db`-файл, нет репликации или периодического бэкапа.

### 3.2 Storm Mode

| Проверка | Результат | Комментарий |
|----------|-----------|-------------|
| Определение шторма | ✅ Есть | 3+ red за час |
| Защита от спама | ⚠️ Частичная | В шторм yellow/orange публикуются с задержкой 3–7 мин, но red — сразу |
| Rate limit Telegram | ✅ Есть | `MAX_POSTS_PER_HOUR = 8`, `_send_with_retry()` обрабатывает `FLOOD_WAIT` |
| Минимальный интервал | ✅ Есть | `MIN_POST_INTERVAL = 20` сек |

**Риск Storm Mode:**
- Если произойдёт крупное событие (например, начало войны, теракт), может быть 5–10 red-новостей за короткое время.
- `job_collect_news()` очищает ВСЕ старые `publish_` задачи (строка 794–798), что может привести к потере отложенных orange/yellow новостей.
- Нет жёсткого ограничения на количество red-новостей подряд.

### 3.3 Rate Limiting

| Проверка | Результат |
|----------|-----------|
| Админ-команды | ✅ 3 вызова за 60 сек |
| Telegram FLOOD_WAIT | ✅ Обрабатывается в `_send_with_retry()` |
| AI API rate limits | ⚠️ Только RouterAI (429 retry) |
| RSS polling | ⚠️ Нет rate limit между источниками (параллельный `asyncio.gather`) |

### 3.4 Circuit Breaker

| Проверка | Результат |
|----------|-----------|
| RSS-источники | ✅ DEGRADED после 3 ошибок, OFFLINE после ещё 3 |
| AI-провайдеры | ❌ Нет |
| Переводчик | ❌ Нет |
| SearXNG | ❌ Нет |

### 3.5 Мониторинг

**Есть:**
- AI-cost tracking ($/день, алерт при $10)
- Delivery stats (sent, delivered, with_image, fallback_images)
- Error stats (FLOOD_WAIT, API errors, network errors)
- DAU/MAU
- User reactions (👍/👎/💾)
- Source health (circuit breaker states)
- Health-check (silence, error rate)

**Не хватает:**
- Latency histogram (p50, p95, p99) по внешним API
- Error rate по провайдерам (RouterAI vs Yandex)
- Queue length (сколько задач в APScheduler)
- Глубина задержек публикаций (сколько yellow новостей ждут > 4 часов)
- Memory usage tracking
- RSS source freshness (когда источник последний раз давал новости)
- A/B test statistical significance (не просто CTR, а p-value)

---

## 4. Аудит продуктовой аналитики и A/B-тестирования

### 4.1 A/B-тестирование

| Проверка | Результат | Комментарий |
|----------|-----------|-------------|
| Сплит-логика | ⚠️ Не 50/50 | Детерминированное распределение по `hashlib.md5(link) % 4` — равномерное, но не адаптивное |
| Перекрёстное загрязнение | ✅ Нет | Один URL → один вариант навсегда |
| Статистическая значимость | ❌ Нет | Нет расчёта p-value, confidence interval, MDE |
| Размер выборки | ⚠️ Нет планирования | Нет power analysis для определения нужного N |
| Метрики | ⚠️ Базовые | CTR (реакции / показы), save rate — но нет времени на прочтение, нет reach |

**Проблема сплит-логики:**
- 4 варианта с равномерным распределением — ок, но нет механизма для раннего останова (early stopping) или победителя (winner selection).
- `get_report_text()` выбирает "лучший CTR", но без статистической значимости это может быть случайность.

### 4.2 Интеграция аналитики в цикл принятия решений

| Проверка | Результат |
|----------|-----------|
| Реакции влияют на score | ✅ `reactions_manager.get_article_score_boost()` добавляет ±0.5 за like/dislike |
| A/B результаты влияют на формат | ❌ Нет — лучший вариант не выбирается автоматически |
| Аналитика влияет на publish policy | ❌ Нет — статичные константы |
| Аналитика влияет на Storm Mode | ❌ Нет |

**Вывод:** аналитика собирается, но не замыкается на автоматическое улучшение продукта. Это "data collection", не "data-driven decisions".

### 4.3 Шкала приоритета (red/orange/yellow)

| Проверка | Результат | Комментарий |
|----------|-----------|-------------|
| Жёсткие константы | ⚠️ Да | `SCORE_DELAYS`, `SOURCE_SCORES`, `BOOST_KEYWORDS` — всё захардкожено в `bot_runner.py` |
| Адаптивность под нишу | ❌ Нет | Для крипто-канала boost на "биткоин" = 5, для финансового — "ставка" = 6. Нет конфигурации без изменения кода |
| Переобучение на прошлые данные | ❌ Нет | Нет ML-модели или даже простого линейного регрессора на реакциях |
| Проверка завышения | ⚠️ Есть риск | `трамп` = +6, `путин` = +6, `санкции` = +7 — при одновременном присутствии нескольких keyword score может запросто достичь 10 из базы 2 |

**Пример завышения:**
- Источник: VC (база 3)
- Заголовок: "Трамп и Путин обсудили санкции против Ирана на фоне войны"
- Boost: max(6, 6, 7, 5, 5) = 7 (берётся максимум, не сумма) → score = 3 + 7 = 10
- Это корректно (максимум), но если добавить `user_prefs` с preferred_topics — ещё +2.

**Проблема:** `boost` берётся как `max()`, а не сумма — это предотвращает переполнение, но `penalty` тоже только -1.0 (один штраф за любое количество penalty keywords). Несбалансировано.

---

## 5. Приоритизированные рекомендации

### P0 — Критично (безопасность, риски потери данных, блокировки)

#### P0-001: Защита webhook от spoofing
- **Что:** Добавить проверку `X-Telegram-Bot-Api-Secret-Token` и/или IP whitelist.
- **Почему:** Любой может отправить фейковый Update на webhook endpoint.
- **Как:**
  - В `config.py` добавить `WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")`.
  - В `handle_webhook()` проверять `request.headers.get("X-Telegram-Bot-Api-Secret-Token") == config.WEBHOOK_SECRET`.
  - Добавить IP whitelist (диапазоны Telegram: `149.154.160.0/20`, `91.108.4.0/22`).
  - Файлы: `bot_runner.py`, `config.py`.

#### P0-002: Экранирование HTML в постах
- **Что:** Экранировать `title`, `summary`, `ai_comment` перед вставкой в HTML-разметку.
- **Почему:** RSS-источники могут содержать HTML-теги в заголовках. Telegram фильтрует `<script>`, но `<a href="evil">` или стили могут пройти.
- **Как:**
  - Использовать `html.escape()` из стандартной библиотеки для `title`, `ai_comment`, `summary` в `format_news_post()`.
  - Файл: `telegram_bot/formatter.py`.

#### P0-003: WAL-режим SQLite + очистка старых данных
- **Что:** Включить WAL для SQLite, добавить периодическую очистку старых записей.
- **Почему:** 6 модулей пишут в одну БД без WAL — риск `DATABASE IS LOCKED` и потери данных. Бесконечный рост таблиц.
- **Как:**
  - В каждом `__init__` SQLite-менеджера выполнять `PRAGMA journal_mode=WAL;`.
  - Добавить `VACUUM` и удаление записей старше 90 дней по расписанию (APScheduler job).
  - Файлы: `storage/cache.py`, `storage/analytics.py`, `storage/reactions.py`, `storage/ab_testing.py`, `utils/circuit_breaker.py`, `utils/rate_limiter.py`.

#### P0-004: Убрать логирование префиксов API-ключей
- **Что:** Не логировать ни одного символа `YANDEX_API_KEY`.
- **Почему:** Снижает энтропию для брутфорса.
- **Как:**
  - В `translator.py` заменить логирование префикса на `"✅ Yandex Translator инициализирован"` без ключей.
  - Файл: `translator.py`.

#### P0-005: Исправить `@lru_cache` на async-функциях
- **Что:** `functools.lru_cache` на `async def` кэширует корутину, не результат.
- **Почему:** При повторном вызове возвращается уже awaitable-объект, что приводит к `RuntimeWarning` или `InvalidStateError`.
- **Как:**
  - Заменить `@lru_cache` на `async_lru` (пакет `async_lru`) или ручной кэш (`dict` с `asyncio.Lock`).
  - Файлы: `ai_core/routerai_provider.py`, `ai_core/analyzer_yandex.py`.

---

### P1 — Важно (архитектура, надёжность, тесты, мониторинг)

#### P1-001: Разделить `bot_runner.py` на модули
- **Что:** Вынести логику скоринга, фильтрации, планирования, UI из `bot_runner.py`.
- **Почему:** God Object блокирует тестирование, ревью и масштабирование.
- **Как:**
  - `scoring.py` — `detect_score()`, `SOURCE_SCORES`, `BOOST_KEYWORDS`, `PENALTY_KEYWORDS`.
  - `filters.py` — `filter_article()`, `is_relevant()`, `is_russian()`, `_is_junk()`, `_is_advertorial()`.
  - `scheduler_jobs.py` — `job_collect_news()`, `publish_single_article()`, `get_delay_for_score()`.
  - `telegram_bot/handlers.py` — все `@dp.message` и `@dp.callback_query` обработчики.
  - `bot_runner.py` оставить только `main()` и инициализацию.

#### P1-002: Заменить синхронные `requests.get()` на `httpx`/`aiohttp`
- **Что:** `image_extractor.py` и `searxng_client.py` используют блокирующий `requests`.
- **Почему:** Блокирует event loop при медленных ответах.
- **Как:**
  - `searxng_client.py` — переписать `search_images()` на `httpx.AsyncClient`.
  - `image_extractor.py` — переписать `extract_image_from_html()` на `httpx.AsyncClient`.
  - Файлы: `utils/searxng_client.py`, `parsers/image_extractor.py`.

#### P1-003: Добавить Circuit Breaker для AI и переводчика
- **Что:** CB для RouterAI, YandexGPT, Yandex Translate.
- **Почему:** Защита от каскадных сбоев и DDoS самому себе при повторных попытках.
- **Как:**
  - Создать `utils/circuit_breaker.py::APICircuitBreaker` (или использовать `pybreaker`).
  - Оборачивать вызовы `analyze_news()`, `translate_to_russian()`.

#### P1-004: Добавить health-check probes для внешних API
- **Что:** Проверять доступность RouterAI, Yandex Translate, SearXNG, Telegram API.
- **Почему:** Сейчас health-check только по internal метрикам (silence, errors).
- **Как:**
  - В `utils/health.py` добавить `async def _check_external_apis()`.
  - Периодически делать lightweight запросы (например, GET к Telegram API `getMe`, HEAD к SearXNG).

#### P1-005: Улучшить тестовое покрытие
- **Что:** Добавить тесты на критичные пути.
- **Почему:** Сейчас нет тестов на `publish_single_article`, webhook, Storm Mode, concurrent SQLite.
- **Как:**
  - `test_publish_single_article.py` — моки для `bot`, `cache_manager`, `analyze_news`, `find_news_image`.
  - `test_webhook_security.py` — проверка secret token, IP whitelist.
  - `test_storm_mode.py` — симуляция 10 red-новостей, проверка rate limits.
  - `test_concurrent_sqlite.py` — 10 потоков пишут одновременно.

#### P1-006: Сделать конфигурацию скоринга внешней
- **Что:** Вынести `SOURCE_SCORES`, `BOOST_KEYWORDS`, `PENALTY_KEYWORDS` в JSON/YAML конфиг.
- **Почему:** Сейчас для смены ниши (финансы → крипто → политика) нужно менять код.
- **Как:**
  - Создать `config/scoring.yaml`.
  - Загружать при старте, валидировать через Pydantic.
  - Добавить hot-reload по сигналу или по расписанию.

---

### P2 — Желательно (рефакторинг, читаемость, новые фичи)

#### P2-001: Рефакторинг `formatter.py`
- **Что:** `_detect_topic_emoji()` — 700 строк if-elif. Заменить на конфигурацию.
- **Почему:** Невозможно поддерживать, легко сломать.
- **Как:**
  - Создать `config/emojis.yaml` со списком `{keywords: ["трамп", "trump"], emoji: "🇺🇸"}`.
  - Загружать и матчить через `any(kw in text for kw in rule.keywords)`.

#### P2-002: Статистическая значимость в A/B-тестах
- **Что:** Добавить расчёт p-value (z-test для пропорций) и confidence intervals.
- **Почему:** Сейчас "лучший CTR" выбирается без понимания, случайность это или нет.
- **Как:**
  - Использовать `statsmodels` или простую реализацию z-test.
  - Добавить в `get_report_text()` флаг "✅ Статистически значимо" или "⚠️ Недостаточно данных".

#### P2-003: Автоматический winner selection в A/B
- **Что:** Если вариант статистически значимо лучше в течение N дней — автоматически повышать его долю (multi-armed bandit) или фиксировать.
- **Почему:** Закрывает loop data-driven optimization.
- **Как:**
  - Добавить `ab_testing_manager.get_winner_variant(min_days=7, confidence=0.95)`.
  - Если winner определён — использовать его для 80% новых постов, 20% — остальные для exploration.

#### P2-004: Метрики latency и queue depth
- **Что:** Prometheus-совместимые метрики или простой `/metrics` endpoint.
- **Почему:** Сейчас нет visibility на latency внешних API.
- **Как:**
  - Добавить `utils/metrics.py` с простыми histogram (в памяти, сбрасываемые при запросе).
  - Собирать: `rss_parse_latency`, `ai_analysis_latency`, `image_search_latency`, `telegram_send_latency`, `scheduler_queue_length`.

#### P2-005: Graceful degradation при недоступности AI
- **Что:** Если AI недоступен — использовать эвристический summary вместо `"AI analysis temporarily unavailable."`.
- **Почему:** Пост с мёртвым текстом — плохой UX.
- **Как:**
  - В `publish_single_article()` при `ai_comment == "AI analysis temporarily unavailable."` использовать `article["summary"][:300]` как fallback.

#### P2-006: Оптимизация памяти `_recent_publishes`
- **Что:** In-memory список `_recent_publishes` в `publish_policy.py` не ограничен.
- **Почему:** При длительной работе и частых публикациях список растёт до 2 часов записей.
- **Как:**
  - `_cleanup_old_records()` вызывается при каждой записи, но при 100 публикациях/час список будет ~200 элементов. Это ок, но лучше использовать `collections.deque` с maxlen.

#### P2-007: Удалить мёртвый код
- **Что:** `ai_core/analyzer.py` (0 байт), `ai_provider.py::_make_request()` (не используется), `_build_prompt()` в `ai_provider.py` (делегирует в RouterAI).
- **Почему:** Мусор в кодовой базе.
- **Как:** Удалить файлы/методы, проверить тесты.

---

## 6. Итоговая матрица рисков

| Риск | Вероятность | Влияние | Приоритет |
|------|-------------|---------|-----------|
| Spoofing webhook | Средняя | Высокое | P0 |
| XSS через RSS заголовки | Низкая | Среднее | P0 |
| SQLite lock / потеря данных | Средняя | Высокое | P0 |
| Утечка API-ключей в логах | Низкая | Высокое | P0 |
| `@lru_cache` на async — баги | Средняя | Среднее | P0 |
| God Object `bot_runner.py` | Высокая | Среднее | P1 |
| Блокирующие `requests.get()` | Средняя | Среднее | P1 |
| Нет CB для AI/переводчика | Средняя | Среднее | P1 |
| Нет тестов на критичные пути | Высокая | Среднее | P1 |
| Жёсткие константы скоринга | Высокая | Низкое | P1 |
| A/B без стат. значимости | Высокая | Низкое | P2 |
| Рост SQLite без очистки | Высокая | Среднее | P0/P1 |

---

*Отчёт подготовлен на основе анализа исходного кода, тестов и конфигурации проекта Smart News Bot.*
