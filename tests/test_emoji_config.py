"""
Тесты для P2-001: Рефакторинг _detect_topic_emoji().

Покрывают:
- Валидацию EmojiConfig / EmojiRule (Pydantic)
- Загрузчик EmojiConfigLoader (YAML, fallback, hot-reload)
- Интеграцию formatter._detect_topic_emoji() с YAML-правилами
"""

import os
from pathlib import Path

import pytest
import yaml

from models.emoji_config import EmojiConfig, EmojiRule
from telegram_bot.emoji_loader import (
    DEFAULT_CONFIG,
    EmojiConfigLoader,
    get_emoji_config,
    get_emoji_loader,
)
from telegram_bot.formatter import _detect_topic_emoji

# =====================================================================
# EmojiRule / EmojiConfig validation
# =====================================================================


class TestEmojiRuleValidation:
    def test_valid_rule(self):
        r = EmojiRule(emoji="🇷🇺", keywords=["россия", "москва"])
        assert r.emoji == "🇷🇺"
        assert r.keywords == ["россия", "москва"]

    def test_empty_emoji_rejected(self):
        with pytest.raises(ValueError):
            EmojiRule(emoji="", keywords=["test"])

    def test_empty_keyword_rejected(self):
        with pytest.raises(ValueError):
            EmojiRule(emoji="🇷🇺", keywords=["россия", ""])

    def test_duplicate_keyword_rejected(self):
        with pytest.raises(ValueError):
            EmojiRule(emoji="🇷🇺", keywords=["россия", "россия"])

    def test_keywords_normalized_to_lower(self):
        r = EmojiRule(emoji="🇷🇺", keywords=["Москва", "РОССИЯ"])
        assert r.keywords == ["москва", "россия"]


class TestEmojiConfigValidation:
    def test_default_config_valid(self):
        cfg = EmojiConfig(**DEFAULT_CONFIG.model_dump())
        assert len(cfg.rules) > 0
        assert cfg.default_emoji == "📰"

    def test_duplicate_emoji_in_rules_rejected(self):
        with pytest.raises(ValueError):
            EmojiConfig(
                rules=[
                    EmojiRule(emoji="🇷🇺", keywords=["a"]),
                    EmojiRule(emoji="🇷🇺", keywords=["b"]),
                ]
            )

    def test_detect_first_match_wins(self):
        cfg = EmojiConfig(
            rules=[
                EmojiRule(emoji="🇷🇺", keywords=["россия"]),
                EmojiRule(emoji="🇺🇸", keywords=["сша"]),
            ],
            source_emoji={},
            default_emoji="📰",
        )
        assert cfg.detect("Новости: россия сегодня") == "🇷🇺"
        assert cfg.detect("Новости из США") == "🇺🇸"

    def test_detect_fallback_source(self):
        cfg = EmojiConfig(rules=[], source_emoji={"RT": "📰"}, default_emoji="❓")
        assert cfg.detect("Нейтральный текст", source="RT") == "📰"

    def test_detect_fallback_default(self):
        cfg = EmojiConfig(rules=[], source_emoji={}, default_emoji="❓")
        assert cfg.detect("Нейтральный текст", source="Unknown") == "❓"

    def test_detect_case_insensitive(self):
        cfg = EmojiConfig(
            rules=[
                EmojiRule(emoji="🇷🇺", keywords=["россия"]),
            ],
            source_emoji={},
            default_emoji="📰",
        )
        assert cfg.detect("РОССИЯ") == "🇷🇺"
        assert cfg.detect("Россия") == "🇷🇺"


# =====================================================================
# EmojiConfigLoader (YAML loading, fallback, hot-reload)
# =====================================================================


class TestEmojiConfigLoader:
    def test_missing_file_fallback(self):
        loader = EmojiConfigLoader(path="/nonexistent/emojis.yaml")
        assert loader.config.default_emoji == "📰"
        assert len(loader.config.rules) > 0

    def test_load_valid_yaml(self, tmp_path: Path):
        data = {
            "rules": [
                {"emoji": "🚀", "keywords": ["космос", "ракета"]},
            ],
            "source_emoji": {"Science": "🔬"},
            "default_emoji": "📰",
        }
        p = tmp_path / "emojis.yaml"
        p.write_text(yaml.safe_dump(data), encoding="utf-8")

        loader = EmojiConfigLoader(path=str(p))
        assert len(loader.config.rules) == 1
        assert loader.config.rules[0].emoji == "🚀"
        assert loader.config.source_emoji == {"Science": "🔬"}

    def test_invalid_yaml_fallback(self, tmp_path: Path):
        p = tmp_path / "emojis.yaml"
        p.write_text("not: [valid yaml::", encoding="utf-8")
        loader = EmojiConfigLoader(path=str(p))
        assert loader.config.default_emoji == "📰"

    def test_validation_error_fallback(self, tmp_path: Path):
        p = tmp_path / "emojis.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "rules": [
                        {"emoji": "", "keywords": ["test"]},  # empty emoji
                    ],
                }
            ),
            encoding="utf-8",
        )
        loader = EmojiConfigLoader(path=str(p))
        assert loader.config.default_emoji == "📰"

    def test_hot_reload_by_mtime(self, tmp_path: Path):
        p = tmp_path / "emojis.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "rules": [{"emoji": "🚀", "keywords": ["космос"]}],
                    "source_emoji": {},
                    "default_emoji": "📰",
                }
            ),
            encoding="utf-8",
        )
        loader = EmojiConfigLoader(path=str(p))
        assert loader.config.rules[0].emoji == "🚀"

        p.write_text(
            yaml.safe_dump(
                {
                    "rules": [{"emoji": "🌊", "keywords": ["океан"]}],
                    "source_emoji": {},
                    "default_emoji": "📰",
                }
            ),
            encoding="utf-8",
        )
        os.utime(p, (p.stat().st_atime + 2, p.stat().st_mtime + 2))

        ok = loader.check_and_reload()
        assert ok is True
        assert loader.config.rules[0].emoji == "🌊"

    def test_empty_yaml_fallback(self, tmp_path: Path):
        p = tmp_path / "emojis.yaml"
        p.write_text("", encoding="utf-8")
        loader = EmojiConfigLoader(path=str(p))
        assert loader.config.default_emoji == "📰"


# =====================================================================
# Integration: formatter._detect_topic_emoji()
# =====================================================================


class TestDetectTopicEmojiIntegration:
    def test_russia_keyword(self, tmp_path: Path, monkeypatch):
        p = tmp_path / "emojis.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "rules": [
                        {"emoji": "🇷🇺", "keywords": ["россия", "путин"]},
                        {"emoji": "🇺🇸", "keywords": ["сша", "трамп"]},
                    ],
                    "source_emoji": {"RT": "📰"},
                    "default_emoji": "❓",
                }
            ),
            encoding="utf-8",
        )

        from telegram_bot import emoji_loader

        emoji_loader._emoji_loader = EmojiConfigLoader(path=str(p))

        assert _detect_topic_emoji("Новости: россия сегодня", "", "") == "🇷🇺"
        assert _detect_topic_emoji("Трамп выступил", "", "") == "🇺🇸"

    def test_source_fallback(self, tmp_path: Path, monkeypatch):
        p = tmp_path / "emojis.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "rules": [],
                    "source_emoji": {"RT": "📰"},
                    "default_emoji": "❓",
                }
            ),
            encoding="utf-8",
        )

        from telegram_bot import emoji_loader

        emoji_loader._emoji_loader = EmojiConfigLoader(path=str(p))

        assert _detect_topic_emoji("Нейтральный заголовок", "", "RT") == "📰"

    def test_default_fallback(self, tmp_path: Path, monkeypatch):
        p = tmp_path / "emojis.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "rules": [],
                    "source_emoji": {},
                    "default_emoji": "❓",
                }
            ),
            encoding="utf-8",
        )

        from telegram_bot import emoji_loader

        emoji_loader._emoji_loader = EmojiConfigLoader(path=str(p))

        assert _detect_topic_emoji("Нейтральный заголовок", "", "Unknown") == "❓"

    def test_first_match_wins(self, tmp_path: Path, monkeypatch):
        p = tmp_path / "emojis.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "rules": [
                        {"emoji": "🇷🇺", "keywords": ["россия"]},
                        {"emoji": "🇺🇸", "keywords": ["россия", "сша"]},
                    ],
                    "source_emoji": {},
                    "default_emoji": "📰",
                }
            ),
            encoding="utf-8",
        )

        from telegram_bot import emoji_loader

        emoji_loader._emoji_loader = EmojiConfigLoader(path=str(p))

        # Первое правило сработает, хотя второе тоже подходит
        assert _detect_topic_emoji("Россия и США", "", "") == "🇷🇺"

    def test_summary_considered(self, tmp_path: Path, monkeypatch):
        p = tmp_path / "emojis.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "rules": [
                        {"emoji": "🚀", "keywords": ["космос"]},
                    ],
                    "source_emoji": {},
                    "default_emoji": "📰",
                }
            ),
            encoding="utf-8",
        )

        from telegram_bot import emoji_loader

        emoji_loader._emoji_loader = EmojiConfigLoader(path=str(p))

        assert _detect_topic_emoji("Заголовок", "Новости из космоса", "") == "🚀"


# =====================================================================
# Singleton behaviour
# =====================================================================


class TestSingleton:
    def test_get_emoji_loader_returns_same_instance(self, tmp_path: Path, monkeypatch):
        p = tmp_path / "emojis.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "rules": [],
                    "source_emoji": {},
                    "default_emoji": "📰",
                }
            ),
            encoding="utf-8",
        )

        from telegram_bot import emoji_loader

        emoji_loader._emoji_loader = None

        loader1 = get_emoji_loader(str(p))
        loader2 = get_emoji_loader(str(p))
        assert loader1 is loader2
