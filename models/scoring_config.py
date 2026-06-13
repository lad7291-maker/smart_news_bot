"""
Pydantic-модель для валидации конфигурации скоринга.
P1-006: Внешняя конфигурация скоринга.
"""

from typing import Dict, List, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator


class ScoringConfig(BaseModel):
    """Валидация scoring.yaml."""

    max_boost_total: float = Field(default=10.0, ge=1.0, le=20.0)
    source_score_range: Tuple[int, int] = Field(default=(1, 10))
    source_scores: Dict[str, float] = Field(default_factory=dict)
    boost_keywords: Dict[str, float] = Field(default_factory=dict)
    penalty_keywords: List[str] = Field(default_factory=list)

    @field_validator("source_score_range")
    @classmethod
    def _validate_range(cls, v: Tuple[int, int]) -> Tuple[int, int]:
        if len(v) != 2:
            raise ValueError("source_score_range должен содержать ровно 2 элемента [min, max]")
        lo, hi = v
        if lo >= hi:
            raise ValueError("source_score_range: min должен быть меньше max")
        if lo < 1 or hi > 20:
            raise ValueError("source_score_range должен быть в пределах [1, 20]")
        return v

    @field_validator("source_scores")
    @classmethod
    def _validate_source_scores(cls, v: Dict[str, float]) -> Dict[str, float]:
        lo, hi = 1, 10  # default range; model_validator runs after field_validators
        for source, score in v.items():
            if not source or not isinstance(source, str):
                raise ValueError(f"Невалидное имя источника: {source!r}")
            if not isinstance(score, (int, float)):
                raise ValueError(
                    f"source_scores['{source}'] должен быть числом, получено {type(score).__name__}"
                )
        return v

    @model_validator(mode="after")
    def _validate_scores_in_range(self) -> "ScoringConfig":
        lo, hi = self.source_score_range
        for source, score in self.source_scores.items():
            if score < lo or score > hi:
                raise ValueError(f"source_scores['{source}'] = {score} вне диапазона [{lo}, {hi}]")
        for word, bonus in self.boost_keywords.items():
            if not isinstance(bonus, (int, float)) or bonus < 0:
                raise ValueError(
                    f"boost_keywords['{word}'] = {bonus} — бонус должен быть неотрицательным числом"
                )
        return self

    @model_validator(mode="after")
    def _validate_boost_cap(self) -> "ScoringConfig":
        if self.boost_keywords:
            max_possible = max(self.boost_keywords.values())
            if max_possible > self.max_boost_total:
                raise ValueError(
                    f"Максимальный boost ({max_possible}) превышает max_boost_total ({self.max_boost_total})"
                )
        return self

    @model_validator(mode="after")
    def _validate_penalty_keywords(self) -> "ScoringConfig":
        seen: set = set()
        for word in self.penalty_keywords:
            if not isinstance(word, str) or not word.strip():
                raise ValueError(
                    f"penalty_keywords содержит пустое или невалидное значение: {word!r}"
                )
            w = word.strip().lower()
            if w in seen:
                raise ValueError(f"penalty_keywords содержит дубликат: '{w}'")
            seen.add(w)
        return self

    def get_source_score(self, source_tag: str, default: float = 2.0) -> float:
        """Безопасное получение базового балла источника."""
        return self.source_scores.get(source_tag, default)

    def get_max_boost(self, text: str) -> float:
        """Максимальный boost из найденных ключевых слов."""
        text_lower = text.lower()
        boost = 0.0
        for word, bonus in self.boost_keywords.items():
            if word.lower() in text_lower:
                boost = max(boost, bonus)
        return boost

    def has_penalty_keyword(self, text: str) -> bool:
        """True, если текст содержит хотя бы одно penalty-слово."""
        text_lower = text.lower()
        for word in self.penalty_keywords:
            if word.lower() in text_lower:
                return True
        return False
