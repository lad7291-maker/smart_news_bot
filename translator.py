"""
Модуль перевода текста через Yandex Translate API.
Использует переменные окружения: YANDEX_API_KEY, YANDEX_FOLDER_ID.
"""
import os
import httpx
from functools import lru_cache
from typing import Optional
from utils.logger import logger

# Загрузка переменных из .env
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

_translator_available = False

if YANDEX_API_KEY and YANDEX_FOLDER_ID:
    _translator_available = True
    logger.info("✅ Yandex Translator инициализирован (ключ: %s..., папка: %s)", 
                YANDEX_API_KEY[:8], YANDEX_FOLDER_ID[:8])
else:
    logger.warning("⚠️ YANDEX_API_KEY или YANDEX_FOLDER_ID не заданы, перевод отключён")

@lru_cache(maxsize=1000)
def translate_to_russian(text: str) -> Optional[str]:
    """
    Переводит текст на русский язык через Yandex Translate API.
    Кэширует переводы одинаковых текстов.
    """
    if not text or not _translator_available:
        return text

    try:
        url = "https://translate.api.cloud.yandex.net/translate/v2/translate"
        headers = {
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "folderId": YANDEX_FOLDER_ID,
            "texts": [text],
            "targetLanguageCode": "ru"
        }

        with httpx.Client(timeout=10) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            translated = result["translations"][0]["text"]
            logger.debug(f"🌐 Yandex Translate: {text[:30]}... → {translated[:30]}...")
            return translated

    except Exception as e:
        logger.error(f"❌ Ошибка перевода через Яндекс: {e}", exc_info=True)
        return text  # при ошибке возвращаем исходный текст


@lru_cache(maxsize=1000)
def translate_to_english(text: str) -> Optional[str]:
    """
    Переводит текст на английский язык через Yandex Translate API.
    Кэширует переводы одинаковых текстов.
    """
    if not text or not _translator_available:
        return text

    try:
        url = "https://translate.api.cloud.yandex.net/translate/v2/translate"
        headers = {
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "folderId": YANDEX_FOLDER_ID,
            "texts": [text],
            "targetLanguageCode": "en"
        }

        with httpx.Client(timeout=10) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            translated = result["translations"][0]["text"]
            logger.debug(f"🌐 Yandex Translate EN: {text[:30]}... → {translated[:30]}...")
            return translated

    except Exception as e:
        logger.error(f"❌ Ошибка перевода на английский через Яндекс: {e}", exc_info=True)
        return text