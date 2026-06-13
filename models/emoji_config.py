"""
Pydantic-модель для валидации конфигурации эмодзи.
P2-001: Рефакторинг _detect_topic_emoji().
"""

from typing import Dict, List

from pydantic import BaseModel, Field, field_validator


class EmojiRule(BaseModel):
    """Одно правило: эмодзи + список ключевых слов."""

    emoji: str = Field(..., min_length=1)
    keywords: List[str] = Field(default_factory=list)

    @field_validator("keywords")
    @classmethod
    def _validate_keywords(cls, v: List[str]) -> List[str]:
        result = []
        seen = set()
        for kw in v:
            if not isinstance(kw, str) or not kw.strip():
                raise ValueError(f"Невалидное keyword: {kw!r}")
            lowered = kw.strip().lower()
            if lowered in seen:
                raise ValueError(f"Дубликат keyword '{lowered}' в правиле emoji")
            seen.add(lowered)
            result.append(lowered)
        return result


class EmojiConfig(BaseModel):
    """Корневая модель emojis.yaml."""

    rules: List[EmojiRule] = Field(default_factory=list)
    source_emoji: Dict[str, str] = Field(default_factory=dict)
    default_emoji: str = Field(default="📰", min_length=1)

    @field_validator("rules")
    @classmethod
    def _validate_rules(cls, v: List[EmojiRule]) -> List[EmojiRule]:
        seen_emojis = set()
        for rule in v:
            if rule.emoji in seen_emojis:
                raise ValueError(f"Дубликат emoji '{rule.emoji}' в правилах")
            seen_emojis.add(rule.emoji)
        return v

    def detect(self, text: str, source: str = "") -> str:
        """
        Определяет эмодзи по тексту и источнику.
        Первое совпадение wins. Fallback на source_emoji → default_emoji.
        """
        text_lower = text.lower()
        for rule in self.rules:
            for kw in rule.keywords:
                if kw in text_lower:
                    return rule.emoji
        return self.source_emoji.get(source, self.default_emoji)
