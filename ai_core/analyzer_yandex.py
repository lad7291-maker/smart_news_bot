"""
YandexGPT fallback-провайдер (асинхронная версия).
"""

import os

import aiohttp

from ai_core.world_leaders_context import get_leaders_context
from utils.logger import logger

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

_available = bool(YANDEX_API_KEY and YANDEX_FOLDER_ID)


def check_yandex_available() -> bool:
    """Проверяет доступность YandexGPT"""
    return _available


# MEM-FIX: lru_cache убран — кэшировал coroutine-объекты → RuntimeError на повторном вызове
async def async_analyze_with_yandexgpt(title: str, summary: str, score: int = 5) -> str:
    """
    Асинхронный вызов YandexGPT с кэшированием.
    """
    if not _available:
        logger.warning("YandexGPT не настроен")
        return "⚠️ AI-анализ не настроен."

    urgency = "🔴 КРИТИЧНО" if score >= 8 else "🟡 ВАЖНО" if score >= 5 else "🟢 ОБЗОР"

    prompt = f"""Ты — аналитик крипто-канала. {urgency} | Важность: {score}/10

ЗАПРЕЩЕНЫ: # [ ] ` ~ > (можно использовать * и _ для форматирования)
Максимум 3 эмодзи.

СТРУКТУРА:
Суть: 3-5 предложений о событии
Влияние: На рынок 24-48ч
Инсайт: Для трейдеров
Вопрос: Подписчикам
Хештеги: 3-5 штук

Заголовок: {title}
Текст: {summary[:700]}"""

    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}

    # Пробуем модели по порядку
    models = ["yandexgpt", "yandexgpt-lite"]
    last_error = None

    for model in models:
        try:
            leaders_ctx = get_leaders_context()
            system_content = (
                "Трейдер-аналитик. Кратко, по делу.\n\n"
                "ВАЖНО: Используй актуальные данные о мировых лидерах и их должностях. "
                "Если в новости упоминаются политики, используй их правильные должности и имена.\n\n"
                "КОНТЕКСТ МИРОВЫХ ЛИДЕРОВ:\n" + leaders_ctx
            )
            payload = {
                "modelUri": f"gpt://{YANDEX_FOLDER_ID}/{model}",
                "completionOptions": {"stream": False, "temperature": 0.3, "maxTokens": 400},
                "messages": [
                    {"role": "system", "text": system_content},
                    {"role": "user", "text": prompt},
                ],
            }

            session = aiohttp.ClientSession()
            try:
                async with session.post(url, json=payload, headers=headers, timeout=20) as resp:
                    resp.raise_for_status()
                    result = await resp.json()
            finally:
                await session.close()

            comment = result["result"]["alternatives"][0]["message"]["text"]

            # Очистка: убираем только запрещённые символы, разрешаем * и _
            forbidden = ["#", "[", "]", "`", "~", ">"]
            for ch in forbidden:
                comment = comment.replace(ch, "")

            # Убираем лишние пустые строки
            lines = [line.strip() for line in comment.split("\n") if line.strip()]
            result_text = "\n".join(lines)

            logger.info(f"YandexGPT ({model}): {title[:40]}...")
            return result_text

        except Exception as e:
            logger.warning(f"YandexGPT {model} failed: {e}")
            last_error = e
            continue

    logger.error(f"YandexGPT error: {last_error}")
    return "🧠 Анализ временно недоступен."
