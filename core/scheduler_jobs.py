def _strip_engagement_phrases(text: str) -> str:
    """Удаляет engagement-вопросы из AI-комментария."""
    if not text:
        return text

    import re

    # Шаг 1: Удаляем известные engagement-фразы (с вопросительным знаком)
    phrases = [
        "Обсуждаем?",
        "Согласны?",
        "Как считаете?",
        "Как думаете?",
        "Верите?",
        "Поддерживаете?",
        "А вы?",
        "А у вас?",
        "Что думаете?",
        "Ваше мнение?",
        "Пишите в комментариях",
        "Делитесь мнением",
        "Ждем ваше мнение",
        "Ждём ваше мнение",
        "А как вы?",
    ]
    for phrase in phrases:
        text = text.replace(phrase, "").strip()

    # Шаг 2: Удаляем фразы с тире/дефисом И всё, что после них до конца предложения
    # Примеры: "Как считаете — это серьёзно?" → удаляем всё "Как считаете — это серьёзно?"
    #          "Согласны — это правильно?" → удаляем всё "Согласны — это правильно?"
    dash_patterns = [
        r"Как считаете\s*[—–\-]\s*[^.!?]*[.!?]?",
        r"Как думаете\s*[—–\-]\s*[^.!?]*[.!?]?",
        r"Согласны\s*[—–\-]\s*[^.!?]*[.!?]?",
        r"Обсуждаем\s*[—–\-]\s*[^.!?]*[.!?]?",
        r"А вы\s*[—–\-]\s*[^.!?]*[.!?]?",
        r"А как вы\s*[—–\-]\s*[^.!?]*[.!?]?",
        r"Ваше мнение\s*[—–\-]\s*[^.!?]*[.!?]?",
        r"Что думаете\s*[—–\-]\s*[^.!?]*[.!?]?",
        r"Верите\s*[—–\-]\s*[^.!?]*[.!?]?",
        r"Поддерживаете\s*[—–\-]\s*[^.!?]*[.!?]?",
    ]
    for pattern in dash_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

    # Шаг 3: Чистим обрывки — тире в начале строки, двойные пробелы, точки с пробелами
    text = re.sub(r"^[—–\-]\s*", "", text).strip()
    text = re.sub(r"\s+[—–\-]\s*$", "", text).strip()
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = re.sub(r"\s+([.!?])", r"\1", text).strip()
    # Убираем точку в конце, если перед ней пробел или она одна
    text = re.sub(r"\s+\.$", ".", text).strip()
    # Убираем висячие пробелы перед пунктуацией
    text = re.sub(r"\s+([,;:!?])", r"\1", text).strip()

    return text


"""
Scheduler jobs для Smart News Bot.
P1-001: Вынесены из bot_runner.py.

Содержит: job_collect_news, publish_single_article, collect_from_source,
_send_yellow_digest, _build_digest_text, get_last_scheduled_time.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from ai_core import analyze_news
from config import config
from core.filters import is_russian
from core.scoring import detect_score, get_delay_for_score
from telegram_bot.formatter import _detect_topic_emoji
from telegram_bot.poster import send_multiple_news
from translator import translate_to_russian
from utils import publish_policy
from utils.alert_manager import alert_manager
from utils.deduplicator import deduplicate_articles
from utils.health import health_checker
from utils.image_search import find_news_image

logger = logging.getLogger(__name__)

# Глобальная очередь yellow-новостей для дайджестов
_yellow_digest_queue: List[Dict[str, Any]] = []


# === Зависимости (устанавливаются при инициализации) ===
_deps: Dict[str, Any] = {}


def set_scheduler_dependencies(**kwargs) -> None:
    """Устанавливает зависимости для scheduler jobs."""
    _deps.update(kwargs)


def _bot():
    return _deps["bot"]


def _scheduler() -> Optional[AsyncIOScheduler]:
    return _deps.get("scheduler")


def _cache_manager():
    return _deps["cache_manager"]


def _parser():
    return _deps["parser"]


# === Дайджест ===


def _build_digest_text(articles: List[Dict[str, Any]]) -> str:
    """Формирует текст дайджеста с группировкой по темам и эмодзи."""
    if not articles:
        return ""

    tagged = []
    for article in articles[:10]:
        title = article.get("title", "Без заголовка")
        summary = article.get("summary", "") or ""
        link = article.get("link", "")
        source = article.get("source", "News")
        emoji = _detect_topic_emoji(title, summary, source)
        short = ""
        if summary:
            s = " ".join(summary.split())
            if len(s) > 30:
                short = s[:120].rstrip()
                if len(s) > 120:
                    short += "…"
        tagged.append(
            {
                "emoji": emoji,
                "title": title,
                "short": short,
                "link": link,
                "source": source,
            }
        )

    groups: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for item in tagged:
        key = item["emoji"]
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(item)

    lines: List[str] = ["📰 <b>Дайджест новостей</b>\n"]
    for emoji in order:
        lines.append(f"\n{emoji} <b>{emoji}</b>")
        for item in groups[emoji]:
            line = f"• {item['title']}"
            if item["short"]:
                line += f"\n  <i>{item['short']}</i>"
            if item["link"]:
                line += f"\n  🔗 <a href='{item['link']}'>Читать</a>"
            if item["source"]:
                line += f" | #{item['source']}"
            lines.append(line)

    text = "\n".join(lines)
    MAX_LEN = 4000
    if len(text) > MAX_LEN:
        truncated = text[:MAX_LEN].rsplit("\n", 1)[0]
        text = truncated + "\n\n<i>… и ещё несколько новостей</i>"
    return text


async def _send_yellow_digest(articles: List[Dict[str, Any]]) -> None:
    """Отправляет дайджест из yellow-новостей одним сообщением."""
    if not articles:
        return
    text = _build_digest_text(articles)
    if not text:
        return

    cache_manager = _cache_manager()
    for article in articles[:10]:
        link = article.get("link", "")
        title = article.get("title", "Без заголовка")
        if link:
            cache_manager.mark_processing(link, "digest", "digest", title)
            cache_manager.mark_processed(link, success=True)

    try:
        await _bot().send_message(
            chat_id=config.TELEGRAM_CHANNEL_ID,
            text=text,
            disable_web_page_preview=True,
        )
        logger.info(f"✅ Дайджест отправлен: {len(articles)} yellow-новостей")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки дайджеста: {e}")
        health_checker.record_error()


async def _send_scheduled_digest() -> None:
    """Отправляет накопленный дайджест в 10:00, 17:00 и 21:00 МСК."""
    global _yellow_digest_queue
    if not _yellow_digest_queue:
        logger.info("📭 Дайджест пуст, ничего не отправляем")
        return
    if len(_yellow_digest_queue) >= 3:
        # Убираем дубли по ссылке и похожие по заголовку
        seen_links: set = set()
        seen_titles: list = []
        unique_articles: list = []
        for article in _yellow_digest_queue:
            link = article.get("link", "")
            title = article.get("title", "")
            if not link:
                continue
            if link in seen_links:
                continue
            # Проверяем похожий заголовок (простая эвристика: нормализованное сравнение)
            norm_title = title.lower().strip().replace(" ", "")
            is_duplicate = False
            for seen in seen_titles:
                if norm_title == seen or (
                    len(norm_title) > 10
                    and len(seen) > 10
                    and (norm_title in seen or seen in norm_title)
                ):
                    is_duplicate = True
                    break
            if is_duplicate:
                continue
            seen_links.add(link)
            seen_titles.append(norm_title)
            unique_articles.append(article)
        if len(unique_articles) >= 3:
            await _send_yellow_digest(unique_articles)
            logger.info(
                f"✅ Дайджест отправлен по расписанию: {len(unique_articles)} уникальных новостей (было {len(_yellow_digest_queue)})"
            )
        else:
            logger.info(
                f"📭 После дедупликации мало новостей ({len(unique_articles)}), накапливаем"
            )
    else:
        logger.info(f"📭 Мало новостей для дайджеста ({len(_yellow_digest_queue)}), накапливаем")
    _yellow_digest_queue.clear()


# === Сбор из одного источника ===


async def collect_from_source(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Собирает новости из одного RSS-источника."""
    url = source.get("url")
    tag = source.get("tag", "unknown")

    if not url:
        return []

    try:
        parser = _parser()
        news = await parser.parse_feed(url, tag)
        cache_manager = _cache_manager()
        fresh = [n for n in news if not cache_manager.is_processed(n.get("link", ""))]
        for item in fresh:
            item["source_tag"] = tag
        logger.info(f"RSS {tag}: получено {len(fresh)} свежих новостей")
        return fresh
    except Exception as e:
        logger.warning(f"Проблема при парсинге {url}: {e}")
        health_checker.record_error()
        return []


def get_last_scheduled_time() -> datetime:
    """Возвращает время последней запланированной публикации."""
    scheduler = _scheduler()
    if scheduler is None:
        return datetime.now()
    jobs = scheduler.get_jobs()
    publish_jobs = [j for j in jobs if j.id.startswith("publish_") and j.next_run_time is not None]
    if not publish_jobs:
        return datetime.now()
    max_time = max(j.next_run_time for j in publish_jobs)
    now = datetime.now()
    if max_time > now + timedelta(hours=2):
        return now
    return max_time


# === Публикация одной новости ===


async def publish_single_article(article: Dict[str, Any]) -> None:
    """Публикует одну новость в канал."""
    link = article.get("link")
    title = (article.get("title") or "")[:120]
    score = article.get("score", 5)
    level = publish_policy.get_publish_level(score)
    cache_manager = _cache_manager()
    scheduler = _scheduler()

    if not link:
        logger.warning("⚠️ У статьи отсутствует link, пропускаем.")
        return

    if cache_manager.is_processed(link):
        logger.info(f"⏭ Уже опубликовано, пропускаем: {title}...")
        return

    # Проверка политики публикации
    mode = publish_policy.get_mode()
    quiet = publish_policy.is_quiet_hours()
    allowed, reason = publish_policy.should_publish(level, score, mode, quiet)

    if not allowed:
        delay = publish_policy.get_delay_seconds(level, score, mode, quiet)
        if delay and delay > 0:
            logger.info(f"⏳ Отложено [{reason}]: {title} → через {delay//60} мин")
            link_hash = cache_manager._generate_hash(link)
            if scheduler:
                scheduler.add_job(
                    publish_single_article,
                    trigger=DateTrigger(run_date=datetime.now() + timedelta(seconds=delay)),
                    id=f"publish_{link_hash}",
                    args=[article],
                    replace_existing=True,
                )
        else:
            logger.info(f"🚫 Пропущено [{reason}]: {title}")
        return

    # Проверка кулдауна по темам
    cooldown_ok, cooldown_reason, cooldown_sec = publish_policy.check_topic_cooldown(
        article.get("title", ""), level
    )
    if not cooldown_ok:
        logger.info(f"⏳ Кулдаун [{cooldown_reason}]: {title} → через {cooldown_sec//60} мин")
        link_hash = cache_manager._generate_hash(link)
        if scheduler:
            scheduler.add_job(
                publish_single_article,
                trigger=DateTrigger(run_date=datetime.now() + timedelta(seconds=cooldown_sec)),
                id=f"publish_{link_hash}",
                args=[article],
                replace_existing=True,
            )
        return

    try:
        cache_manager.mark_processing(
            link,
            article.get("type"),
            article.get("source"),
            article.get("title"),
        )

        # Перевод (только перед публикацией)
        article_title = article.get("title", "") or ""
        article_summary = article.get("summary", "") or ""
        if not is_russian(f"{article_title} {article_summary}"):
            try:
                translated_title, translated_summary = await asyncio.gather(
                    translate_to_russian(article_title),
                    translate_to_russian(article_summary),
                    return_exceptions=True,
                )
                if not isinstance(translated_title, Exception):
                    article["title"] = translated_title or article_title
                if not isinstance(translated_summary, Exception):
                    article["summary"] = translated_summary or article_summary
                article["translated"] = True
                logger.info(f"🌐 Переведено перед публикацией: {article['title'][:50]}...")
            except Exception as te:
                logger.warning(f"⚠️ Ошибка перевода перед публикацией: {te}")

        # Параллельно: AI-анализ + поиск изображения
        ai_task = analyze_news(
            title=article.get("title", ""), summary=article.get("summary", ""), score=score
        )

        existing_image = article.get("image_url")
        existing_image_source = article.get("image_source")
        existing_image_score = article.get("image_score", 0)

        # Гибридный подход к изображениям:
        # score >= 65 — высокая уверенность, используем сразу
        # score 50-65 — спорный, вызываем LLM judge
        # score 30-50 — сомнительные, LLM + SearXNG
        # score < 30 — отбрасываем, ищем через SearXNG
        if existing_image and existing_image_score >= 65:
            image_task = asyncio.sleep(0)
            source_label = existing_image_source or "rss"
            logger.info(
                f"🖼 Изображение из {source_label} (score={existing_image_score}): {existing_image[:60]}..."
            )
        else:
            # Собираем кандидатов для гибридного подхода
            candidates = []
            if existing_image and existing_image_score >= 30:
                from ai_core.image_judge import ImageCandidate

                candidates.append(
                    ImageCandidate(
                        url=existing_image,
                        score=existing_image_score,
                        source=existing_image_source or "rss",
                    )
                )

            image_task = find_news_image(
                title=article.get("title", ""),
                source=article.get("source", ""),
                summary=article.get("summary", ""),
                existing_candidates=candidates if candidates else None,
            )

        try:
            ai_comment, image_url = await asyncio.wait_for(
                asyncio.gather(ai_task, image_task), timeout=60
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"⏱ Таймаут AI/изображения для статьи: {article.get('title', '')[:50]}..."
            )
            ai_comment = ""
            image_url = existing_image if existing_image and existing_image_score >= 65 else None

        article["ai_comment"] = _strip_engagement_phrases(ai_comment)
        if existing_image and existing_image_score >= 65:
            article["image_url"] = existing_image
            article["image_source"] = existing_image_source or "rss"
        elif image_url:
            article["image_url"] = image_url

            from utils.image_relevance_checker import get_fallback_image_url

            fallback_url = get_fallback_image_url(article.get("source", ""))
            if fallback_url and image_url == fallback_url:
                article["image_is_fallback"] = True
                article["image_source"] = "fallback"
                logger.info(f"🔄 Fallback-изображение для {article.get('source', '')}")
            else:
                # Определяем source по URL
                if article.get("image_source") != "llm":
                    article["image_source"] = "searxng"
                logger.info(f"🖼 SearXNG-изображение для {article.get('source', '')}")

        await send_multiple_news([article], max_posts=1, delay=0)

        cache_manager.mark_processed(link, success=True)
        publish_policy.record_publish(score, article.get("title", ""), article.get("source", ""))
        health_checker.record_publish()
        logger.info(f"✅ Опубликовано [{level} {score}]: {title}...")
    except Exception as e:
        logger.error(f"❌ Ошибка публикации ({link}): {e}", exc_info=True)
        cache_manager.mark_processed(link, success=False)
        health_checker.record_error()


# === Основной сбор, перевод и постановка в очередь ===


async def job_collect_news() -> None:
    """Основной job сбора новостей из всех RSS-источников."""
    scheduler = _scheduler()
    if scheduler is None:
        return

    config_obj = _deps["config"]
    score_delays = _deps["SCORE_DELAYS"]
    max_posts_per_run = _deps.get("MAX_POSTS_PER_RUN")
    cache_manager = _cache_manager()

    logger.info(f"🔍 Сбор новостей (интервал {config_obj.PUBLISH_INTERVAL_MINUTES} мин)...")

    try:
        tasks = [collect_from_source(src) for src in config_obj.RSS_SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_news = []
        for res in results:
            if isinstance(res, Exception):
                logger.warning(f"Ошибка при сборе: {res}")
            else:
                all_news.extend(res)

        if not all_news:
            logger.info("😴 Нет свежих новостей")
            return

        # Фильтрация
        from core.filters import filter_article

        filtered_news = [a for a in all_news if filter_article(a)]
        logger.info(f"📊 Всего свежих: {len(all_news)}, после фильтра: {len(filtered_news)}")

        if not filtered_news:
            logger.info("😴 Нет подходящих новостей после фильтрации")
            return

        # Оценка баллов
        for article in filtered_news:
            article["score"] = detect_score(article)

        # Антиспам: только логирование
        high_count = len([a for a in filtered_news if a["score"] >= 8])
        if high_count > 5:
            logger.info(
                f"⚠️ Много важных новостей ({high_count}), все будут опубликованы с интервалом {score_delays['high']}с."
            )

        # Сортировка
        filtered_news.sort(
            key=lambda x: (x["score"], x.get("published") or datetime.now()), reverse=True
        )

        # Дедупликация
        filtered_news = deduplicate_articles(filtered_news, similarity_threshold=0.72)

        if max_posts_per_run is not None:
            filtered_news = filtered_news[:max_posts_per_run]

        # Политика публикации
        mode = publish_policy.get_mode()
        quiet = publish_policy.is_quiet_hours()
        logger.info(f"📊 Режим ленты: {mode.upper()}, тихие часы: {quiet}")

        # P2-008: Удаляем только просроченные publish_ задачи
        # (те, чей run_time > now + MAX_QUEUE_MINUTES), сохраняя актуальные orange/yellow
        MAX_QUEUE_MINUTES = 120
        now = datetime.now()
        max_run_time = now + timedelta(minutes=MAX_QUEUE_MINUTES)
        all_publish_jobs = [j for j in scheduler.get_jobs() if j.id.startswith("publish_")]
        jobs_to_remove = []
        jobs_to_keep = []
        for j in all_publish_jobs:
            next_run = j.next_run_time
            # next_run_time может быть timezone-aware или naive
            if next_run is not None:
                if hasattr(next_run, "replace") and next_run.tzinfo is not None:
                    next_run = next_run.replace(tzinfo=None)
                if next_run > max_run_time:
                    jobs_to_remove.append(j)
                else:
                    jobs_to_keep.append(j)
            else:
                jobs_to_remove.append(j)

        for j in jobs_to_remove:
            scheduler.remove_job(j.id)

        if jobs_to_remove or jobs_to_keep:
            logger.info(
                f"🧹 Очередь publish_: удалено {len(jobs_to_remove)} (просрочено >{MAX_QUEUE_MINUTES}мин), "
                f"сохранено {len(jobs_to_keep)}"
            )

        # Планирование
        base_time = datetime.now()
        current_time = base_time
        MIN_POST_INTERVAL = 600
        MAX_QUEUE_MINUTES = 120
        TARGET_SPAN_MINUTES = 60  # растягиваем публикации на 1 час
        scheduled_count = 0
        yellow_articles = []

        # Считаем сколько red/orange новостей будет опубликовано
        publishable_articles = [
            a
            for a in filtered_news
            if a.get("link")
            and not cache_manager.is_processed(a.get("link", ""))
            and not cache_manager.is_title_processed(a.get("title", ""), hours=12)
            and publish_policy.get_publish_level(a["score"]) != "yellow"
        ]
        total_publishable = len(publishable_articles)

        for article in filtered_news:
            link = article.get("link")
            title = (article.get("title") or "")[:80]
            score = article["score"]
            level = publish_policy.get_publish_level(score)

            if not link:
                continue

            delay_seconds = get_delay_for_score(score, mode, quiet)
            link_hash = cache_manager._generate_hash(link)
            job_id = f"publish_{link_hash}"

            if cache_manager.is_processed(link):
                logger.info(f"⏭ Уже опубликовано ранее (URL), пропускаем: {title}...")
                continue

            full_title = article.get("title", "")
            if cache_manager.is_title_processed(full_title, hours=12):
                logger.info(f"⏭ Уже опубликован похожий заголовок, пропускаем: {title}...")
                continue

            # Yellow-новости в дайджест
            if level == "yellow":
                yellow_articles.append(article)
                continue

            min_interval = {"red": 600, "orange": 600, "yellow": 3600}.get(level, 600)

            # Равномерно распределяем новости на TARGET_SPAN_MINUTES (60 мин)
            # Все publishable новости ДОЛЖНЫ уложиться в час, даже если interval < min_interval
            if total_publishable > 1:
                step_seconds = (TARGET_SPAN_MINUTES * 60) // total_publishable
                # Максимум 15 мин между постами (чтобы не слишком редко)
                step_seconds = min(step_seconds, 900)
            else:
                step_seconds = min_interval

            # Но первую новость всё равно не публикуем мгновенно — минимум 5 мин подготовки
            if scheduled_count == 0:
                step_seconds = max(step_seconds, 300)

            run_time = current_time + timedelta(seconds=step_seconds)

            queue_minutes = (run_time - datetime.now()).total_seconds() / 60
            if queue_minutes > MAX_QUEUE_MINUTES:
                current_time = datetime.now()
                run_time = current_time + timedelta(seconds=max(delay_seconds, MIN_POST_INTERVAL))
                logger.info(
                    f"🔄 Очередь {queue_minutes:.0f} мин — сброс, продолжаем с {run_time.strftime('%H:%M:%S')}"
                )

            scheduler.add_job(
                publish_single_article,
                trigger=DateTrigger(run_date=run_time),
                id=job_id,
                args=[article],
                replace_existing=True,
            )
            scheduled_count += 1
            actual_delay = int((run_time - datetime.now()).total_seconds())
            logger.info(
                f"⏳ [{level} {score}] delay={delay_seconds}, step={step_seconds}с, actual={actual_delay}с, run_time={run_time.strftime('%H:%M:%S')} → {title}..."
            )
            current_time = run_time

        # Накапливаем yellow в глобальную очередь
        global _yellow_digest_queue
        _yellow_digest_queue.extend(yellow_articles)
        if len(_yellow_digest_queue) > 30:
            _yellow_digest_queue[:] = _yellow_digest_queue[-30:]

        # P2-004: Обновляем метрику длины очереди
        from utils.metrics import collector

        queue_jobs = [j for j in scheduler.get_jobs() if j.id.startswith("publish_")]
        collector.set_queue_length(len(queue_jobs))

        logger.info(
            f"✅ В очередь добавлено: {scheduled_count}, yellow в дайджесте: {len(yellow_articles)}"
        )

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в job_collect_news: {e}", exc_info=True)
        health_checker.record_error()

    # Проверяем AI cost и шлём алерт если нужно
    try:
        from storage.analytics import analytics_manager

        alert, spent = analytics_manager.check_ai_cost_alert(daily_budget=10.0)
        if alert:
            asyncio.create_task(alert_manager.send_ai_cost_alert(spent))
    except Exception as cost_err:
        logger.debug(f"AI cost check failed: {cost_err}")
