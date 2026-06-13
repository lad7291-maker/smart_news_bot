"""
LLM Image Judge — гибридный подбор изображений для новостей.

Логика:
1. score >= 65 — высокая уверенность, публикуем сразу без LLM
2. 50 <= score < 65 — спорный случай, LLM с 1 кандидатом + альтернативы
3. 30 <= score < 50 — формируем список кандидатов (текущий + SearXNG + fallback)
4. score < 30 — отбрасываем, ищем через SearXNG

Использует RouterAI (qwen/qwen3-max) — дешёвая и быстрая модель для классификации.
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import aiohttp

from utils.logger import logger


@dataclass
class ImageCandidate:
    """Кандидат-изображение для оценки."""

    url: str
    score: int = 0
    source: str = "unknown"  # rss, article_img, og_image, searxng, fallback
    title: str = ""
    alt: str = ""
    width: int = 0
    height: int = 0
    page_host: str = ""
    engine: Optional[str] = None  # для searxng
    is_social_card: bool = False
    is_logo: bool = False
    is_flag: bool = False
    is_meme: bool = False
    unsafe_flags: List[str] = field(default_factory=list)
    detected_labels: List[str] = field(default_factory=list)


@dataclass
class JudgeResult:
    """Результат оценки LLM."""

    selected_url: Optional[str]
    reason: str
    score: int
    source: str
    llm_used: bool = False
    cost_usd: float = 0.0
    debug: Dict[str, Any] = field(default_factory=dict)


class ImageJudge:
    """LLM-фоторедактор для финального выбора изображения. Singleton."""

    BASE_URL = "https://routerai.ru/api/v1"
    DEFAULT_MODEL = "qwen/qwen3-max"
    PRICING = {"input": 0.10, "output": 0.30}

    _instance: Optional["ImageJudge"] = None
    _initialized = False

    def __new__(cls, api_key: Optional[str] = None, model: Optional[str] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        # Предотвращаем повторную инициализацию (кроме явных параметров для тестов)
        if ImageJudge._initialized and api_key is None and model is None:
            return

        self.api_key = api_key or os.getenv("ROUTERAI_API_KEY")
        self.model = model or os.getenv("IMAGE_JUDGE_MODEL", self.DEFAULT_MODEL)
        self.available = bool(self.api_key)
        self._session: Optional[aiohttp.ClientSession] = None

        ImageJudge._initialized = True
        logger.info(f"ImageJudge initialized: model={self.model}, available={self.available}")

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Закрывает HTTP-сессию."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def __del__(self):
        """Деструктор — пытается закрыть сессию."""
        if self._session and not self._session.closed:
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._session.close())
                else:
                    loop.run_until_complete(self._session.close())
            except Exception:
                pass  # Event loop может быть уже закрыт

    def _build_prompt(
        self,
        article_title: str,
        article_summary: str,
        article_categories: List[str],
        candidates: List[ImageCandidate],
    ) -> str:
        """Строит промпт для LLM-фоторедактора."""

        candidates_json = []
        for i, c in enumerate(candidates):
            candidates_json.append(
                {
                    "index": i,
                    "url": c.url,
                    "source": c.source,
                    "title": c.title,
                    "alt": c.alt,
                    "width": c.width,
                    "height": c.height,
                    "page_host": c.page_host,
                    "base_score": c.score,
                    "is_social_card": c.is_social_card,
                    "is_logo": c.is_logo,
                    "is_flag": c.is_flag,
                    "is_meme": c.is_meme,
                    "unsafe_flags": c.unsafe_flags,
                    "detected_labels": c.detected_labels,
                }
            )

        prompt = f"""Ты — LLM-фоторедактор новостного агентства. Выбери ОДНО лучшее изображение для новости или честно скажи, что безопасного и релевантного изображения нет.

Ориентиры как в крупных редакциях (BBC, Getty):
- Картинка не должна вводить в заблуждение относительно сути новости
- Никаких рекламных баннеров, мемов, кликбейтных стоков без прямой связи с текстом
- Предпочтение реальным фото, логотипам, картам, понятным объектам по теме
- Горизонтальный формат, близкий к 16:9, достаточное разрешение (не маленькие пиксели)

НОВОСТЬ:
Заголовок: {article_title}
Содержание: {article_summary[:500]}
Категории: {', '.join(article_categories)}

КАНДИДАТЫ:
{json.dumps(candidates_json, ensure_ascii=False, indent=2)}

РЕДАКЦИОННЫЕ ПРАВИЛА:

1. Смысловая релевантность:
   - Картинка должна быть прямо связана с тем, что в заголовке: люди, компании, страны, объекты
   - ВАЖНО: метаданные (title, alt, detected_labels, width, height) могут отсутствовать. Это НЕ основание для отказа.
     Оценивай по URL и source домену — новостные фото редко имеют метаданные. Если URL содержит имя персоны/страны/темы — это релевантно. Если домен — надёжный новостной (bbc, cnn, interfax, tass, ria) — считай релевантным.
     В этом случае оценивай по URL и source домена — многие новостные фото не имеют метаданных.
   - Общие стоки (рукопожатия, абстрактные монетки) — слабые кандидаты

2. Тип новости → тип картинки:
   - POLITICS/WAR: реальные фото лидеров, официальные здания, карты региона
   - ECONOMY/CRYPTO: логотипы компаний/бирж, офисы, графики, биржевые залы
   - TECH: логотипы, дата-центры, устройства, интерфейсы
   - SCIENCE: лаборатории, приборы, визуализации
   - INCIDENTS: нейтральные виды, техника, карты (избегай шок-контента)

3. Что отбрасывать:
   - is_social_card — шеринговые баннеры
   - is_meme — мемы/комиксы
   - Рекламные баннеры, промо с текстом
   - Нерелевантные стоки: пляжи, еда, птицы, котики, футбол
   - Очень маленькие: width < 600 ИЛИ height < 400
   - Насилие/кровь в unsafe_flags, если есть альтернатива

4. Этические ограничения:
   - Не ассоциируй случайных людей с преступлениями
   - Избегай стереотипных образов
   - При сомнении — нейтральная картинка (логотип, здание, карта)

5. Формат:
   - Горизонтальный, близкий к 16:9 или 4:3
   - При равной релевантности: большее разрешение, чистая композиция

АЛГОРИТМ:
1) Для каждого кандидата: final_score = base_score + релевантность − штрафы
2) Отфильтруй final_score < 30
3) Выбери максимальный
4) Если нет подходящих — отказ

ФОРМАТ ОТВЕТА (СТРОГИЙ JSON БЕЗ ДОПОЛНИТЕЛЬНОГО ТЕКСТА):

{{
  "selected": {{
    "url": "<string or null>",
    "score": <0-100>,
    "source": "<source или 'none'>",
    "reason": "<1-3 предложения>"
  }},
  "debug": {{
    "article_topic": "<главная тема>",
    "top_candidates": [
      {{
        "url": "<url>",
        "final_score": <число>,
        "matched_entities": ["<entity1>"],
        "penalties": ["<reason1>"]
      }}
    ]
  }}
}}

Если нет подходящих: url=null, source="none", reason="Отказ: ..."
Отвечай ТОЛЬКО JSON."""
        return prompt

    async def judge(
        self,
        article_title: str,
        article_summary: str,
        candidates: List[ImageCandidate],
        article_categories: Optional[List[str]] = None,
    ) -> JudgeResult:
        """
        Вызывает LLM для финального выбора изображения.

        Returns:
            JudgeResult с выбранным URL или None
        """
        if not self.available:
            logger.debug("ImageJudge: LLM недоступен (нет API ключа)")
            return JudgeResult(
                selected_url=None,
                reason="LLM judge недоступен",
                score=0,
                source="none",
                llm_used=False,
            )

        if not candidates:
            return JudgeResult(
                selected_url=None,
                reason="Нет кандидатов для оценки",
                score=0,
                source="none",
                llm_used=False,
            )

        categories = article_categories or []
        prompt = self._build_prompt(article_title, article_summary, categories, candidates)

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Ты фоторедактор новостного агентства. Отвечай только JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 400,
        }

        start = time.time()
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            async with self.session.post(
                f"{self.BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)

            cost = (prompt_tokens / 1_000_000) * self.PRICING["input"] + (
                completion_tokens / 1_000_000
            ) * self.PRICING["output"]

            # Парсим JSON
            result = self._parse_response(text)

            selected = result.get("selected", {})
            selected_url = selected.get("url")
            reason = selected.get("reason", "Нет объяснения")
            score = selected.get("score", 0)
            source = selected.get("source", "none")
            debug = result.get("debug", {})

            if not selected_url or selected_url == "null":
                logger.info(f"🤖 ImageJudge: отказ — {reason} (cost=${cost:.5f})")
                return JudgeResult(
                    selected_url=None,
                    reason=reason,
                    score=score,
                    source="none",
                    llm_used=True,
                    cost_usd=cost,
                    debug=debug,
                )

            logger.info(
                f"🤖 ImageJudge выбрал (score={score}) "
                f"из {len(candidates)} кандидатов: {selected_url[:60]}... "
                f"(cost=${cost:.5f}, time={time.time()-start:.1f}s)"
            )

            return JudgeResult(
                selected_url=selected_url,
                reason=reason,
                score=score,
                source=source,
                llm_used=True,
                cost_usd=cost,
                debug=debug,
            )

        except Exception as e:
            logger.warning(f"ImageJudge failed: {e}")
            return JudgeResult(
                selected_url=None,
                reason=f"LLM ошибка: {e}",
                score=0,
                source="none",
                llm_used=True,
            )

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Парсит JSON-ответ LLM. Устойчив к markdown и лишнему тексту."""
        original = text.strip()

        # 1. Убираем markdown code blocks
        text = original
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        # 2. Пробуем распарсить как есть
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 3. Ищем JSON объект в тексте (между первой { и последней })
        import re

        # Ищем сбалансированные фигурные скобки
        start = text.find("{")
        if start == -1:
            logger.warning(f"ImageJudge: не найден JSON в ответе: {original[:200]}...")
            return self._parse_error_result()

        # Находим парную закрывающую скобку
        depth = 0
        end = start
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        json_str = text[start:end]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # 4. Пробуем исправить типичные ошибки LLM
        # Убираем trailing commas (повторяем для вложенных)
        for _ in range(3):
            new_str = re.sub(r",(\s*[}\]])", r"\1", json_str)
            if new_str == json_str:
                break
            json_str = new_str

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # 5. Пробуем найти просто объект с selected
        selected_match = re.search(r'"selected"\s*:\s*\{[^{}]*\}', text, re.DOTALL)
        if selected_match:
            try:
                wrapped = "{" + selected_match.group() + "}"
                return json.loads(wrapped)
            except:
                pass

        logger.warning(f"ImageJudge: не удалось распарсить JSON: {original[:300]}...")
        return self._parse_error_result()

    def _parse_error_result(self) -> Dict[str, Any]:
        """Результат при ошибке парсинга."""
        return {
            "selected": {
                "url": None,
                "score": 0,
                "source": "none",
                "reason": "Ошибка парсинга LLM-ответа",
            },
            "debug": {"article_topic": "", "top_candidates": []},
        }


# Глобальный экземпляр
image_judge = ImageJudge()


async def judge_images(
    article_title: str,
    article_summary: str,
    candidates: List[ImageCandidate],
    article_categories: Optional[List[str]] = None,
) -> JudgeResult:
    """Удобная обёртка для вызова ImageJudge."""
    return await image_judge.judge(article_title, article_summary, candidates, article_categories)
