"""
A/B тестирование форматов постов (P3-002).
- Распределение вариантов 50/50
- Логирование метрик: CTR (реакции), доставка
- Отчёт по результатам
- P2-002: Статистическая значимость через z-test + p-value + 95% CI
- P2-003: Автоматический winner selection (Multi-Armed Bandit, 80/20)
"""

import hashlib
import math
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.db_maintenance import enable_wal_mode
from utils.logger import logger

# Варианты A/B теста
AB_VARIANTS = {
    "control": {
        "name": "Контроль",
        "description": "Стандартный формат: AI-комментарий + случайный closer",
        "has_ai_comment": True,
        "has_closer_question": True,
        "has_summary": True,
    },
    "no_ai_comment": {
        "name": "Без AI",
        "description": "Только заголовок + summary, без AI-комментария",
        "has_ai_comment": False,
        "has_closer_question": True,
        "has_summary": True,
    },
    "no_closer": {
        "name": "Без вопроса",
        "description": "Без вопроса в конце, только AI-комментарий",
        "has_ai_comment": True,
        "has_closer_question": False,
        "has_summary": True,
    },
    "short_form": {
        "name": "Короткий",
        "description": "Только заголовок + ссылка, без AI и summary",
        "has_ai_comment": False,
        "has_closer_question": False,
        "has_summary": False,
    },
}

# Минимальный размер выборки для объявления стат. значимости
MIN_SAMPLE_SIZE = 100

# P2-003: Доля трафика на winner при определённом лидере
WINNER_TRAFFIC_SHARE = 0.80
EXPLORATION_TRAFFIC_SHARE = 0.20


def _z_test(
    control_ctr: float,
    treatment_ctr: float,
    control_n: int,
    treatment_n: int,
) -> Tuple[float, float, float, float]:
    """
    Двухвыборочный z-test для пропорций (CTR).

    Args:
        control_ctr: CTR контроля (0–100)
        treatment_ctr: CTR варианта (0–100)
        control_n: Количество показов контроля
        treatment_n: Количество показов варианта

    Returns:
        (z_score, p_value, ci_95_lower, ci_95_upper) — ci относительно разницы treatment - control
    """
    if control_n < 1 or treatment_n < 1:
        return 0.0, 1.0, -999.0, 999.0

    # Переводим проценты в пропорции
    p1 = control_ctr / 100.0
    p2 = treatment_ctr / 100.0

    # Pooled proportion
    x1 = p1 * control_n
    x2 = p2 * treatment_n
    p_pool = (x1 + x2) / (control_n + treatment_n)

    # Standard error
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / control_n + 1 / treatment_n))
    if se == 0:
        return 0.0, 1.0, 0.0, 0.0

    # Z-score
    z = (p2 - p1) / se

    # P-value (two-tailed)
    try:
        from scipy import stats

        p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    except ImportError:
        # Fallback без scipy: приближение через erf
        p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))

    # 95% CI для разницы пропорций
    se_diff = math.sqrt(p1 * (1 - p1) / control_n + p2 * (1 - p2) / treatment_n)
    margin = 1.96 * se_diff
    diff = p2 - p1
    ci_lower = (diff - margin) * 100  # обратно в проценты
    ci_upper = (diff + margin) * 100

    return z, p_value, ci_lower, ci_upper


def _significance_flag(p_value: float, n: int, ci_lower: float, ci_upper: float) -> str:
    """Возвращает текстовый флаг стат. значимости."""
    if n < MIN_SAMPLE_SIZE:
        return "⚠️ Недостаточно данных"
    if p_value < 0.05 and ci_lower > 0:
        return "✅ Стат. значимо лучше"
    if p_value < 0.05 and ci_upper < 0:
        return "❌ Стат. значимо хуже"
    if p_value < 0.05:
        return "✅ Стат. значимо (p < 0.05)"
    return "➖ Нет различий"


class ABTestingManager:
    """Менеджер A/B тестирования форматов постов."""

    def __init__(self, db_path: str = "storage/news_cache.db"):
        Path(db_path).parent.mkdir(exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        enable_wal_mode(self.conn)
        self._init_database()
        logger.info(f"ABTestingManager инициализирован: {db_path}")

    def _init_database(self):
        cursor = self.conn.cursor()

        # --- Записи A/B тестов ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ab_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_link TEXT NOT NULL,
                article_title TEXT,
                variant TEXT NOT NULL,
                message_id INTEGER,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                has_image INTEGER DEFAULT 0,
                score INTEGER DEFAULT 0
            )
        """
        )

        # --- Метрики по вариантам (агрегированные) ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ab_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                variant TEXT NOT NULL,
                date TEXT NOT NULL,
                impressions INTEGER DEFAULT 0,
                reactions INTEGER DEFAULT 0,
                saves INTEGER DEFAULT 0,
                UNIQUE(variant, date)
            )
        """
        )

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ab_tests_link ON ab_tests(article_link)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ab_tests_variant ON ab_tests(variant)")
        # --- P2-003: Состояние winner для Multi-Armed Bandit ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ab_winner_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                winner_variant TEXT,
                determined_at TIMESTAMP,
                confidence REAL,
                total_impressions INTEGER DEFAULT 0
            )
        """
        )

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ab_metrics_date ON ab_metrics(date)")

        self.conn.commit()

    def assign_variant(self, article_link: str) -> str:
        """
        P2-003: Определяет вариант A/B для статьи.
        Если winner определён → 80% трафика на winner, 20% — exploration.
        Иначе — равномерное распределение по хешу URL.
        """
        if not article_link:
            return "control"

        winner = self._get_cached_winner()
        if winner:
            # MAB: 80% winner, 20% exploration (равномерно между остальными)
            hash_val = int(hashlib.md5(article_link.encode()).hexdigest(), 16)
            bucket = hash_val % 100  # 0–99
            if bucket < int(WINNER_TRAFFIC_SHARE * 100):
                return winner
            # Exploration: равномерно между остальными вариантами
            others = [v for v in AB_VARIANTS if v != winner]
            idx = (hash_val // 100) % len(others)
            return others[idx]

        # Обычное равномерное распределение
        hash_val = int(hashlib.md5(article_link.encode()).hexdigest(), 16)
        variants = list(AB_VARIANTS.keys())
        idx = hash_val % len(variants)
        return variants[idx]

    def _get_cached_winner(self) -> Optional[str]:
        """Возвращает закешированный winner из БД или None."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT winner_variant FROM ab_winner_state WHERE id = 1")
        row = cursor.fetchone()
        return row["winner_variant"] if row else None

    def get_winner_variant(
        self, min_days: int = 7, confidence: float = 0.95
    ) -> Optional[Dict[str, Any]]:
        """
        P2-003: Определяет winner на основе стат. значимости.

        Args:
            min_days: Минимум дней сбора данных
            confidence: Уровень доверия (p < 1 - confidence)

        Returns:
            Dict с winner-вариантом или None если недостаточно данных
        """
        # Проверяем, есть ли уже закешированный winner
        cached = self._get_cached_winner()
        if cached:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM ab_winner_state WHERE id = 1")
            row = cursor.fetchone()
            return {
                "variant": cached,
                "name": AB_VARIANTS.get(cached, {}).get("name", cached),
                "determined_at": row["determined_at"] if row else None,
                "confidence": row["confidence"] if row else None,
                "total_impressions": row["total_impressions"] if row else 0,
                "cached": True,
            }

        # Получаем результаты за min_days
        results = self.get_results(days=min_days)
        control = next((r for r in results if r["variant"] == "control"), None)
        if not control or control["impressions"] < MIN_SAMPLE_SIZE:
            return None

        # Ищем вариант со стат. значимым улучшением
        p_threshold = 1.0 - confidence
        candidates = []
        for r in results:
            if r["variant"] == "control":
                continue
            if r["impressions"] < MIN_SAMPLE_SIZE:
                continue
            p_val = r.get("p_value", 1.0)
            ci_lower = r.get("ci_lower", -999.0)
            if p_val < p_threshold and ci_lower > 0:
                candidates.append(r)

        if not candidates:
            return None

        # Выбираем вариант с наивысшим CTR
        winner = max(candidates, key=lambda x: x["ctr"])
        total_impressions = sum(r["impressions"] for r in results)

        # Кешируем winner
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO ab_winner_state (id, winner_variant, determined_at, confidence, total_impressions)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                winner_variant = excluded.winner_variant,
                determined_at = excluded.determined_at,
                confidence = excluded.confidence,
                total_impressions = excluded.total_impressions
        """,
            (winner["variant"], datetime.now().isoformat(), winner["p_value"], total_impressions),
        )
        self.conn.commit()
        logger.info(
            f"P2-003: Winner определён: {winner['name']} ({winner['variant']}), "
            f"CTR={winner['ctr']}%, p={winner['p_value']:.4f}"
        )

        return {
            "variant": winner["variant"],
            "name": winner["name"],
            "determined_at": datetime.now().isoformat(),
            "confidence": winner["p_value"],
            "total_impressions": total_impressions,
            "cached": False,
        }

    def reset_winner(self) -> bool:
        """
        P2-003: Сбрасывает winner state.
        Возвращает True если был winner, False если нечего сбрасывать.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT winner_variant FROM ab_winner_state WHERE id = 1")
        row = cursor.fetchone()
        had_winner = row is not None and row["winner_variant"] is not None

        cursor.execute("DELETE FROM ab_winner_state WHERE id = 1")
        self.conn.commit()

        if had_winner:
            logger.info("P2-003: Winner state сброшен")
        return had_winner

    def get_winner_status_text(self) -> str:
        """P2-003: Текстовый статус winner для Telegram."""
        winner_info = self.get_winner_variant(min_days=7, confidence=0.95)
        if winner_info:
            cached = " (из кэша)" if winner_info.get("cached") else ""
            return (
                f"🏆 Winner: <b>{winner_info['name']}</b>{cached}\n"
                f"   CTR: выше control (p={winner_info['confidence']:.4f})\n"
                f"   Распределение: {int(WINNER_TRAFFIC_SHARE*100)}% winner, "
                f"{int(EXPLORATION_TRAFFIC_SHARE*100)}% exploration"
            )

        results = self.get_results(days=7)
        control = next((r for r in results if r["variant"] == "control"), None)
        if not control or control["impressions"] == 0:
            return "📊 Нет данных для определения winner"
        if control["impressions"] < MIN_SAMPLE_SIZE:
            return (
                f"⏳ Сбор данных: {control['impressions']}/{MIN_SAMPLE_SIZE} "
                f"показов control (нужно ещё {MIN_SAMPLE_SIZE - control['impressions']})"
            )
        return "➖ Пока нет стат. значимого winner (все варианты в пределах шума)"

    def get_variant_config(self, variant: str) -> Dict[str, Any]:
        """Возвращает конфигурацию варианта."""
        return AB_VARIANTS.get(variant, AB_VARIANTS["control"])

    def record_sent(
        self,
        article_link: str,
        article_title: str,
        variant: str,
        message_id: Optional[int] = None,
        has_image: bool = False,
        score: int = 0,
    ):
        """Записывает факт отправки поста с вариантом A/B."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO ab_tests (article_link, article_title, variant, message_id, has_image, score)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (article_link, article_title, variant, message_id, int(has_image), score),
        )
        self.conn.commit()

    def record_reaction(self, variant: str, reaction_type: str = "like"):
        """Записывает реакцию на пост варианта A/B."""
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = self.conn.cursor()

        # Upsert метрики
        cursor.execute(
            """
            INSERT INTO ab_metrics (variant, date, impressions, reactions, saves)
            VALUES (?, ?, 0, 0, 0)
            ON CONFLICT(variant, date) DO NOTHING
        """,
            (variant, today),
        )

        if reaction_type == "save":
            cursor.execute(
                """
                UPDATE ab_metrics SET saves = saves + 1 WHERE variant = ? AND date = ?
            """,
                (variant, today),
            )
        else:
            cursor.execute(
                """
                UPDATE ab_metrics SET reactions = reactions + 1 WHERE variant = ? AND date = ?
            """,
                (variant, today),
            )

        self.conn.commit()

    def get_results(self, days: int = 7) -> List[Dict[str, Any]]:
        """Возвращает результаты A/B теста за последние N дней."""
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        cursor = self.conn.cursor()

        # Статистика по отправленным
        cursor.execute(
            """
            SELECT
                variant,
                COUNT(*) as impressions,
                AVG(score) as avg_score,
                SUM(has_image) as with_image
            FROM ab_tests
            WHERE sent_at >= ?
            GROUP BY variant
        """,
            (since,),
        )
        sent_stats = {row["variant"]: dict(row) for row in cursor.fetchall()}

        # Статистика по реакциям
        cursor.execute(
            """
            SELECT
                variant,
                SUM(impressions) as total_impressions,
                SUM(reactions) as total_reactions,
                SUM(saves) as total_saves
            FROM ab_metrics
            WHERE date >= ?
            GROUP BY variant
        """,
            (since,),
        )
        reaction_stats = {row["variant"]: dict(row) for row in cursor.fetchall()}

        # Объединяем
        results = []
        for variant in AB_VARIANTS:
            sent = sent_stats.get(variant, {})
            react = reaction_stats.get(variant, {})
            impressions = sent.get("impressions", 0)
            reactions = react.get("total_reactions", 0)
            saves = react.get("total_saves", 0)
            ctr = (reactions / impressions * 100) if impressions > 0 else 0
            save_rate = (saves / impressions * 100) if impressions > 0 else 0

            results.append(
                {
                    "variant": variant,
                    "name": AB_VARIANTS[variant]["name"],
                    "impressions": impressions,
                    "reactions": reactions,
                    "saves": saves,
                    "ctr": round(ctr, 2),
                    "save_rate": round(save_rate, 2),
                    "avg_score": round(sent.get("avg_score", 0) or 0, 2),
                }
            )

        # P2-002: Добавляем стат. значимость относительно control
        control = next((r for r in results if r["variant"] == "control"), None)
        if control and control["impressions"] > 0:
            for r in results:
                if r["variant"] == "control":
                    r["z_score"] = 0.0
                    r["p_value"] = 1.0
                    r["ci_lower"] = 0.0
                    r["ci_upper"] = 0.0
                    r["significance"] = "—"
                    continue

                z, p, ci_lo, ci_hi = _z_test(
                    control_ctr=control["ctr"],
                    treatment_ctr=r["ctr"],
                    control_n=control["impressions"],
                    treatment_n=r["impressions"],
                )
                r["z_score"] = round(z, 3)
                r["p_value"] = round(p, 4)
                r["ci_lower"] = round(ci_lo, 2)
                r["ci_upper"] = round(ci_hi, 2)
                r["significance"] = _significance_flag(p, r["impressions"], ci_lo, ci_hi)
        else:
            for r in results:
                r["z_score"] = 0.0
                r["p_value"] = 1.0
                r["ci_lower"] = 0.0
                r["ci_upper"] = 0.0
                r["significance"] = "⚠️ Недостаточно данных"

        return results

    def get_report_text(self, days: int = 7) -> str:
        """Формирует текстовый отчёт для Telegram."""
        results = self.get_results(days)
        if not results or all(r["impressions"] == 0 for r in results):
            return f"📊 Нет данных A/B тестов за последние {days} дней"

        lines = [f"📊 <b>A/B тесты (за {days} дней)</b>\n"]
        for r in results:
            sig = r.get("significance", "")
            ci = (
                f"[{r['ci_lower']:+.1f}%; {r['ci_upper']:+.1f}%]"
                if r["variant"] != "control"
                else ""
            )
            lines.append(
                f"<b>{r['name']}</b> ({r['variant']}) {sig}\n"
                f"  Показы: {r['impressions']} | Реакции: {r['reactions']} | Сохранения: {r['saves']}\n"
                f"  CTR: {r['ctr']}% | p={r['p_value']:.4f} | CI95: {ci}\n"
            )

        # Находим лучший вариант по CTR с учётом стат. значимости
        candidates = [
            r
            for r in results
            if r["impressions"] >= MIN_SAMPLE_SIZE
            and r.get("p_value", 1.0) < 0.05
            and r["variant"] != "control"
        ]
        if candidates:
            best = max(candidates, key=lambda x: x["ctr"])
            lines.append(
                f"\n🏆 Лучший CTR: <b>{best['name']}</b> ({best['ctr']}%) {best.get('significance', '')}"
            )
        else:
            # Нет стат. значимых результатов — показываем лидера по CTR с предупреждением
            best = max(results, key=lambda x: x["ctr"] if x["impressions"] > 0 else -1)
            if best["impressions"] < MIN_SAMPLE_SIZE:
                lines.append(
                    f"\n⚠️ Лидер по CTR: <b>{best['name']}</b> ({best['ctr']}%) — недостаточно данных для выводов"
                )
            else:
                lines.append(
                    f"\n➖ Лидер по CTR: <b>{best['name']}</b> ({best['ctr']}%) — различия не стат. значимы"
                )

        return "\n".join(lines)

    def close(self):
        """Закрывает соединение с БД."""
        if self.conn:
            self.conn.close()


# Глобальный экземпляр
ab_testing_manager = ABTestingManager()
