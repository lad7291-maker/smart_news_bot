"""
Тесты для P1-006: Внешняя конфигурация скоринга.

Покрывают:
- Валидацию ScoringConfig (Pydantic)
- Загрузчик ScoringConfigLoader (YAML, fallback, hot-reload)
- Интеграцию core/scoring.py с внешним конфигом
"""

import os
import signal
import tempfile
from pathlib import Path

import pytest
import yaml

from core.scoring import detect_score, get_delay_for_score
from core.scoring_config_loader import (
    DEFAULT_CONFIG,
    ScoringConfigLoader,
    get_scoring_config,
    get_scoring_loader,
)
from models.scoring_config import ScoringConfig

# =====================================================================
# ScoringConfig (Pydantic) validation
# =====================================================================


class TestScoringConfigValidation:
    def test_default_config_valid(self):
        """DEFAULT_CONFIG должен проходить валидацию."""
        cfg = ScoringConfig(**DEFAULT_CONFIG.model_dump())
        assert cfg.max_boost_total == 10.0
        assert cfg.source_score_range == (1, 10)
        assert "Interfax" in cfg.source_scores
        assert "трамп" in cfg.boost_keywords

    def test_source_score_range_must_have_two_elements(self):
        with pytest.raises(ValueError):
            ScoringConfig(source_score_range=(1,))

    def test_source_score_range_min_lt_max(self):
        with pytest.raises(ValueError):
            ScoringConfig(source_score_range=(10, 5))

    def test_source_score_range_within_bounds(self):
        with pytest.raises(ValueError):
            ScoringConfig(source_score_range=(0, 10))
        with pytest.raises(ValueError):
            ScoringConfig(source_score_range=(1, 25))

    def test_source_score_out_of_range(self):
        with pytest.raises(ValueError):
            ScoringConfig(
                source_scores={"Test": 15},
                source_score_range=(1, 10),
            )
        with pytest.raises(ValueError):
            ScoringConfig(
                source_scores={"Test": 0},
                source_score_range=(1, 10),
            )

    def test_boost_keyword_negative_bonus(self):
        with pytest.raises(ValueError):
            ScoringConfig(boost_keywords={"bad": -1.0})

    def test_boost_keyword_non_numeric(self):
        with pytest.raises(ValueError):
            ScoringConfig(boost_keywords={"bad": "string"})

    def test_max_boost_total_exceeded(self):
        with pytest.raises(ValueError):
            ScoringConfig(
                max_boost_total=5.0,
                boost_keywords={"huge": 10.0},
            )

    def test_penalty_keyword_duplicate(self):
        with pytest.raises(ValueError):
            ScoringConfig(penalty_keywords=["спорт", "спорт"])

    def test_penalty_keyword_empty(self):
        with pytest.raises(ValueError):
            ScoringConfig(penalty_keywords=["спорт", ""])

    def test_valid_custom_config(self):
        cfg = ScoringConfig(
            max_boost_total=15.0,
            source_score_range=(1, 10),
            source_scores={"Custom": 8},
            boost_keywords={"word": 5.0},
            penalty_keywords=["spam"],
        )
        assert cfg.get_source_score("Custom") == 8.0
        assert cfg.get_source_score("Missing") == 2.0
        assert cfg.get_max_boost("some word here") == 5.0
        assert cfg.get_max_boost("no match") == 0.0
        assert cfg.has_penalty_keyword("this is spam") is True
        assert cfg.has_penalty_keyword("clean text") is False


# =====================================================================
# ScoringConfigLoader (YAML loading, fallback, hot-reload)
# =====================================================================


class TestScoringConfigLoader:
    def test_missing_file_fallback(self):
        """При отсутствии файла — fallback на DEFAULT_CONFIG."""
        loader = ScoringConfigLoader(path="/nonexistent/scoring.yaml")
        assert loader.config.source_scores == DEFAULT_CONFIG.source_scores

    def test_load_valid_yaml(self, tmp_path: Path):
        data = {
            "max_boost_total": 8.0,
            "source_score_range": [1, 10],
            "source_scores": {"TestSource": 7},
            "boost_keywords": {"test": 3.0},
            "penalty_keywords": ["spam"],
        }
        p = tmp_path / "scoring.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")

        loader = ScoringConfigLoader(path=str(p))
        assert loader.config.max_boost_total == 8.0
        assert loader.config.source_scores == {"TestSource": 7.0}

    def test_invalid_yaml_fallback(self, tmp_path: Path):
        p = tmp_path / "scoring.yaml"
        p.write_text("this is not: [valid yaml: :", encoding="utf-8")

        loader = ScoringConfigLoader(path=str(p))
        assert loader.config.source_scores == DEFAULT_CONFIG.source_scores

    def test_validation_error_fallback(self, tmp_path: Path):
        p = tmp_path / "scoring.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "max_boost_total": 5.0,
                    "source_score_range": [1, 10],
                    "source_scores": {"Bad": 99},
                }
            ),
            encoding="utf-8",
        )

        loader = ScoringConfigLoader(path=str(p))
        assert loader.config.source_scores == DEFAULT_CONFIG.source_scores

    def test_hot_reload_by_mtime(self, tmp_path: Path):
        p = tmp_path / "scoring.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "max_boost_total": 10.0,
                    "source_score_range": [1, 10],
                    "source_scores": {"SourceA": 5},
                    "boost_keywords": {},
                    "penalty_keywords": [],
                }
            ),
            encoding="utf-8",
        )

        loader = ScoringConfigLoader(path=str(p))
        assert loader.config.source_scores == {"SourceA": 5.0}

        # Изменяем файл
        p.write_text(
            yaml.safe_dump(
                {
                    "max_boost_total": 10.0,
                    "source_score_range": [1, 10],
                    "source_scores": {"SourceB": 9},
                    "boost_keywords": {},
                    "penalty_keywords": [],
                }
            ),
            encoding="utf-8",
        )
        # Принудительно меняем mtime в будущее, чтобы гарантировать перезагрузку
        os.utime(p, (p.stat().st_atime + 2, p.stat().st_mtime + 2))

        ok = loader.check_and_reload()
        assert ok is True
        assert loader.config.source_scores == {"SourceB": 9.0}

    def test_reload_explicit(self, tmp_path: Path):
        p = tmp_path / "scoring.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "max_boost_total": 10.0,
                    "source_score_range": [1, 10],
                    "source_scores": {"X": 1},
                    "boost_keywords": {},
                    "penalty_keywords": [],
                }
            ),
            encoding="utf-8",
        )

        loader = ScoringConfigLoader(path=str(p))
        assert loader.config.source_scores == {"X": 1.0}

        p.write_text(
            yaml.safe_dump(
                {
                    "max_boost_total": 10.0,
                    "source_score_range": [1, 10],
                    "source_scores": {"Y": 2},
                    "boost_keywords": {},
                    "penalty_keywords": [],
                }
            ),
            encoding="utf-8",
        )

        assert loader.reload() is True
        assert loader.config.source_scores == {"Y": 2.0}

    def test_empty_yaml_fallback(self, tmp_path: Path):
        p = tmp_path / "scoring.yaml"
        p.write_text("", encoding="utf-8")
        loader = ScoringConfigLoader(path=str(p))
        assert loader.config.source_scores == DEFAULT_CONFIG.source_scores


# =====================================================================
# Integration: core/scoring.py uses external config
# =====================================================================


class TestScoringIntegration:
    def test_detect_score_uses_yaml_source_scores(self, tmp_path: Path, monkeypatch):
        """detect_score должен использовать source_scores из YAML."""
        p = tmp_path / "scoring.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "max_boost_total": 10.0,
                    "source_score_range": [1, 10],
                    "source_scores": {"TestNews": 9},
                    "boost_keywords": {},
                    "penalty_keywords": [],
                }
            ),
            encoding="utf-8",
        )

        # Подменяем singleton
        from core import scoring_config_loader

        scoring_config_loader._scoring_loader = ScoringConfigLoader(path=str(p))

        article = {
            "source_tag": "TestNews",
            "title": "Something",
            "summary": "",
            "link": "http://example.com/1",
        }
        score = detect_score(article)
        assert score == 9

    def test_detect_score_boost_from_yaml(self, tmp_path: Path, monkeypatch):
        """detect_score должен применять boost_keywords из YAML."""
        p = tmp_path / "scoring.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "max_boost_total": 10.0,
                    "source_score_range": [1, 10],
                    "source_scores": {"TestNews": 5},
                    "boost_keywords": {"кризис": 4.0},
                    "penalty_keywords": [],
                }
            ),
            encoding="utf-8",
        )

        from core import scoring_config_loader

        scoring_config_loader._scoring_loader = ScoringConfigLoader(path=str(p))

        article = {
            "source_tag": "TestNews",
            "title": "Финансовый кризис",
            "summary": "",
            "link": "http://example.com/2",
        }
        score = detect_score(article)
        assert score == 9  # 5 base + 4 boost

    def test_detect_score_penalty_from_yaml(self, tmp_path: Path, monkeypatch):
        """detect_score должен применять penalty_keywords из YAML."""
        p = tmp_path / "scoring.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "max_boost_total": 10.0,
                    "source_score_range": [1, 10],
                    "source_scores": {"TestNews": 5},
                    "boost_keywords": {},
                    "penalty_keywords": ["спорт"],
                }
            ),
            encoding="utf-8",
        )

        from core import scoring_config_loader

        scoring_config_loader._scoring_loader = ScoringConfigLoader(path=str(p))

        article = {
            "source_tag": "TestNews",
            "title": "Новости спорта",
            "summary": "",
            "link": "http://example.com/3",
        }
        score = detect_score(article)
        assert score == 4  # 5 base - 1 penalty

    def test_detect_score_clamped_to_1_10(self, tmp_path: Path, monkeypatch):
        """Итоговый score должен быть в диапазоне [1, 10]."""
        p = tmp_path / "scoring.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "max_boost_total": 20.0,
                    "source_score_range": [1, 10],
                    "source_scores": {"TestNews": 10},
                    "boost_keywords": {"огромный": 15.0},
                    "penalty_keywords": [],
                }
            ),
            encoding="utf-8",
        )

        from core import scoring_config_loader

        scoring_config_loader._scoring_loader = ScoringConfigLoader(path=str(p))

        article = {
            "source_tag": "TestNews",
            "title": "огромный заголовок",
            "summary": "",
            "link": "http://example.com/4",
        }
        score = detect_score(article)
        assert score == 10  # clamped

    def test_get_delay_for_score(self):
        assert get_delay_for_score(9, "normal", False) == 0
        assert get_delay_for_score(5, "normal", False) == 0
        assert get_delay_for_score(3, "normal", False) == 1800


# =====================================================================
# Singleton behaviour
# =====================================================================


class TestSingleton:
    def test_get_scoring_loader_returns_same_instance(self, tmp_path: Path, monkeypatch):
        p = tmp_path / "scoring.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "max_boost_total": 10.0,
                    "source_score_range": [1, 10],
                    "source_scores": {},
                    "boost_keywords": {},
                    "penalty_keywords": [],
                }
            ),
            encoding="utf-8",
        )

        from core import scoring_config_loader

        scoring_config_loader._scoring_loader = None

        monkeypatch.setenv("SCORING_CONFIG_PATH", str(p))
        loader1 = get_scoring_loader(str(p))
        loader2 = get_scoring_loader(str(p))
        assert loader1 is loader2
