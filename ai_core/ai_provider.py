"""
Универсальный AI-провайдер с RouterAI в приоритете.
RouterAI агрегирует DeepSeek, Kimi и другие модели через единый OpenAI-compatible API.
Fallback: YandexGPT (если RouterAI недоступен).
"""

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiohttp

# Импорт RouterAI провайдера
from ai_core.routerai_provider import RouterAIProvider
from utils.logger import logger


@dataclass
class AIResponse:
    text: str
    provider: str
    tokens_used: int = 0
    cost_usd: float = 0.0


class AIProvider:
    """Унифицированный AI-провайдер: RouterAI → Yandex fallback."""

    PRICING = {
        "routerai/deepseek": {"input": 0.07, "output": 0.28},
        "routerai/kimi": {"input": 0.60, "output": 0.60},
        "yandex": {"input": 0.0, "output": 0.0},
    }

    def __init__(self):
        # Инициализируем RouterAI
        self.routerai = RouterAIProvider()

        # Yandex (fallback)
        self.keys = {
            "yandex": os.getenv("YANDEX_API_KEY"),
        }
        self.yandex_folder = os.getenv("YANDEX_FOLDER_ID")

        self.available = {
            "routerai": self.routerai.available,
            "yandex": bool(self.keys["yandex"] and self.yandex_folder),
        }

        # Приоритет: RouterAI в первую очередь
        priority_str = os.getenv("AI_PROVIDER_PRIORITY", "routerai,yandex")
        self.provider_priority = [
            p.strip()
            for p in priority_str.split(",")
            if p.strip() in self.available and self.available[p.strip()]
        ]

        # Если priority пустой — используем все доступные
        if not self.provider_priority:
            self.provider_priority = [p for p, avail in self.available.items() if avail]

        logger.info(f"AI Providers active: {[p for p, v in self.available.items() if v]}")
        logger.info(f"Provider priority: {self.provider_priority}")
        logger.info(f"RouterAI model: {self.routerai.model}")

    async def analyze_news(self, title: str, summary: str, score: int = 5) -> AIResponse:
        """
        Основной метод анализа.
        Пробует RouterAI, при неудаче — YandexGPT.
        """
        for provider in self.provider_priority:
            if not self.available[provider]:
                logger.debug(f"{provider}: skipped (not available)")
                continue

            try:
                logger.info(f"Using {provider}...")
                if provider == "routerai":
                    resp = await self.routerai.analyze_news(title, summary, score)
                    # Конвертируем RouterAIResponse в наш AIResponse
                    return AIResponse(
                        text=resp.text,
                        provider=resp.provider,
                        tokens_used=resp.tokens_used,
                        cost_usd=resp.cost_usd,
                    )
                elif provider == "yandex":
                    return await self._yandex_analyze(title, summary, score)
            except Exception as e:
                logger.warning(f"{provider} failed: {e}")
                continue

        return AIResponse(
            text="AI analysis temporarily unavailable.",
            provider="none",
            tokens_used=0,
            cost_usd=0.0,
        )

    def _build_prompt(self, title: str, summary: str, score: int) -> str:
        """Строит промпт для модели (перенаправляется в RouterAI)."""
        return self.routerai._build_prompt(title, summary, score)

    async def _make_request(
        self, url: str, headers: Dict, payload: Dict, timeout: int = 30, retries: int = 3
    ) -> Dict:
        """Универсальная отправка POST с retry (для legacy/fallback).
        Использует единую сессию для предотвращения утечек (BUG-002)."""
        session = aiohttp.ClientSession()
        try:
            for attempt in range(1, retries + 1):
                try:
                    async with session.post(
                        url, json=payload, headers=headers, timeout=timeout
                    ) as resp:
                        if resp.status == 429:
                            wait = 2**attempt
                            logger.warning(f"Rate limit (429), retry in {wait}s")
                            await asyncio.sleep(wait)
                            continue
                        resp.raise_for_status()
                        return await resp.json()
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.warning(f"Request failed (attempt {attempt}/{retries}): {e}")
                    if attempt == retries:
                        raise
                    await asyncio.sleep(2**attempt)
        finally:
            await session.close()
        raise Exception("All retries failed")

    async def _yandex_analyze(self, title: str, summary: str, score: int) -> AIResponse:
        """Fallback через YandexGPT."""
        from ai_core.analyzer_yandex import async_analyze_with_yandexgpt

        text = await async_analyze_with_yandexgpt(title, summary, score)
        return AIResponse(text=text, provider="yandex", tokens_used=0, cost_usd=0.0)

    def _clean_text(self, text: str) -> str:
        """Очистка текста."""
        forbidden = ["#", "[", "]", "~", ">", "---", "***", "```"]
        for ch in forbidden:
            text = text.replace(ch, "")
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)


# Глобальный экземпляр
ai_provider = AIProvider()


async def analyze_news(title: str, summary: str, score: int = 5) -> str:
    """Удобная асинхронная обёртка."""
    response = await ai_provider.analyze_news(title, summary, score)
    return response.text


def get_ai_stats() -> Dict[str, Any]:
    """Возвращает статистику о провайдерах."""
    return {
        "available": ai_provider.available,
        "pricing": ai_provider.PRICING,
        "priority": ai_provider.provider_priority,
        "routerai_model": ai_provider.routerai.model if ai_provider.routerai.available else None,
    }
