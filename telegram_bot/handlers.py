"""
Telegram handlers для Smart News Bot.
P1-001: Вынесены из bot_runner.py.

Регистрация через register_handlers(dp, **dependencies).
"""

import asyncio
import logging
from typing import Any, Dict

from aiogram import Dispatcher, F, types
from aiogram.filters import Command

from telegram_bot.keyboards import (
    build_minscore_keyboard,
    build_settings_keyboard,
    build_start_keyboard,
)

logger = logging.getLogger(__name__)

# Зависимости, которые будут переданы при регистрации
_deps: Dict[str, Any] = {}


def _is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом."""
    admin_id = _deps.get("ADMIN_ID")
    return user_id == admin_id


async def _require_admin(message: types.Message) -> bool:
    """Отправляет отказ, если пользователь не админ."""
    if not _is_admin(message.from_user.id):
        await message.answer("🚫 Доступ запрещён. Этот бот только для администратора.")
        logger.warning(f"Попытка доступа от неавторизованного пользователя: {message.from_user.id}")
        return False
    return True


async def _require_admin_callback(callback: types.CallbackQuery) -> bool:
    """Отправляет отказ, если пользователь не админ."""
    if not _is_admin(callback.from_user.id):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        logger.warning(
            f"Попытка доступа от неавторизованного пользователя: {callback.from_user.id}"
        )
        return False
    return True


# === Message handlers ===


async def cmd_start(message: types.Message) -> None:
    if not await _require_admin(message):
        return
    config = _deps["config"]
    score_delays = _deps["SCORE_DELAYS"]
    await message.answer(
        "🤖 *Smart News Bot — 10‑балльная система*\n"
        "Собирает мировые новости, переводит и оценивает значимость.\n\n"
        f"⏱ Интервал сбора: {config.PUBLISH_INTERVAL_MINUTES} мин.\n"
        f"🔴 8–10 баллов → {score_delays['high']}с\n"
        f"🟠 5–7 баллов → {score_delays['medium']}с\n"
        f"🟢 1–4 балла → {score_delays['low']}с\n\n"
        "Или используй кнопки ниже:",
        reply_markup=build_start_keyboard(),
    )


async def cmd_post_now(message: types.Message) -> None:
    if not await _require_admin(message):
        return
    await message.answer("🔍 Запускаю внеочередной сбор...")
    job_collect_news = _deps["job_collect_news"]
    asyncio.create_task(job_collect_news())
    await message.answer("✅ Задача запущена.")


async def cmd_stats(message: types.Message) -> None:
    if not await _require_admin(message):
        return
    cache_manager = _deps["cache_manager"]
    scheduler = _deps["scheduler"]
    config = _deps["config"]
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
        f"Сбор: {config.PUBLISH_INTERVAL_MINUTES} мин"
    )


async def cmd_top(message: types.Message) -> None:
    """Топ-5 новостей за неделю по реакциям."""
    if not await _require_admin(message):
        return
    reactions_manager = _deps["reactions_manager"]
    top = reactions_manager.get_top_articles(days=7, limit=5)
    if not top:
        await message.answer("📭 Пока нет реакций за неделю.")
        return

    lines = ["🏆 *Топ новостей за неделю*\n"]
    for i, article in enumerate(top, 1):
        title = article.get("article_title", "Без заголовка")[:60]
        likes = article.get("likes", 0)
        dislikes = article.get("dislikes", 0)
        saves = article.get("saves", 0)
        source = article.get("source_tag", "News")
        score = article.get("score", 0)
        lines.append(
            f"{i}. *{title}*\n"
            f"   👍 {likes}  👎 {dislikes}  💾 {saves} | #{source} | score: {score}\n"
        )
    await message.answer("\n".join(lines), parse_mode="Markdown")


async def cmd_analytics(message: types.Message) -> None:
    """Показать аналитику доставки и метрики."""
    if not await _require_admin(message):
        return
    analytics_manager = _deps["analytics_manager"]
    analytics_manager.record_user_session(str(message.from_user.id))
    report = analytics_manager.get_analytics_report()
    d24 = report["delivery_24h"]
    d7 = report["delivery_7d"]
    e24 = report["errors_24h"]
    e7 = report["errors_7d"]
    top = report["top_sources"]

    lines = [
        "📈 *Аналитика Smart News Bot*\n",
        f"👥 *Аудитория:*",
        f"  DAU (1д): {report['dau']}",
        f"  MAU (30д): {report['mau']}",
        "",
        f"📬 *Доставка (24ч):*",
        f"  Отправлено: {d24.get('total_sent', 0)}",
        f"  Доставлено: {d24.get('delivered', 0)}",
        f"  Успешность: {d24.get('delivery_rate', 0.0)}%",
        f"  С фото: {d24.get('with_image', 0)} (fallback: {d24.get('fallback_images', 0)})",
        "",
        f"📬 *Доставка (7д):*",
        f"  Отправлено: {d7.get('total_sent', 0)}",
        f"  Доставлено: {d7.get('delivered', 0)}",
        f"  Успешность: {d7.get('delivery_rate', 0.0)}%",
        "",
        f"❌ *Ошибки (24ч):*",
        f"  Всего: {e24.get('total_errors', 0)}",
        f"  FLOOD_WAIT: {e24.get('flood_wait', 0)}",
        f"  API errors: {e24.get('api_errors', 0)}",
        f"  Network: {e24.get('network_errors', 0)}",
        "",
        f"❌ *Ошибки (7д):*",
        f"  Всего: {e7.get('total_errors', 0)}",
        f"  FLOOD_WAIT: {e7.get('flood_wait', 0)}",
    ]
    if top:
        lines.extend(["", "🏆 *Топ источников (7д):*"])
        for i, src in enumerate(top[:5], 1):
            avg = round(src.get("avg_score", 0) or 0, 1)
            lines.append(f"  {i}. {src['source_tag']}: {src['posts']} постов (avg score: {avg})")
    else:
        lines.extend(["", "🏆 *Топ источников:* пока нет данных"])
    lines.append("\n_Обновляется в реальном времени_")
    await message.answer("\n".join(lines), parse_mode="Markdown")


async def cmd_ab_results(message: types.Message) -> None:
    """Показать результаты A/B тестов."""
    if not await _require_admin(message):
        return
    ab_testing_manager = _deps["ab_testing_manager"]
    report = ab_testing_manager.get_report_text(days=7)
    await message.answer(report, parse_mode="HTML")


async def cmd_ab_winner(message: types.Message) -> None:
    """P2-003: Показать статус winner или сбросить."""
    if not await _require_admin(message):
        return
    ab_testing_manager = _deps["ab_testing_manager"]
    args = message.text.split()[1:] if message.text else []

    if args and args[0].lower() == "reset":
        had = ab_testing_manager.reset_winner()
        if had:
            await message.answer(
                "✅ Winner state сброшен. A/B тесты возобновлены с равномерным распределением."
            )
        else:
            await message.answer("ℹ️ Winner state не был установлен. Нечего сбрасывать.")
        return

    status = ab_testing_manager.get_winner_status_text()
    await message.answer(status, parse_mode="HTML")


async def cmd_metrics(message: types.Message) -> None:
    """P2-004: Показать метрики latency и queue depth."""
    if not await _require_admin(message):
        return
    from utils.metrics import collector

    report = collector.get_report_text()
    await message.answer(report, parse_mode="HTML")


async def cmd_ai_cost(message: types.Message) -> None:
    """Показать стоимость AI-запросов."""
    if not await _require_admin(message):
        return
    analytics_manager = _deps["analytics_manager"]
    daily = analytics_manager.get_ai_cost(days=1)
    weekly = analytics_manager.get_ai_cost(days=7)
    monthly = analytics_manager.get_ai_cost(days=30)
    by_provider = analytics_manager.get_ai_cost_by_provider(days=7)

    lines = [
        "🤖 *Стоимость AI-запросов*\n",
        f"*За сегодня:*",
        f"  Запросов: {daily['requests']}",
        f"  Токены: {daily['tokens_input']:,} in / {daily['tokens_output']:,} out",
        f"  Стоимость: ${daily['cost_usd']:.4f}",
        "",
        f"*За неделю:*",
        f"  Запросов: {weekly['requests']}",
        f"  Стоимость: ${weekly['cost_usd']:.4f}",
        "",
        f"*За месяц:*",
        f"  Запросов: {monthly['requests']}",
        f"  Стоимость: ${monthly['cost_usd']:.4f}",
    ]
    if by_provider:
        lines.extend(["", "*По провайдерам (7д):*"])
        for p in by_provider:
            lines.append(
                f"  {p['provider']}/{p['model']}: {p['requests']} req, ${p['total_cost']:.4f}"
            )
    alert, spent = analytics_manager.check_ai_cost_alert(daily_budget=10.0)
    if alert:
        lines.extend(["", f"🚨 *АЛЕРТ:* ${spent:.2f} из $10.00 дневного лимита!"])
    lines.append("\n_Обновляется в реальном времени_")
    await message.answer("\n".join(lines), parse_mode="Markdown")


async def cmd_help(message: types.Message) -> None:
    if not await _require_admin(message):
        return
    await cmd_start(message)


# === FEAT-018: Команды персонализации ===


async def cmd_topic(message: types.Message) -> None:
    """Подписаться на тему: /topic крипто"""
    if not await _require_admin(message):
        return
    cache_manager = _deps["cache_manager"]
    chat_id = str(message.chat.id)
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "📝 Укажи тему для подписки:\n"
            "`/topic крипто` — подписаться на крипто-новости\n\n"
            "Твои текущие подписки: /mytopics"
        )
        return
    topic = args[1].strip().lower()
    prefs = cache_manager.get_user_prefs(chat_id)
    preferred = prefs.get("preferred_topics", [])
    if topic in preferred:
        await message.answer(f"✅ Ты уже подписан на тему «{topic}»")
        return
    preferred.append(topic)
    cache_manager.set_user_prefs(chat_id, preferred_topics=preferred)
    await message.answer(
        f"✅ Подписка на «{topic}» оформлена!\n\nТеперь новости по этой теме будут получать +2 к баллу."
    )


async def cmd_notopic(message: types.Message) -> None:
    """Отписаться от темы: /notopic крипто"""
    if not await _require_admin(message):
        return
    cache_manager = _deps["cache_manager"]
    chat_id = str(message.chat.id)
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "📝 Укажи тему для отписки:\n"
            "`/notopic крипто` — отписаться от крипто-новостей\n\n"
            "Твои текущие подписки: /mytopics"
        )
        return
    topic = args[1].strip().lower()
    prefs = cache_manager.get_user_prefs(chat_id)
    preferred = prefs.get("preferred_topics", [])
    if topic not in preferred:
        await message.answer(f"❌ Ты не подписан на тему «{topic}»")
        return
    preferred.remove(topic)
    cache_manager.set_user_prefs(chat_id, preferred_topics=preferred)
    await message.answer(f"✅ Подписка на «{topic}» отменена.")


async def cmd_block(message: types.Message) -> None:
    """Заблокировать тему: /block спорт"""
    if not await _require_admin(message):
        return
    cache_manager = _deps["cache_manager"]
    chat_id = str(message.chat.id)
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "📝 Укажи тему для блокировки:\n"
            "`/block спорт` — не показывать спорт\n"
            "`/block кино` — не показывать кино\n\n"
            "Заблокированные темы: /mytopics"
        )
        return
    topic = args[1].strip().lower()
    prefs = cache_manager.get_user_prefs(chat_id)
    blocked = prefs.get("blocked_topics", [])
    if topic in blocked:
        await message.answer(f"✅ Тема «{topic}» уже заблокирована")
        return
    blocked.append(topic)
    cache_manager.set_user_prefs(chat_id, blocked_topics=blocked)
    await message.answer(
        f"🚫 Тема «{topic}» заблокирована.\n\nНовости с этой темой не будут показываться."
    )


async def cmd_unblock(message: types.Message) -> None:
    """Разблокировать тему: /unblock спорт"""
    if not await _require_admin(message):
        return
    cache_manager = _deps["cache_manager"]
    chat_id = str(message.chat.id)
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "📝 Укажи тему для разблокировки:\n"
            "`/unblock спорт` — снова показывать спорт\n\n"
            "Заблокированные темы: /mytopics"
        )
        return
    topic = args[1].strip().lower()
    prefs = cache_manager.get_user_prefs(chat_id)
    blocked = prefs.get("blocked_topics", [])
    if topic not in blocked:
        await message.answer(f"❌ Тема «{topic}» не заблокирована")
        return
    blocked.remove(topic)
    cache_manager.set_user_prefs(chat_id, blocked_topics=blocked)
    await message.answer(f"✅ Тема «{topic}» разблокирована.")


async def cmd_mytopics(message: types.Message) -> None:
    """Показать текущие подписки и блокировки."""
    if not await _require_admin(message):
        return
    cache_manager = _deps["cache_manager"]
    chat_id = str(message.chat.id)
    prefs = cache_manager.get_user_prefs(chat_id)
    preferred = prefs.get("preferred_topics", [])
    blocked = prefs.get("blocked_topics", [])
    min_score = prefs.get("min_score", 1)
    lines = ["📋 *Твои настройки:*\n"]
    lines.append(f"✅ Подписки: {', '.join(preferred) or 'нет (все темы)'}")
    lines.append(f"🚫 Блокировки: {', '.join(blocked) or 'нет'}")
    lines.append(f"📊 Минимальный балл: {min_score}")
    lines.append("\n*Команды:*")
    lines.append("`/topic [тема]` — подписаться")
    lines.append("`/notopic [тема]` — отписаться")
    lines.append("`/block [тема]` — заблокировать")
    lines.append("`/unblock [тема]` — разблокировать")
    lines.append("`/minscore [1-10]` — минимальный балл")
    await message.answer("\n".join(lines))


async def cmd_minscore(message: types.Message) -> None:
    """Установить минимальный балл: /minscore 5"""
    if not await _require_admin(message):
        return
    cache_manager = _deps["cache_manager"]
    chat_id = str(message.chat.id)
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        prefs = cache_manager.get_user_prefs(chat_id)
        current = prefs.get("min_score", 1)
        await message.answer(
            f"📊 Текущий минимальный балл: {current}\n\n"
            "Укажи новое значение (1-10):\n"
            "`/minscore 5` — показывать только новости от 5 баллов\n"
            "`/minscore 1` — показывать все новости"
        )
        return
    try:
        score = int(args[1].strip())
        if score < 1 or score > 10:
            raise ValueError
    except ValueError:
        await message.answer("❌ Укажи число от 1 до 10")
        return
    cache_manager.set_user_prefs(chat_id, min_score=score)
    await message.answer(
        f"✅ Минимальный балл установлен: {score}\n\nТеперь будут показываться только новости от {score} баллов."
    )


async def cmd_settings(message: types.Message) -> None:
    """Открыть меню настроек (FEAT-019)."""
    if not await _require_admin(message):
        return
    chat_id = str(message.chat.id)
    await message.answer(
        "⚙️ *Настройки персонализации*\n\n"
        "Здесь можно выбрать интересующие темы, заблокировать нежелательные "
        "и установить минимальный балл для новостей.",
        reply_markup=build_settings_keyboard(chat_id),
    )


async def cmd_health(message: types.Message) -> None:
    """Показать статус health-check с probes внешних API (P1-004)."""
    if not await _require_admin(message):
        return
    health_checker = _deps["health_checker"]
    source_tracker = _deps["source_tracker"]
    status = await health_checker.get_full_status()
    lines = ["🏥 *Health Check Status*\n"]
    lines.append("✅ Статус: *ЗДОРОВ*" if status["healthy"] else "🚨 Статус: *ПРОБЛЕМЫ*")
    last_publish = status.get("last_publish")
    lines.append(f"🕐 Последняя публикация: {last_publish[:19] if last_publish else 'нет'}")
    lines.append(f"❌ Ошибок за час: {status['errors_last_hour']}")
    for check_name, check_data in status["checks"].items():
        ok = check_data.get("ok", True)
        icon = "✅" if ok else "🚨"
        if check_name == "silence":
            minutes = check_data.get("minutes", 0)
            threshold = check_data.get("threshold", 30)
            lines.append(f"{icon} Молчание: {minutes:.0f} мин (порог {threshold})")
        elif check_name == "errors":
            count = check_data.get("count", 0)
            threshold = check_data.get("threshold", 10)
            lines.append(f"{icon} Ошибки: {count} (порог {threshold})")

    # P1-004: Статус внешних API
    api_checks = status.get("api_checks", {})
    if api_checks:
        lines.append("\n🌐 *Внешние API:*")
        api_labels = {
            "telegram": "📱 Telegram",
            "routerai": "🤖 RouterAI",
            "yandex_translate": "🌐 Yandex Translate",
            "searxng": "🔍 SearXNG",
        }
        for api_name, api_result in api_checks.items():
            ok = api_result.get("ok", False)
            icon = "✅" if ok else "🚨"
            label = api_labels.get(api_name, api_name)
            if ok:
                lines.append(f"  {icon} {label}")
            else:
                error = api_result.get("error", "unknown")
                lines.append(f"  {icon} {label}: {error}")

    source_statuses = source_tracker.get_all_statuses()
    if source_statuses:
        lines.append("\n📡 *Источники:*")
        for src in source_statuses:
            icon = {"ok": "✅", "degraded": "⚠️", "offline": "🚫"}.get(src["status"], "❓")
            lines.append(f"  {icon} {src['source_tag']}: {src['status']}")
            if src["consecutive_errors"] > 0:
                lines.append(f"     Ошибок подряд: {src['consecutive_errors']}")
    lines.append("\nПроверка каждые 15 мин.")
    await message.answer("\n".join(lines))


# === Callback handlers ===


async def cb_post_now(callback: types.CallbackQuery) -> None:
    if not await _require_admin_callback(callback):
        return
    await callback.answer("Запускаю сбор...", show_alert=True)
    job_collect_news = _deps["job_collect_news"]
    asyncio.create_task(job_collect_news())
    await callback.message.answer("✅ Внеочередной сбор запущен.")


async def cb_stats(callback: types.CallbackQuery) -> None:
    if not await _require_admin_callback(callback):
        return
    await callback.answer()
    cache_manager = _deps["cache_manager"]
    scheduler = _deps["scheduler"]
    config = _deps["config"]
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
        f"Сбор: {config.PUBLISH_INTERVAL_MINUTES} мин"
    )


async def cb_top(callback: types.CallbackQuery) -> None:
    if not await _require_admin_callback(callback):
        return
    await callback.answer()
    reactions_manager = _deps["reactions_manager"]
    top = reactions_manager.get_top_articles(days=7, limit=5)
    if not top:
        await callback.message.answer("📭 Пока нет реакций за неделю.")
        return

    lines = ["🏆 *Топ новостей за неделю*\n"]
    for i, article in enumerate(top, 1):
        title = article.get("article_title", "Без заголовка")[:60]
        likes = article.get("likes", 0)
        dislikes = article.get("dislikes", 0)
        saves = article.get("saves", 0)
        source = article.get("source_tag", "News")
        score = article.get("score", 0)
        lines.append(
            f"{i}. *{title}*\n"
            f"   👍 {likes}  👎 {dislikes}  💾 {saves} | #{source} | score: {score}\n"
        )
    await callback.message.answer("\n".join(lines), parse_mode="Markdown")


async def cb_analytics(callback: types.CallbackQuery) -> None:
    if not await _require_admin_callback(callback):
        return
    await callback.answer()
    analytics_manager = _deps["analytics_manager"]
    analytics_manager.record_user_session(str(callback.from_user.id))
    report = analytics_manager.get_analytics_report()
    d24 = report["delivery_24h"]
    d7 = report["delivery_7d"]
    e24 = report["errors_24h"]
    e7 = report["errors_7d"]
    top = report["top_sources"]

    lines = [
        "📈 *Аналитика Smart News Bot*\n",
        f"👥 *Аудитория:*",
        f"  DAU (1д): {report['dau']}",
        f"  MAU (30д): {report['mau']}",
        "",
        f"📬 *Доставка (24ч):*",
        f"  Отправлено: {d24.get('total_sent', 0)}",
        f"  Доставлено: {d24.get('delivered', 0)}",
        f"  Успешность: {d24.get('delivery_rate', 0.0)}%",
        f"  С фото: {d24.get('with_image', 0)} (fallback: {d24.get('fallback_images', 0)})",
        "",
        f"📬 *Доставка (7д):*",
        f"  Отправлено: {d7.get('total_sent', 0)}",
        f"  Доставлено: {d7.get('delivered', 0)}",
        f"  Успешность: {d7.get('delivery_rate', 0.0)}%",
        "",
        f"❌ *Ошибки (24ч):*",
        f"  Всего: {e24.get('total_errors', 0)}",
        f"  FLOOD_WAIT: {e24.get('flood_wait', 0)}",
        f"  API errors: {e24.get('api_errors', 0)}",
        f"  Network: {e24.get('network_errors', 0)}",
        "",
        f"❌ *Ошибки (7д):*",
        f"  Всего: {e7.get('total_errors', 0)}",
        f"  FLOOD_WAIT: {e7.get('flood_wait', 0)}",
    ]
    if top:
        lines.extend(["", "🏆 *Топ источников (7д):*"])
        for i, src in enumerate(top[:5], 1):
            avg = round(src.get("avg_score", 0) or 0, 1)
            lines.append(f"  {i}. {src['source_tag']}: {src['posts']} постов (avg score: {avg})")
    else:
        lines.extend(["", "🏆 *Топ источников:* пока нет данных"])
    lines.append("\n_Обновляется в реальном времени_")
    await callback.message.answer("\n".join(lines), parse_mode="Markdown")


async def cb_ab_results(callback: types.CallbackQuery) -> None:
    if not await _require_admin_callback(callback):
        return
    await callback.answer()
    ab_testing_manager = _deps["ab_testing_manager"]
    report = ab_testing_manager.get_report_text(days=7)
    await callback.message.answer(report, parse_mode="HTML")


async def cb_ab_winner(callback: types.CallbackQuery) -> None:
    if not await _require_admin_callback(callback):
        return
    await callback.answer()
    ab_testing_manager = _deps["ab_testing_manager"]
    status = ab_testing_manager.get_winner_status_text()
    await callback.message.answer(status, parse_mode="HTML")


async def cb_metrics(callback: types.CallbackQuery) -> None:
    if not await _require_admin_callback(callback):
        return
    await callback.answer()
    from utils.metrics import collector

    report = collector.get_report_text()
    await callback.message.answer(report, parse_mode="HTML")


async def cb_ai_cost(callback: types.CallbackQuery) -> None:
    if not await _require_admin_callback(callback):
        return
    await callback.answer()
    analytics_manager = _deps["analytics_manager"]
    daily = analytics_manager.get_ai_cost(days=1)
    weekly = analytics_manager.get_ai_cost(days=7)
    monthly = analytics_manager.get_ai_cost(days=30)
    by_provider = analytics_manager.get_ai_cost_by_provider(days=7)

    lines = [
        "🤖 *Стоимость AI-запросов*\n",
        f"*За сегодня:*",
        f"  Запросов: {daily['requests']}",
        f"  Токены: {daily['tokens_input']:,} in / {daily['tokens_output']:,} out",
        f"  Стоимость: ${daily['cost_usd']:.4f}",
        "",
        f"*За неделю:*",
        f"  Запросов: {weekly['requests']}",
        f"  Стоимость: ${weekly['cost_usd']:.4f}",
        "",
        f"*За месяц:*",
        f"  Запросов: {monthly['requests']}",
        f"  Стоимость: ${monthly['cost_usd']:.4f}",
    ]
    if by_provider:
        lines.extend(["", "*По провайдерам (7д):*"])
        for p in by_provider:
            lines.append(
                f"  {p['provider']}/{p['model']}: {p['requests']} req, ${p['total_cost']:.4f}"
            )
    alert, spent = analytics_manager.check_ai_cost_alert(daily_budget=10.0)
    if alert:
        lines.extend(["", f"🚨 *АЛЕРТ:* ${spent:.2f} из $10.00 дневного лимита!"])
    lines.append("\n_Обновляется в реальном времени_")
    await callback.message.answer("\n".join(lines), parse_mode="Markdown")


async def cb_help(callback: types.CallbackQuery) -> None:
    if not await _require_admin_callback(callback):
        return
    await callback.answer()
    config = _deps["config"]
    score_delays = _deps["SCORE_DELAYS"]
    await callback.message.answer(
        "🤖 *Smart News Bot — 10‑балльная система*\n"
        "Собирает мировые новости, переводит и оценивает значимость.\n\n"
        f"⏱ Интервал сбора: {config.PUBLISH_INTERVAL_MINUTES} мин.\n"
        f"🔴 8–10 баллов → {score_delays['high']}с\n"
        f"🟠 5–7 баллов → {score_delays['medium']}с\n"
        f"🟢 1–4 балла → {score_delays['low']}с\n\n"
        "*Команды:*\n"
        "*/start* — главное меню\n"
        "*/post_now* — внеочередной сбор\n"
        "*/stats* — статистика\n"
        "*/top* — топ новостей за неделю\n"
        "*/analytics* — аналитика доставки\n"
        "*/ab_results* — A/B тесты\n"
        "*/ab_winner* — статус winner\n"
        "*/metrics* — метрики latency\n"
        "*/ai_cost* — стоимость AI\n"
        "*/settings* — настройки\n"
        "*/health* — health check\n"
        "*/help* — помощь"
    )


async def cb_start_menu(callback: types.CallbackQuery) -> None:
    if not await _require_admin_callback(callback):
        return
    await callback.answer()
    config = _deps["config"]
    score_delays = _deps["SCORE_DELAYS"]
    await callback.message.edit_text(
        "🤖 *Smart News Bot — 10‑балльная система*\n"
        "Собирает мировые новости, переводит и оценивает значимость.\n\n"
        f"⏱ Интервал сбора: {config.PUBLISH_INTERVAL_MINUTES} мин.\n"
        f"🔴 8–10 баллов → {score_delays['high']}с\n"
        f"🟠 5–7 баллов → {score_delays['medium']}с\n"
        f"🟢 1–4 балла → {score_delays['low']}с\n\n"
        "Или используй кнопки ниже:",
        reply_markup=build_start_keyboard(),
    )


async def cb_settings_menu(callback: types.CallbackQuery) -> None:
    if not await _require_admin_callback(callback):
        return
    await callback.answer()
    cache_manager = _deps["cache_manager"]
    chat_id = str(callback.message.chat.id)
    prefs = cache_manager.get_user_prefs(chat_id)
    preferred = prefs.get("preferred_topics", [])
    blocked = prefs.get("blocked_topics", [])
    min_score = prefs.get("min_score", 1)
    lines = ["⚙️ *Настройки персонализации*\n"]
    if preferred:
        lines.append(f"✅ Подписки: {', '.join(preferred)}")
    if blocked:
        lines.append(f"🚫 Блокировки: {', '.join(blocked)}")
    lines.append(f"📊 Минимальный балл: {min_score}")
    lines.append("\nНажми на кнопки ниже, чтобы изменить:")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=build_settings_keyboard(chat_id),
    )


async def cb_topic_toggle(callback: types.CallbackQuery) -> None:
    if not await _require_admin_callback(callback):
        return
    cache_manager = _deps["cache_manager"]
    chat_id = str(callback.message.chat.id)
    topic = callback.data.split(":", 1)[1]
    prefs = cache_manager.get_user_prefs(chat_id)
    preferred = prefs.get("preferred_topics", [])
    if topic in preferred:
        preferred.remove(topic)
        await callback.answer(f"❌ Отписались от «{topic}»", show_alert=True)
    else:
        preferred.append(topic)
        await callback.answer(f"✅ Подписались на «{topic}»", show_alert=True)
    cache_manager.set_user_prefs(chat_id, preferred_topics=preferred)
    await callback.message.edit_reply_markup(reply_markup=build_settings_keyboard(chat_id))


async def cb_block_toggle(callback: types.CallbackQuery) -> None:
    if not await _require_admin_callback(callback):
        return
    cache_manager = _deps["cache_manager"]
    chat_id = str(callback.message.chat.id)
    topic = callback.data.split(":", 1)[1]
    prefs = cache_manager.get_user_prefs(chat_id)
    blocked = prefs.get("blocked_topics", [])
    if topic in blocked:
        blocked.remove(topic)
        await callback.answer(f"✅ Разблокировали «{topic}»", show_alert=True)
    else:
        blocked.append(topic)
        await callback.answer(f"🚫 Заблокировали «{topic}»", show_alert=True)
    cache_manager.set_user_prefs(chat_id, blocked_topics=blocked)
    await callback.message.edit_reply_markup(reply_markup=build_settings_keyboard(chat_id))


async def cb_minscore_menu(callback: types.CallbackQuery) -> None:
    if not await _require_admin_callback(callback):
        return
    await callback.answer()
    cache_manager = _deps["cache_manager"]
    chat_id = str(callback.message.chat.id)
    prefs = cache_manager.get_user_prefs(chat_id)
    current = prefs.get("min_score", 1)
    await callback.message.edit_text(
        f"📊 *Минимальный балл новостей*\n\n"
        f"Сейчас: {current}\n\n"
        "Выбери минимальный балл (1 — все новости, 10 — только самые важные):",
        reply_markup=build_minscore_keyboard(current),
    )


async def cb_minscore_set(callback: types.CallbackQuery) -> None:
    if not await _require_admin_callback(callback):
        return
    cache_manager = _deps["cache_manager"]
    chat_id = str(callback.message.chat.id)
    score = int(callback.data.split(":", 1)[1])
    cache_manager.set_user_prefs(chat_id, min_score=score)
    await callback.answer(f"📊 Минимальный балл: {score}", show_alert=True)
    await cb_minscore_menu(callback)


async def cb_reaction(callback: types.CallbackQuery) -> None:
    """Обрабатывает нажатие на кнопки реакций под постами."""
    try:
        parts = callback.data.split(":")
        if len(parts) != 3:
            await callback.answer("❌ Ошибка формата")
            return
        _, reaction_type, message_id_str = parts
        message_id = int(message_id_str)
        user_id = str(callback.from_user.id)
        reactions_manager = _deps["reactions_manager"]
        stats = reactions_manager.add_reaction(message_id, user_id, reaction_type)
        if "error" in stats:
            await callback.answer(f"❌ {stats['error']}")
            return
        action = stats.get("action", "added")
        reaction_type = stats.get("reaction_type", reaction_type)
        like_count = stats.get("like", 0)
        dislike_count = stats.get("dislike", 0)
        save_count = stats.get("save", 0)
        action_text = {"like": "👍", "dislike": "👎", "save": "💾"}.get(reaction_type, "")
        if action == "added":
            await callback.answer(f"{action_text} Реакция добавлена")
        else:
            await callback.answer(f"{action_text} Реакция убрана")
        from telegram_bot.poster import _build_reactions_keyboard

        await callback.message.edit_reply_markup(reply_markup=_build_reactions_keyboard(message_id))
    except Exception as e:
        logger.error(f"Ошибка обработки реакции: {e}", exc_info=True)
        await callback.answer("❌ Ошибка обработки реакции")


# === Регистрация ===


def register_handlers(dp: Dispatcher, **dependencies) -> None:
    """Регистрирует все handlers в диспетчере."""
    _deps.update(dependencies)

    # Message handlers
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_post_now, Command("post_now"))
    dp.message.register(cmd_stats, Command("stats"))
    dp.message.register(cmd_top, Command("top"))
    dp.message.register(cmd_analytics, Command("analytics"))
    dp.message.register(cmd_ab_results, Command("ab_results"))
    dp.message.register(cmd_ab_winner, Command("ab_winner"))
    dp.message.register(cmd_metrics, Command("metrics"))
    dp.message.register(cmd_ai_cost, Command("ai_cost"))
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_topic, Command("topic"))
    dp.message.register(cmd_notopic, Command("notopic"))
    dp.message.register(cmd_block, Command("block"))
    dp.message.register(cmd_unblock, Command("unblock"))
    dp.message.register(cmd_mytopics, Command("mytopics"))
    dp.message.register(cmd_minscore, Command("minscore"))
    dp.message.register(cmd_settings, Command("settings"))
    dp.message.register(cmd_health, Command("health"))

    # Callback handlers
    dp.callback_query.register(cb_post_now, F.data == "post_now")
    dp.callback_query.register(cb_stats, F.data == "stats")
    dp.callback_query.register(cb_top, F.data == "top")
    dp.callback_query.register(cb_analytics, F.data == "analytics")
    dp.callback_query.register(cb_ab_results, F.data == "ab_results")
    dp.callback_query.register(cb_ab_winner, F.data == "ab_winner")
    dp.callback_query.register(cb_metrics, F.data == "metrics")
    dp.callback_query.register(cb_ai_cost, F.data == "ai_cost")
    dp.callback_query.register(cb_help, F.data == "help")
    dp.callback_query.register(cb_start_menu, F.data == "start_menu")
    dp.callback_query.register(cb_settings_menu, F.data == "settings_menu")
    dp.callback_query.register(cb_topic_toggle, F.data.startswith("topic_toggle:"))
    dp.callback_query.register(cb_block_toggle, F.data.startswith("block_toggle:"))
    dp.callback_query.register(cb_minscore_menu, F.data == "minscore_menu")
    dp.callback_query.register(cb_minscore_set, F.data.startswith("minscore_set:"))
    dp.callback_query.register(cb_reaction, F.data.startswith("react:"))
