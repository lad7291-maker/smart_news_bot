"""
AI Core модуль для анализа новостей.
Универсальный провайдер с поддержкой Yandex и DeepSeek.
"""
from ai_core.ai_provider import (
    AIProvider,
    analyze_news,
    get_ai_stats,
    AIResponse
)
from ai_core.analyzer_yandex import (
    async_analyze_with_yandexgpt as analyze_with_yandexgpt,
    check_yandex_available
)

__all__ = [
    'AIProvider',
    'analyze_news',
    'get_ai_stats',
    'AIResponse',
    'analyze_with_yandexgpt',
    'check_yandex_available',
]