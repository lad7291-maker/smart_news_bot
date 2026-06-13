"""
Автоматическое обновление контекста мировых лидеров (P3-004).
Парсит Wikipedia для актуальных должностей.
Fallback на статичный список при ошибке.
"""

import asyncio
import re
from datetime import datetime
from typing import Dict, Optional

import httpx

from ai_core.world_leaders_context import ALL_LEADERS, get_leaders_context
from utils.logger import logger

# Карта: страна/должность → Wikipedia страница + поле для парсинга
WIKI_PAGES = {
    ("USA", "president"): ("President_of_the_United_States", "incumbent"),
    ("USA", "vice_president"): ("Vice_President_of_the_United_States", "incumbent"),
    ("Russia", "president"): ("President_of_Russia", "incumbent"),
    ("Russia", "prime_minister"): ("Prime_Minister_of_Russia", "incumbent"),
    ("China", "president"): ("President_of_China", "incumbent"),
    ("United Kingdom", "prime_minister"): ("Prime_Minister_of_the_United_Kingdom", "incumbent"),
    ("India", "prime_minister"): ("Prime_Minister_of_India", "incumbent"),
    ("Ukraine", "president"): ("President_of_Ukraine", "incumbent"),
    ("Israel", "prime_minister"): ("Prime_Minister_of_Israel", "incumbent"),
    ("Japan", "prime_minister"): ("Prime_Minister_of_Japan", "incumbent"),
    ("Brazil", "president"): ("President_of_Brazil", "incumbent"),
}

_HEADERS = {"User-Agent": "SmartNewsBot/1.0 (research@example.com)"}


async def _fetch_wiki_page(page_title: str) -> Optional[str]:
    """Получает wiki-разметку страницы через MediaWiki API."""
    try:
        async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as client:
            url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "titles": page_title,
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "format": "json",
            }
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            pages = data["query"]["pages"]
            page = list(pages.values())[0]
            return page["revisions"][0]["slots"]["main"]["*"]
    except Exception as e:
        logger.warning(f"Wiki fetch failed for {page_title}: {e}")
        return None


def _extract_incumbent(wiki_text: str, field: str = "incumbent") -> Optional[str]:
    """Извлекает имя действующего лица из wiki-разметки infobox."""
    if not wiki_text:
        return None
    patterns = [
        rf"\|\s*{re.escape(field)}\s*=\s*\[\[(.*?)\]\]",
        rf"\|\s*{re.escape(field)}\s*=\s*(.+?)(?:\n|\|)",
    ]
    for pattern in patterns:
        match = re.search(pattern, wiki_text)
        if match:
            raw = match.group(1).strip()
            return raw.split("|")[0].strip()
    return None


async def update_leaders_from_wikipedia() -> Dict[str, Dict[str, str]]:
    """
    Обновляет данные о лидерах из Wikipedia.
    Возвращает словарь обновлений {country: {position: name}}.
    """
    updates: Dict[str, Dict[str, str]] = {}
    for (country, position), (page_title, field) in WIKI_PAGES.items():
        wiki_text = await _fetch_wiki_page(page_title)
        if wiki_text:
            name = _extract_incumbent(wiki_text, field)
            if name:
                updates.setdefault(country, {})[position] = name
                logger.info(f"🌐 Wiki update: {country}/{position} = {name}")
            else:
                logger.warning(f"⚠️ Could not extract {field} from {page_title}")
        await asyncio.sleep(0.5)
    return updates


def apply_updates(updates: Dict[str, Dict[str, str]]) -> bool:
    """
    Применяет обновления к ALL_LEADERS (in-memory).
    Возвращает True если были изменения.
    """
    changed = False
    for country, positions in updates.items():
        if country not in ALL_LEADERS:
            continue
        admin = ALL_LEADERS[country]
        for position, new_name in positions.items():
            if position in admin:
                old_name = admin[position].get("name_en", "")
                if old_name != new_name:
                    admin[position]["name_en"] = new_name
                    admin[position]["last_updated"] = datetime.now().isoformat()
                    logger.info(f"🔄 Leader updated: {country}/{position}: {old_name} → {new_name}")
                    changed = True
    return changed


async def maybe_update_leaders(force: bool = False) -> bool:
    """
    Проверяет необходимость обновления и выполняет его.
    Обновление раз в неделю (или при force=True).
    Fallback на статичный список при ошибке.
    """
    # Проверяем когда последний раз обновляли
    last_update = None
    for country, admin in ALL_LEADERS.items():
        for pos, person in admin.items():
            lu = person.get("last_updated")
            if lu:
                try:
                    dt = datetime.fromisoformat(lu)
                    if last_update is None or dt > last_update:
                        last_update = dt
                except ValueError:
                    pass

    if not force and last_update:
        days_since = (datetime.now() - last_update).days
        if days_since < 7:
            logger.debug(f"Leaders context is fresh ({days_since} days), skipping update")
            return False

    logger.info("🌐 Updating world leaders context from Wikipedia...")
    try:
        updates = await update_leaders_from_wikipedia()
        if updates:
            changed = apply_updates(updates)
            if changed:
                logger.info("✅ World leaders context updated from Wikipedia")
            return changed
        else:
            logger.warning("⚠️ No updates from Wikipedia, using static fallback")
            return False
    except Exception as e:
        logger.error(f"❌ Failed to update leaders from Wikipedia: {e}")
        logger.info("📋 Using static fallback for world leaders")
        return False


# Для синхронного вызова из существующего кода
def get_leaders_context_with_update() -> str:
    """
    Возвращает контекст лидеров, при необходимости запуская обновление.
    Обновление происходит асинхронно в фоне.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(maybe_update_leaders())
        else:
            loop.run_until_complete(maybe_update_leaders())
    except Exception as e:
        logger.debug(f"Background leader update failed: {e}")
    return get_leaders_context()
