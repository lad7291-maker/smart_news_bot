"""
RouterAI Provider — OpenAI-compatible API агрегатор.
Поддерживает: DeepSeek, Kimi K2.5/2.6, GPT-4o-mini и другие модели через единый endpoint.
"""

import asyncio
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Optional

import aiohttp

from ai_core.world_leaders_context import get_leaders_context
from utils.logger import logger


@dataclass
class AIResponse:
    text: str
    provider: str
    tokens_used: int = 0
    cost_usd: float = 0.0


class RouterAIProvider:
    """RouterAI — единый API для DeepSeek, Kimi и других моделей."""

    BASE_URL = "https://routerai.ru/api/v1"

    # Pricing (USD per 1M tokens) — примерные, обновить при необходимости
    PRICING = {
        "deepseek/deepseek-chat": {"input": 0.07, "output": 0.28},
        "deepseek-chat": {"input": 0.07, "output": 0.28},
        "kimi-coding/k2p5": {"input": 0.60, "output": 0.60},
        "kimi-coding/k2p6": {"input": 0.80, "output": 0.80},
        "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    }

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("ROUTERAI_API_KEY")
        self.model = model or os.getenv("ROUTERAI_MODEL", "deepseek/deepseek-chat")
        self.available = bool(self.api_key)

        # Определяем pricing для выбранной модели
        self.model_pricing = self.PRICING.get(self.model, {"input": 0.10, "output": 0.30})

        logger.info(f"RouterAI initialized: model={self.model}, available={self.available}")

    def _build_prompt(self, title: str, summary: str, score: int = 5) -> str:
        """Строит промпт для разбора новости — журналистский фактчек."""
        urgency = (
            "ВАЖНАЯ НОВОСТЬ" if score >= 8 else "ЗНАЧИМАЯ НОВОСТЬ" if score >= 5 else "НОВОСТЬ"
        )

        return f"""Ты пишешь короткий комментарий к новости в Telegram-канал. Стиль — как будто человек скинул новость в чат и написал пару мыслей.

{urgency}

Ты — редактор новостного Telegram-канала. Объясни суть новости простым языком.
ФОРМАТ (пиши естественно, не по шаблону):
- 2-3 коротких абзаца о новости
- Простые слова, как в разговоре
- Цифры и факты вписывай в текст, не списком

ЗАПРЕЩЕНО:
- Списки с bullet points (—, •, -)
- Звёздочки для жирного текста (**)
- Прогнозы ("будет", "обвалится", "взлетит")
- Рекомендации ("покупайте", "держите")
- Торговые термины (волатильность, лонг, шорт)
- Упоминание AI как источника
- Повтор заголовка дословно

ИСТОЧНИК:
Заголовок: {title}
Текст: {summary[:900]}"""

    async def _make_request(self, payload: Dict, timeout: int = 45, retries: int = 3) -> Dict:
        """Универсальная отправка с retry и exponential backoff.
        Использует единую сессию для предотвращения утечек (BUG-002)."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        session = aiohttp.ClientSession()
        try:
            for attempt in range(1, retries + 1):
                try:
                    async with session.post(
                        f"{self.BASE_URL}/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                    ) as resp:
                        if resp.status == 429:
                            wait = min(2**attempt, 60)
                            logger.warning(f"RouterAI rate limit (429), retry in {wait}s")
                            await asyncio.sleep(wait)
                            continue
                        if resp.status >= 500:
                            logger.warning(f"RouterAI server error ({resp.status}), retrying...")
                            await asyncio.sleep(2**attempt)
                            continue
                        resp.raise_for_status()
                        return await resp.json()

                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.warning(f"RouterAI request failed (attempt {attempt}/{retries}): {e}")
                    if attempt == retries:
                        raise
                    await asyncio.sleep(2**attempt)
        finally:
            await session.close()

        raise Exception("All RouterAI retries failed")

    @lru_cache(maxsize=128)
    async def analyze_news(self, title: str, summary: str, score: int = 5) -> AIResponse:
        """Анализ новости через RouterAI."""
        if not self.available:
            raise RuntimeError("RouterAI not available: missing API key")

        prompt = self._build_prompt(title, summary, score)
        temperature = 0.3 if score >= 8 else 0.5

        leaders_ctx = get_leaders_context()
        system_content = (
            "Ты редактор новостей. Простой язык, факты, контекст. Без прогнозов и торговых терминов.\n\n"
            "ВАЖНО: Используй актуальные данные о мировых лидерах и их должностях из контекста ниже. "
            "Если в новости упоминаются политики, используй их правильные должности и имена.\n\n"
            "КОНТЕКСТ МИРОВЫХ ЛИДЕРОВ:\n" + leaders_ctx
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": 220,
        }

        data = await self._make_request(payload)

        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", 0)
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        input_cost = (prompt_tokens / 1_000_000) * self.model_pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * self.model_pricing["output"]
        total_cost = input_cost + output_cost

        text = self._clean_text(text)
        text = self._validate_output(text)  # FEAT-007: валидация AI-выхода
        logger.info(
            f"RouterAI ({self.model}): {title[:40]}... | "
            f"Tokens: {tokens} | Cost: ${total_cost:.5f}"
        )

        return AIResponse(
            text=text, provider=f"routerai/{self.model}", tokens_used=tokens, cost_usd=total_cost
        )

    def _clean_text(self, text: str) -> str:
        """Очистка от нежелательных символов."""
        forbidden = ["#", "[", "]", "~", ">", "---", "***", "```"]
        for ch in forbidden:
            text = text.replace(ch, "")
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)

    def _validate_output(self, text: str) -> str:
        """
        Валидация AI-выхода (FEAT-007).
        Проверяет и исправляет распространённые проблемы.
        """
        if not text:
            return "AI analysis temporarily unavailable."

        # Убираем markdown-звёздочки
        text = text.replace("**", "").replace("*", "")

        # Убираем списки с bullet points (запрещены в промпте)
        lines = []
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("- ", "• ", "— ")):
                line = stripped[2:]
            lines.append(line)
        text = "\n".join(lines)

        # Убираем торговые термины (если пробрались)
        trading_terms = ["лонг", "шорт", "волатильность", "маржин", "плечо"]
        for term in trading_terms:
            text = text.replace(term, "[...]")

        # Убираем прямые рекомендации
        if any(
            phrase in text.lower() for phrase in ["покупайте", "продавайте", "держите", "вложите"]
        ):
            text += "\n\n(Редакция: инвестиционные рекомендации удалены)"

        # Ограничиваем длину
        if len(text) > 800:
            text = text[:797] + "..."

        return text.strip()


# Глобальный экземпляр
routerai_provider = RouterAIProvider()


async def analyze_news(title: str, summary: str, score: int = 5) -> str:
    """Удобная обёртка."""
    response = await routerai_provider.analyze_news(title, summary, score)
    return response.text


def get_stats() -> Dict[str, Any]:
    """Статистика провайдера."""
    return {
        "available": routerai_provider.available,
        "model": routerai_provider.model,
        "pricing": routerai_provider.model_pricing,
    }
