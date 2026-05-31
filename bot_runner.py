#!/usr/bin/env python3
"""
Smart News Bot — ваша личная версия с калиброванными настройками.
- Сбор из 15+ рабочих RSS-источников
- Перевод иностранных новостей через Yandex Translate
- AI-комментарии через YandexGPT / DeepSeek с учётом балла важности
- Оценка 1–10, задержки: 8-10→35с, 5-7→120с, 1-4→240с
- Антиспам: только предупреждение, потерь важных новостей НЕТ
- Полное исправление утечки сессий, HTML-разметка
"""
import asyncio
import re
import logging
import os
import atexit
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from langdetect import detect, LangDetectException

from config import config
from utils.logger import setup_logging
from storage.cache import cache_manager
from parsers.rss_parser import RSSParser
from telegram_bot.poster import send_multiple_news
from translator import translate_to_russian
from ai_core import analyze_news  # асинхронный AI-анализ
from utils.image_search import find_news_image
from utils.deduplicator import deduplicate_articles
from utils import publish_policy
from utils.health import health_checker, periodic_health_check

# === ИНИЦИАЛИЗАЦИЯ ЛОГГЕРА ===
setup_logging()
logger = logging.getLogger(__name__)

# ========== БАЗОВЫЕ НАСТРОЙКИ ==========
PUBLISH_INTERVAL_MINUTES: int = 15        # Как часто запускать сбор RSS-лент (минут)
ADMIN_ID: int = 1718706291               # Ваш Telegram ID
MAX_POSTS_PER_RUN: Optional[int] = None  # None = не ограничивать количество новостей за прогон
# ======================================

# === НАСТРОЙКИ ЗАДЕРЖЕК (секунды) ===
# Установлены по вашему желанию:
# 🔴 8–10 баллов → 35 сек
# 🟠 5–7 баллов → 120 сек
# 🟢 1–4 балла → 240 сек
SCORE_DELAYS: Dict[str, int] = {
    "high": 150,    # 2.5 мин (рандом 120-180с ниже)
    "medium": 390,  # 6.5 мин (рандом 300-480с ниже)
    "low": 14400,   # 4 часа
}

# === БАЗОВЫЕ БАЛЛЫ ДЛЯ ИСТОЧНИКОВ (СКОРРЕКТИРОВАНЫ, ЧТОБЫ НЕ ЗАВЫШАТЬ) ===
SOURCE_SCORES: Dict[str, int] = {
    # ----- Русскоязычные -----
    "Interfax": 5,
    "Security": 4,
    "RT": 5,
    "RIA": 5,
    "Habr": 2,
    "VC": 3,
    "Science": 2,
    # ----- Финансы/Крипто -----
    "CoinTelegraph": 5,
    "CoinDesk": 5,
    "CNBC_World": 5,
    "NYT_Business": 5,
    "NYT_Economy": 5,
    "NYT_DealBook": 4,
    "Investing": 5,
    "NYT_Tech": 4,
}

# === КЛЮЧЕВЫЕ СЛОВА ДЛЯ ПОВЫШЕНИЯ БАЛЛА ===
# ⚠️ ВАШИ БОНУСЫ ПОЛНОСТЬЮ СОХРАНЕНЫ (высокие значения)
BOOST_KEYWORDS: Dict[str, float] = {
    # ----- Геополитика / Военные -----
    "трамп": 6,
    "путин": 6,
    "украина": 5,
    "война": 5,
    "санкции": 7,
    "атака": 4,
    "удар": 3,
    "теракт": 3,
    "обстрел": 1,
    "ракета": 4,
    "ядерный": 5,
    "мобилизация": 5,
    "иран": 5,
    # ----- Экономика / Финансы -----
    "ставка": 6,
    "инфляция": 6,
    "дефолт": 6,
    "рецессия": 6,
    "кризис": 6,
    "нефть": 5,
    "газ": 5,
    "золото": 6,
    "Moex": 5,
    # ----- Крипто -----
    "биткоин": 5,
    "bitcoin": 5,
    "btc": 5,
    # ----- Политика -----
    "выборы": 5,
    "импичмент": 5,
    "переговоры": 4,
    "саммит": 4,
    "резолюция": 4,
    # ----- Прочее -----
    "срочно": 3,
    "breaking": 1,
}

# === КЛЮЧЕВЫЕ СЛОВА ДЛЯ ПОНИЖЕНИЯ БАЛЛА (НЕ-РЫНОЧНЫЕ ТЕМЫ) ===
PENALTY_KEYWORDS: List[str] = [
    "спорт", "футбол", "хоккей", "теннис", "олимпиада",
    "кино", "фильм", "актер", "режиссер", "музыка", "концерт",
    "шоу", "телевидение", "юмор", "знаменитость",
]

# === Ключевые слова для фильтрации (базовая релевантность) ===
KEYWORDS: List[str] = [
    "политика", "политик", "путин", "трамп", "санкции", "выборы", "война",
    "финансы", "финансов", "экономика", "рубль", "доллар", "евро", "инфляция", "ставка",
    "крипто", "биткоин", "bitcoin", "btc", "ethereum", "eth", "криптовалюта", "token",
    "металл", "золото", "серебро", "платина", "медь", "никель", "алюминий", "украина",
    "сырье", "сырьё", "нефть", "газ", "уголь", "пшеница", "кукуруза", "сталь", "руда",
    "россия", "сша", "китай", "европа", "бизнес", "инвестиции",
    "акции", "облигации", "форекс", "биржа", "трейдинг", "Moex", "Nasdaq 100"
]

bot = Bot(
    token=config.TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

parser = RSSParser(hours_limit=72)
scheduler: Optional[AsyncIOScheduler] = None


# === Утилиты фильтрации и оценки ===
def is_russian(text: str) -> bool:
    if not text:
        return False
    try:
        lang = detect(text[:500])
        return lang == "ru"
    except LangDetectException:
        return bool(re.search("[а-яА-Я]", text))

def is_relevant(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    return any(word.lower() in text_lower for word in KEYWORDS)

# === BLACKLIST: мусорные заголовки ===
_JUNK_WORDS = {
    "умножить", "разделить", "сложить", "вычесть", "пример",
    "тест", "викторина", "quiz", "опрос", "голосование",
    "хохот", "смешно", "прикол", "анекдот", "мем",
    "угадай", "найди", "реши", "ответь",
    "загадка", "головоломка", "ребус",
    "сколько будет", "считай", "математика",
}

def _is_junk(text: str) -> bool:
    """Проверяет, является ли текст мусором (викторина, тест, мат. пример)."""
    text_lower = text.lower()
    for junk in _JUNK_WORDS:
        if junk in text_lower:
            return True
    return False

def filter_article(article: Dict[str, Any]) -> bool:
    title = (article.get("title") or "").strip()
    summary = (article.get("summary") or "").strip()
    full_text = f"{title} {summary}"
    
    # Фильтр мусора
    if _is_junk(title):
        logger.debug(f"🗑 Мусор отфильтрован: {title[:60]}...")
        return False
    
    # Минимальная длина summary — мусор обычно короткий
    if summary and len(summary) < 80:
        logger.debug(f"🗑 Слишком короткий summary ({len(summary)} симв.): {title[:60]}...")
        return False
    
    return is_russian(full_text) and is_relevant(full_text)

def detect_score(article: Dict[str, Any]) -> int:
    """
    Оценивает новость по 10-балльной шкале (1–10).
    🔧 ИСПРАВЛЕНО:
      - boost начинается с 0.0 (не с 2.0)
      - penalty начинается с 0.0 (не с 2.0), при штрафе -1.0
      - freshness начинается с 0.0 (нет фиксированного 1.5)
      - базовый балл источника снижен до разумных значений
    """
    source_tag = (article.get("source_tag") or article.get("source") or "").strip()
    base_score = SOURCE_SCORES.get(source_tag, 2)  # по умолчанию 2

    # Бонус за ключевые слова (максимум из найденных)
    title = (article.get("title") or "").lower()
    summary = (article.get("summary") or "").lower()
    text = f"{title} {summary}"
    boost = 0.0
    for word, bonus in BOOST_KEYWORDS.items():
        if word.lower() in text:
            boost = max(boost, bonus)

    # Штраф за нерелевантные темы (спорт, кино и т.п.)
    penalty = 0.0
    for word in PENALTY_KEYWORDS:
        if word.lower() in text:
            penalty = -1.0
            break

    # Бонус за свежесть (только если есть дата, иначе 0)
    freshness = 0.0
    published = article.get("published")
    if published:
        age = datetime.now() - published
        hours = age.total_seconds() / 3600
        if hours < 6:
            freshness = 0.5
        elif hours < 12:
            freshness = 0.3
        elif hours < 24:
            freshness = 0.1

    total = base_score + boost + penalty + freshness
    return max(1, min(10, int(round(total))))

def get_delay_for_score(score: int, mode: str, quiet: bool) -> int:
    """Возвращает задержку напрямую по баллу, игнорируя publish_policy задержки."""
    if score >= 8:
        return 0      # red: публикуем сразу, интервал контролируем min_interval
    elif score >= 5:
        return 0      # orange: публикуем сразу, интервал контролируем min_interval
    else:
        return 1800   # yellow: 30 мин fallback


# === Публикация одной новости ===
async def publish_single_article(article: Dict[str, Any]) -> None:
    link = article.get("link")
    title = (article.get("title") or "")[:120]
    score = article.get("score", 5)
    level = publish_policy.get_publish_level(score)

    if not link:
        logger.warning("⚠️ У статьи отсутствует link, пропускаем.")
        return

    if cache_manager.is_processed(link):
        logger.info(f"⏭ Уже опубликовано, пропускаем: {title}...")
        return

    # === ПРОВЕРКА ПОЛИТИКИ ПУБЛИКАЦИИ ===
    mode = publish_policy.get_mode()
    quiet = publish_policy.is_quiet_hours()

    allowed, reason = publish_policy.should_publish(level, score, mode, quiet)
    if not allowed:
        delay = publish_policy.get_delay_seconds(level, score, mode, quiet)
        if delay and delay > 0:
            logger.info(f"⏳ Отложено [{reason}]: {title} → через {delay//60} мин")
            link_hash = cache_manager._generate_hash(link)
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

    # === ПРОВЕРКА КУЛДАУНА ПО ТЕМАМ ===
    cooldown_ok, cooldown_reason, cooldown_sec = publish_policy.check_topic_cooldown(
        article.get("title", ""), level
    )
    if not cooldown_ok:
        logger.info(f"⏳ Кулдаун [{cooldown_reason}]: {title} → через {cooldown_sec//60} мин")
        link_hash = cache_manager._generate_hash(link)
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

        # Параллельно: AI-анализ + поиск изображения
        ai_task = analyze_news(
            title=article.get("title", ""),
            summary=article.get("summary", ""),
            score=score
        )
        image_task = find_news_image(
            title=article.get("title", ""),
            source=article.get("source", ""),
            summary=article.get("summary", "")
        )
        ai_comment, image_url = await asyncio.gather(ai_task, image_task)

        article["ai_comment"] = ai_comment
        if image_url:
            article["image_url"] = image_url
            # Проверяем, является ли фото fallback (флаг/логотип)
            from utils.image_relevance_checker import get_fallback_image_url
            fallback_url = get_fallback_image_url(article.get("source", ""))
            if fallback_url and image_url == fallback_url:
                article["image_is_fallback"] = True
                article["image_source"] = "fallback"
                logger.info(f"🔄 Используем fallback-изображение для {article.get('source', '')}")

        await send_multiple_news([article], max_posts=1, delay=0)

        cache_manager.mark_processed(link, success=True)
        publish_policy.record_publish(score, article.get("title", ""), article.get("source", ""))
        health_checker.record_publish()  # FEAT-004: отмечаем публикацию для health-check
        logger.info(f"✅ Опубликовано [{level} {score}]: {title}...")
    except Exception as e:
        logger.error(f"❌ Ошибка публикации ({link}): {e}", exc_info=True)
        cache_manager.mark_processed(link, success=False)


# === Дайджест yellow-новостей (FEAT-001) ===
async def _send_yellow_digest(articles: List[Dict[str, Any]]) -> None:
    """Отправляет дайджест из yellow-новостей одним сообщением."""
    if not articles:
        return
    lines = ["📰 <b>Дайджест новостей</b>\n"]
    for i, article in enumerate(articles[:10], 1):
        title = article.get("title", "Без заголовка")
        link = article.get("link", "")
        source = article.get("source", "News")
        lines.append(f"{i}. {title}\n🔗 <a href='{link}'>Читать</a> | #{source}")
        cache_manager.mark_processed(article.get("link", ""), success=True)
    text = "\n\n".join(lines)
    try:
        await bot.send_message(
            chat_id=config.TELEGRAM_CHANNEL_ID,
            text=text,
            disable_web_page_preview=True,
        )
        logger.info(f"✅ Дайджест отправлен: {len(articles)} yellow-новостей")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки дайджеста: {e}")


# === Сбор из одного источника ===
async def collect_from_source(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    url = source.get("url")
    tag = source.get("tag", "unknown")

    if not url:
        return []

    try:
        news = await asyncio.to_thread(parser.parse_feed, url, tag)
        fresh = [n for n in news if not cache_manager.is_processed(n.get("link", ""))]
        for item in fresh:
            item["source_tag"] = tag
        logger.info(f"RSS {tag}: получено {len(fresh)} свежих новостей")
        return fresh
    except Exception as e:
        logger.warning(f"Проблема при парсинге {url}: {e}")
        return []


# === Получение времени последней запланированной публикации ===
def get_last_scheduled_time() -> datetime:
    if scheduler is None:
        return datetime.now()
    jobs = scheduler.get_jobs()
    publish_jobs = [j for j in jobs if j.id.startswith("publish_") and j.next_run_time is not None]
    if not publish_jobs:
        return datetime.now()
    max_time = max(j.next_run_time for j in publish_jobs)
    # Если очередь ушла более чем на 2 часа вперёд — игнорируем, начинаем с now
    now = datetime.now()
    if max_time > now + timedelta(hours=2):
        return now
    return max_time


# === Основной сбор, перевод и постановка в очередь ===
async def job_collect_news() -> None:
    global scheduler

    if scheduler is None:
        return

    logger.info(f"🔍 Сбор новостей (интервал {PUBLISH_INTERVAL_MINUTES} мин)...")

    try:
        tasks = [collect_from_source(src) for src in config.RSS_SOURCES]
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

        # --- ПЕРЕВОД ---
        logger.info("🌐 Перевод иностранных новостей...")
        translated_news = []
        for article in all_news:
            title = article.get("title", "") or ""
            summary = article.get("summary", "") or ""
            if not is_russian(f"{title} {summary}"):
                article["title"] = translate_to_russian(title) or title
                article["summary"] = translate_to_russian(summary) or summary
                article["translated"] = True
            translated_news.append(article)

        # --- ФИЛЬТРАЦИЯ ---
        filtered_news = [a for a in translated_news if filter_article(a)]
        logger.info(f"📊 Всего свежих: {len(all_news)}, после фильтра: {len(filtered_news)}")

        if not filtered_news:
            logger.info("😴 Нет подходящих новостей после фильтрации")
            return

        # --- ОЦЕНКА БАЛЛОВ ---
        for article in filtered_news:
            article["score"] = detect_score(article)

        # 🔧 АНТИСПАМ: теперь ТОЛЬКО ЛОГИРОВАНИЕ, новости НЕ ОТБРАСЫВАЮТСЯ.
        high_count = len([a for a in filtered_news if a["score"] >= 8])
        if high_count > 5:
            logger.info(f"⚠️ Много важных новостей ({high_count}), все будут опубликованы с интервалом {SCORE_DELAYS['high']}с.")

        # Сортировка: сначала высокий балл, потом свежесть
        filtered_news.sort(key=lambda x: (x["score"], x.get("published") or datetime.now()), reverse=True)

        # --- ДЕДУПЛИКАЦИЯ: убираем одну и ту же новость из разных источников ---
        filtered_news = deduplicate_articles(filtered_news, similarity_threshold=0.72)

        if MAX_POSTS_PER_RUN is not None:
            filtered_news = filtered_news[:MAX_POSTS_PER_RUN]

        # --- ПОЛИТИКА ПУБЛИКАЦИИ ---
        mode = publish_policy.get_mode()
        quiet = publish_policy.is_quiet_hours()
        logger.info(f"📊 Режим ленты: {mode.upper()}, тихие часы: {quiet}")

        # Очищаем старые publish_ задачи — иначе они накапливаются на дни вперёд
        old_jobs = [j for j in scheduler.get_jobs() if j.id.startswith("publish_")]
        if old_jobs:
            for j in old_jobs:
                scheduler.remove_job(j.id)
            logger.info(f"🧹 Очищено старых задач: {len(old_jobs)}")

        # Начинаем планирование с текущего времени
        base_time = datetime.now()
        current_time = base_time
        logger.info(f"📅 Начало планирования с: {current_time.strftime('%H:%M:%S')}")

        MIN_POST_INTERVAL = 20  # минимум 20 сек между любыми двумя постами
        MAX_QUEUE_MINUTES = 60  # максимум 60 минут очереди (FEAT-001: было 15)
        scheduled_count = 0
        skipped_yellow = 0
        yellow_articles = []  # FEAT-001: накапливаем yellow для дайджеста
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

            # 🛡️ Проверяем, не была ли новость уже опубликована ранее (по URL)
            if cache_manager.is_processed(link):
                logger.info(f"⏭ Уже опубликовано ранее (URL), пропускаем: {title}...")
                continue
            
            # 🛡️ Проверяем, не был ли уже опубликован ПОХОЖИЙ заголовок (дубли с разных источников)
            full_title = article.get("title", "")
            if cache_manager.is_title_processed(full_title, hours=12):
                logger.info(f"⏭ Уже опубликован похожий заголовок, пропускаем: {title}...")
                continue

            # FEAT-001: Yellow-новости отправляем в дайджест вместо пропуска
            if level == "yellow":
                yellow_articles.append(article)
                continue

            # Гарантируем минимальный интервал между постами
            min_interval = {"red": 30, "orange": 90, "yellow": 3600}.get(level, 30)
            run_time = current_time + timedelta(seconds=max(delay_seconds, min_interval))

            # Если очередь ушла дальше MAX_QUEUE_MINUTES — сбрасываем base_time
            # но current_time продолжает расти, чтобы сохранить интервал между постами
            queue_minutes = (run_time - datetime.now()).total_seconds() / 60
            if queue_minutes > MAX_QUEUE_MINUTES:
                # Сбрасываем: следующая новость будет через MIN_POST_INTERVAL от now
                current_time = datetime.now()
                run_time = current_time + timedelta(seconds=max(delay_seconds, MIN_POST_INTERVAL))
                logger.info(f"🔄 Очередь {queue_minutes:.0f} мин — сброс, продолжаем с {run_time.strftime('%H:%M:%S')}")

            scheduler.add_job(
                publish_single_article,
                trigger=DateTrigger(run_date=run_time),
                id=job_id,
                args=[article],
                replace_existing=True,
            )
            scheduled_count += 1
            actual_delay = int((run_time - datetime.now()).total_seconds())
            logger.info(f"⏳ [{level} {score}] delay={delay_seconds}, actual={actual_delay}с, run_time={run_time.strftime('%H:%M:%S')} → {title}...")

            current_time = run_time

        # FEAT-001: Отправляем дайджест yellow-новостей, если их накопилось достаточно
        if len(yellow_articles) >= 3:
            asyncio.create_task(_send_yellow_digest(yellow_articles))
        elif yellow_articles:
            # Если мало — публикуем по одной с большой задержкой
            for article in yellow_articles:
                current_time += timedelta(minutes=30)
                link_hash = cache_manager._generate_hash(article.get("link", ""))
                scheduler.add_job(
                    publish_single_article,
                    trigger=DateTrigger(run_date=current_time),
                    id=f"publish_{link_hash}",
                    args=[article],
                    replace_existing=True,
                )
                scheduled_count += 1

        logger.info(f"✅ В очередь добавлено: {scheduled_count}, yellow в дайджесте: {len(yellow_articles)}")

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в job_collect_news: {e}", exc_info=True)


# === Команды Telegram ===
def _build_start_keyboard() -> InlineKeyboardMarkup:
    """Inline-клавиатура для /start (FEAT-005)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📰 Собрать новости", callback_data="post_now")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
        ]
    )


@dp.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    await message.answer(
        "🤖 *Smart News Bot — 10‑балльная система*\n"
        "Собирает мировые новости, переводит и оценивает значимость.\n\n"
        f"⏱ Интервал сбора: {PUBLISH_INTERVAL_MINUTES} мин.\n"
        f"🔴 8–10 баллов → {SCORE_DELAYS['high']}с\n"
        f"🟠 5–7 баллов → {SCORE_DELAYS['medium']}с\n"
        f"🟢 1–4 балла → {SCORE_DELAYS['low']}с\n\n"
        "Или используй кнопки ниже:",
        reply_markup=_build_start_keyboard(),
    )


@dp.message(Command("post_now"))
async def cmd_post_now(message: types.Message) -> None:
    await message.answer("🔍 Запускаю внеочередной сбор...")
    asyncio.create_task(job_collect_news())
    await message.answer("✅ Задача запущена.")


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message) -> None:
    stats = cache_manager.get_processing_stats()
    scheduled_count = 0
    if scheduler is not None:
        jobs = scheduler.get_jobs()
        scheduled_count = sum(1 for j in jobs if j.id.startswith("publish_"))
    await message.answer(
        f"📊 *Статистика*\n"
        f"Всего в кэше: {stats.get('total', 0)}\n"
        f"Опубликовано: {stats.get('processed', 0)}\n"
        f"Ошибок: {stats.get('failed', 0)}\n"
        f"В очереди: {scheduled_count}\n"
        f"Сбор: {PUBLISH_INTERVAL_MINUTES} мин"
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    await cmd_start(message)


# === Callback-обработчики inline-клавиатуры (FEAT-005) ===
@dp.callback_query(F.data == "post_now")
async def cb_post_now(callback: types.CallbackQuery) -> None:
    await callback.answer("Запускаю сбор...")
    asyncio.create_task(job_collect_news())
    await callback.message.answer("✅ Внеочередной сбор запущен.")


@dp.callback_query(F.data == "stats")
async def cb_stats(callback: types.CallbackQuery) -> None:
    await callback.answer()
    stats = cache_manager.get_processing_stats()
    scheduled_count = 0
    if scheduler is not None:
        jobs = scheduler.get_jobs()
        scheduled_count = sum(1 for j in jobs if j.id.startswith("publish_"))
    await callback.message.answer(
        f"📊 *Статистика*\n"
        f"Всего в кэше: {stats.get('total', 0)}\n"
        f"Опубликовано: {stats.get('processed', 0)}\n"
        f"Ошибок: {stats.get('failed', 0)}\n"
        f"В очереди: {scheduled_count}\n"
        f"Сбор: {PUBLISH_INTERVAL_MINUTES} мин"
    )


@dp.callback_query(F.data == "help")
async def cb_help(callback: types.CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "🤖 *Smart News Bot — 10‑балльная система*\n"
        "Собирает мировые новости, переводит и оценивает значимость.\n\n"
        f"⏱ Интервал сбора: {PUBLISH_INTERVAL_MINUTES} мин.\n"
        f"🔴 8–10 баллов → {SCORE_DELAYS['high']}с\n"
        f"🟠 5–7 баллов → {SCORE_DELAYS['medium']}с\n"
        f"🟢 1–4 балла → {SCORE_DELAYS['low']}с\n\n"
        "*/post_now* — внеочередной сбор\n"
        "*/stats* — статистика\n"
        "*/help* — помощь"
    )


# === Pidfile для предотвращения двойного запуска (BUG-001) ===
PIDFILE = "/tmp/smart_news_bot.pid"


def _check_pidfile() -> bool:
    """Проверяет, не запущен ли уже другой инстанс бота."""
    if os.path.exists(PIDFILE):
        try:
            with open(PIDFILE, "r") as f:
                pid = int(f.read().strip())
            # Проверяем, существует ли процесс
            os.kill(pid, 0)
            logger.error(f"🚫 Бот уже запущен (PID {pid}). Завершение.")
            return False
        except (ValueError, OSError, ProcessLookupError):
            # PID-файл устарел — перезаписываем
            pass
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: os.remove(PIDFILE) if os.path.exists(PIDFILE) else None)
    return True


# === Запуск ===
async def main() -> None:
    if not _check_pidfile():
        return
    global scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        job_collect_news,
        trigger=IntervalTrigger(minutes=PUBLISH_INTERVAL_MINUTES),
        id="collect_news",
        replace_existing=True,
        next_run_time=datetime.now(),
    )
    scheduler.start()
    
    # Очищаем ВСЕ старые publish-задачи при запуске — иначе они копятся на дни
    removed = 0
    for job in list(scheduler.get_jobs()):
        if job.id.startswith("publish_"):
            scheduler.remove_job(job.id)
            removed += 1
    if removed > 0:
        logger.info(f"🧹 Очищено {removed} старых задач из очереди")
    
    logger.info(
        f"⏱ Планировщик запущен. Интервалы: 8-10→{SCORE_DELAYS['high']}с, "
        f"5-7→{SCORE_DELAYS['medium']}с, 1-4→{SCORE_DELAYS['low']}с"
    )

    # Запускаем health-check в фоне (FEAT-004)
    asyncio.create_task(periodic_health_check(bot, interval_minutes=15))
    logger.info("🏥 Health-check запущен (интервал: 15 мин)")

    try:
        if config.WEBHOOK_URL:
            # FEAT-002: Webhook mode
            from aiohttp import web
            
            async def handle_webhook(request):
                update = types.Update.model_validate(await request.json())
                await dp.feed_update(bot, update)
                return web.Response()
            
            app = web.Application()
            app.router.add_post(config.WEBHOOK_PATH, handle_webhook)
            
            # Устанавливаем webhook
            await bot.set_webhook(
                url=f"{config.WEBHOOK_URL}{config.WEBHOOK_PATH}",
                drop_pending_updates=True
            )
            logger.info(f"🌐 Webhook установлен: {config.WEBHOOK_URL}{config.WEBHOOK_PATH}")
            
            # Запускаем сервер
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', config.WEBHOOK_PORT)
            await site.start()
            logger.info(f"🌐 Сервер webhook запущен на порту {config.WEBHOOK_PORT}")
            
            # Держим бота живым
            while True:
                await asyncio.sleep(3600)
        else:
            # Polling mode (default)
            logger.info("📡 Запуск в режиме polling...")
            await dp.start_polling(bot, skip_updates=True)
    finally:
        if config.WEBHOOK_URL:
            await bot.delete_webhook()
            logger.info("🌐 Webhook удалён")
        if scheduler:
            scheduler.shutdown()
        await bot.session.close()
        await asyncio.sleep(0.5)
        await asyncio.get_event_loop().shutdown_asyncgens()
        cache_manager.close()
        logger.info("🛑 Бот остановлен, ресурсы освобождены")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Завершение по Ctrl+C")