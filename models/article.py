"""
Pydantic-модель статьи для валидации и типизации.
Заменяет dict[str, Any] на строго типизированную структуру.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Self

from pydantic import BaseModel, Field, field_validator, model_validator


class Article(BaseModel):
    """Модель новостной статьи с валидацией полей."""

    model_config = {"extra": "allow", "populate_by_name": True}

    title: str = Field(..., min_length=1, description="Заголовок новости")
    link: str = Field(..., description="URL статьи")
    summary: str = Field(default="", description="Краткое содержание")
    source: str = Field(default="News", description="Тег источника")
    published: datetime = Field(default_factory=datetime.now, description="Дата публикации")
    type: str = Field(default="rss", description="Тип источника")

    # Поля, добавляемые после парсинга
    source_tag: Optional[str] = Field(default=None, description="Тег источника (дубль source)")
    score: Optional[int] = Field(default=None, ge=1, le=10, description="Оценка важности 1-10")
    ai_comment: Optional[str] = Field(default=None, description="AI-комментарий")
    image_url: Optional[str] = Field(default=None, description="URL изображения")
    image_is_fallback: bool = Field(default=False, description="Fallback-изображение")
    image_source: Optional[str] = Field(default=None, description="Источник изображения")
    translated: bool = Field(default=False, description="Была ли переведена")

    @field_validator("link")
    @classmethod
    def _validate_link(cls, v: str) -> str:
        if not v:
            return v
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"link должен быть HTTP URL, получено: {v!r}")
        return v

    @field_validator("title")
    @classmethod
    def _validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title не может быть пустым")
        return v

    @model_validator(mode="after")
    def _sync_source_tag(self) -> Self:
        """source_tag синхронизируется с source если не задан."""
        if self.source_tag is None:
            self.source_tag = self.source
        return self

    # ── Удобные свойства ──

    @property
    def display_title(self) -> str:
        """Заголовок для отображения (обрезанный)."""
        return self.title[:120]

    @property
    def has_image(self) -> bool:
        """Есть ли изображение у статьи."""
        return self.image_url is not None and len(self.image_url) > 0

    @property
    def level(self) -> str:
        """Уровень публикации по score."""
        if self.score is None:
            return "unknown"
        if self.score >= 9:
            return "red"
        elif self.score >= 7:
            return "orange"
        return "yellow"

    # ── Фабричные методы ──

    @classmethod
    async def from_rss_entry(cls, entry: Any, source_tag: str) -> Self:
        """Создаёт Article из записи feedparser (async)."""
        title = cls._clean_text(entry.get("title", "Без заголовка"))
        link = entry.get("link", "")
        summary = cls._clean_text(entry.get("summary", entry.get("description", "")))
        published = cls._extract_published_date(entry)

        # Извлекаем изображение с оценкой релевантности
        image_url = None
        image_source = None
        image_score = 0
        try:
            from parsers.image_extractor import extract_image_with_score

            result = await extract_image_with_score(entry, link, title)
            if result:
                image_url, image_score, image_source = result
        except Exception:
            pass

        return cls(
            title=title,
            link=link,
            summary=summary,
            source=source_tag,
            published=published,
            type="rss",
            image_url=image_url,
            image_source=image_source,
            image_score=image_score,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Self:
        """Создаёт Article из dict (для обратной совместимости)."""
        # published может быть datetime или строка
        published = data.get("published")
        if isinstance(published, str):
            try:
                published = datetime.fromisoformat(published)
            except ValueError:
                published = datetime.now()
        elif not isinstance(published, datetime):
            published = datetime.now()

        # Фильтруем только известные поля
        known = {
            "title",
            "link",
            "summary",
            "source",
            "published",
            "type",
            "source_tag",
            "score",
            "ai_comment",
            "image_url",
            "image_is_fallback",
            "image_source",
            "translated",
        }
        kwargs = {k: v for k, v in data.items() if k in known}
        kwargs["published"] = published
        return cls(**kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """Сериализует Article в dict (для обратной совместимости)."""
        return self.model_dump(mode="json")

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like .get() для обратной совместимости."""
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        """Dict-like [] доступ для обратной совместимости."""
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Dict-like [] присваивание для обратной совместимости."""
        setattr(self, key, value)

    # ── Внутренние утилиты ──

    @staticmethod
    def _clean_text(text: str) -> str:
        """Очищает текст от HTML и лишних пробелов."""
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", "", text)
        text = " ".join(text.split())
        return text[:500]

    @staticmethod
    def _extract_published_date(entry: Any) -> datetime:
        """Извлекает дату публикации из записи RSS."""
        for attr in ("published_parsed", "updated_parsed", "created_parsed"):
            if hasattr(entry, attr):
                val = getattr(entry, attr)
                # MagicMock может вернуть callable; feedparser возвращает tuple
                if val is not None and not callable(val):
                    try:
                        return datetime(*val[:6])
                    except (TypeError, ValueError):
                        pass
        return datetime.now()
