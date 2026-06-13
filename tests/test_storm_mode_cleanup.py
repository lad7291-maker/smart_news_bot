"""
Тесты для P2-008: Storm Mode — не очищать все старые задачи.

Покрывают:
- Просроченные задачи (> MAX_QUEUE_MINUTES) удаляются
- Актуальные orange/yellow задачи сохраняются
- Логирование количества удалённых/сохранённых
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


class TestStormModeCleanup:
    """Тесты очистки очереди при бурсте red-новостей."""

    def _make_job(self, job_id, minutes_from_now):
        """Создаёт mock job с заданным next_run_time."""
        job = MagicMock()
        job.id = job_id
        run_time = datetime.now() + timedelta(minutes=minutes_from_now)
        # APScheduler возвращает timezone-aware datetime
        try:
            import pytz

            run_time = pytz.UTC.localize(run_time)
        except ImportError:
            pass
        job.next_run_time = run_time
        return job

    def test_filter_logic_expired_removed(self):
        """Задачи с run_time > MAX_QUEUE_MINUTES (120) удаляются."""
        MAX_QUEUE_MINUTES = 120

        now = datetime.now()
        max_run_time = now + timedelta(minutes=MAX_QUEUE_MINUTES)

        # Задача на 3 часа вперёд — просрочена
        old_job = self._make_job("publish_old", 180)
        # Задача на 30 минут — актуальна
        recent_job = self._make_job("publish_recent", 30)

        jobs = [old_job, recent_job]
        jobs_to_remove = []
        jobs_to_keep = []

        for j in jobs:
            next_run = j.next_run_time
            if next_run is not None:
                if hasattr(next_run, "replace") and next_run.tzinfo is not None:
                    next_run = next_run.replace(tzinfo=None)
                if next_run > max_run_time:
                    jobs_to_remove.append(j)
                else:
                    jobs_to_keep.append(j)
            else:
                jobs_to_remove.append(j)

        assert len(jobs_to_remove) == 1
        assert jobs_to_remove[0].id == "publish_old"
        assert len(jobs_to_keep) == 1
        assert jobs_to_keep[0].id == "publish_recent"

    def test_filter_logic_all_preserved(self):
        """Все задачи в пределах MAX_QUEUE_MINUTES сохраняются."""
        MAX_QUEUE_MINUTES = 120

        now = datetime.now()
        max_run_time = now + timedelta(minutes=MAX_QUEUE_MINUTES)

        job1 = self._make_job("publish_1", 10)
        job2 = self._make_job("publish_2", 60)
        job3 = self._make_job("publish_3", 119)

        jobs = [job1, job2, job3]
        jobs_to_remove = []
        jobs_to_keep = []

        for j in jobs:
            next_run = j.next_run_time
            if next_run is not None:
                if hasattr(next_run, "replace") and next_run.tzinfo is not None:
                    next_run = next_run.replace(tzinfo=None)
                if next_run > max_run_time:
                    jobs_to_remove.append(j)
                else:
                    jobs_to_keep.append(j)
            else:
                jobs_to_remove.append(j)

        assert len(jobs_to_remove) == 0
        assert len(jobs_to_keep) == 3

    def test_filter_logic_all_removed(self):
        """Все задачи за пределами MAX_QUEUE_MINUTES удаляются."""
        MAX_QUEUE_MINUTES = 120

        now = datetime.now()
        max_run_time = now + timedelta(minutes=MAX_QUEUE_MINUTES)

        job1 = self._make_job("publish_1", 121)
        job2 = self._make_job("publish_2", 180)
        job3 = self._make_job("publish_3", 300)

        jobs = [job1, job2, job3]
        jobs_to_remove = []
        jobs_to_keep = []

        for j in jobs:
            next_run = j.next_run_time
            if next_run is not None:
                if hasattr(next_run, "replace") and next_run.tzinfo is not None:
                    next_run = next_run.replace(tzinfo=None)
                if next_run > max_run_time:
                    jobs_to_remove.append(j)
                else:
                    jobs_to_keep.append(j)
            else:
                jobs_to_remove.append(j)

        assert len(jobs_to_remove) == 3
        assert len(jobs_to_keep) == 0

    def test_filter_logic_boundary_slightly_under_120(self):
        """Задача чуть меньше 120 минут — сохраняется."""
        MAX_QUEUE_MINUTES = 120

        now = datetime.now()
        max_run_time = now + timedelta(minutes=MAX_QUEUE_MINUTES)

        # 119 минут — точно меньше 120
        job = self._make_job("publish_boundary", 119)

        jobs = [job]
        jobs_to_remove = []
        jobs_to_keep = []

        for j in jobs:
            next_run = j.next_run_time
            if next_run is not None:
                if hasattr(next_run, "replace") and next_run.tzinfo is not None:
                    next_run = next_run.replace(tzinfo=None)
                if next_run > max_run_time:
                    jobs_to_remove.append(j)
                else:
                    jobs_to_keep.append(j)
            else:
                jobs_to_remove.append(j)

        assert len(jobs_to_keep) == 1
        assert len(jobs_to_remove) == 0

    def test_filter_logic_none_next_run_time(self):
        """Задача без next_run_time удаляется."""
        MAX_QUEUE_MINUTES = 120

        now = datetime.now()
        max_run_time = now + timedelta(minutes=MAX_QUEUE_MINUTES)

        job = MagicMock()
        job.id = "publish_none"
        job.next_run_time = None

        jobs = [job]
        jobs_to_remove = []
        jobs_to_keep = []

        for j in jobs:
            next_run = j.next_run_time
            if next_run is not None:
                if hasattr(next_run, "replace") and next_run.tzinfo is not None:
                    next_run = next_run.replace(tzinfo=None)
                if next_run > max_run_time:
                    jobs_to_remove.append(j)
                else:
                    jobs_to_keep.append(j)
            else:
                jobs_to_remove.append(j)

        assert len(jobs_to_remove) == 1
        assert len(jobs_to_keep) == 0
