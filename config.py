import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ============ Telegram ============
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

    # ============ Yandex API ============
    YANDEX_API_KEY = os.getenv('YANDEX_API_KEY')
    YANDEX_FOLDER_ID = os.getenv('YANDEX_FOLDER_ID')

    # ============ Настройки проекта ============
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', 10))
    USER_AGENT = os.getenv('USER_AGENT', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    CACHE_DURATION_DAYS = int(os.getenv('CACHE_DURATION_DAYS', 7))

    # ============ Webhook (опционально) ============
    WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Если задан — используем webhook вместо polling
    WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', 8080))
    WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/webhook')

    # ============ RSS-ИСТОЧНИКИ (ТОЛЬКО РАБОЧИЕ) ============
    RSS_SOURCES = [
        # ----- РУССКОЯЗЫЧНЫЕ (ПРОВЕРЕННЫЕ) -----
        {'url': 'https://habr.com/ru/rss/articles/?fl=ru', 'tag': 'Habr'},
        {'url': 'https://vc.ru/rss', 'tag': 'VC'},
        {'url': 'https://nplus1.ru/rss', 'tag': 'Science'},
        {'url': 'https://www.securitylab.ru/_services/export/rss/', 'tag': 'Security'},
        {'url': 'https://www.interfax.ru/rss.asp', 'tag': 'Interfax'},
        {'url': 'https://russian.rt.com/rss', 'tag': 'RT'},
        {'url': 'https://ria.ru/export/rss2/index.xml', 'tag': 'RIA'},

        # ----- АНГЛОЯЗЫЧНЫЕ (КРИПТО/ФИНАНСЫ) -----
        {'url': 'https://www.coindesk.com/arc/outboundfeeds/rss/', 'tag': 'CoinDesk'},
        {'url': 'https://www.investing.com/rss/news_1.rss', 'tag': 'Investing'},
        {'url': 'https://cointelegraph.com/rss', 'tag': 'CoinTelegraph'},

        # ----- CNBC (РАБОТАЕТ) -----
        {'url': 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114', 'tag': 'CNBC_World'},

        # ----- NEW YORK TIMES (ВСЕ РАЗДЕЛЫ РАБОТАЮТ) -----
        {'url': 'https://rss.nytimes.com/services/xml/rss/nyt/Business.xml', 'tag': 'NYT_Business'},
        {'url': 'https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml', 'tag': 'NYT_Economy'},
        {'url': 'https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml', 'tag': 'NYT_Tech'},
        {'url': 'https://rss.nytimes.com/services/xml/rss/nyt/Dealbook.xml', 'tag': 'NYT_DealBook'},
    ]

    # ============ ПРЯМЫЕ ИСТОЧНИКИ (ДЛЯ БУДУЩЕГО) ============
    DIRECT_SOURCES = []

    # ============ ПРОМПТЫ ДЛЯ AI-АНАЛИЗА ============
    AI_PROMPTS = {
        'analyze_news': """Ты — старший аналитик хедж-фонда, специализирующийся на AI и алгоритмической торговле.
Проанализируй новость и дай краткую оценку (3-4 предложения) на русском языке:
1. Ключевой смысл
2. Потенциальное влияние на рынок
3. Возможность использования в торговых алгоритмах

Новость: {title}
Текст: {summary}""",
    }

config = Config()