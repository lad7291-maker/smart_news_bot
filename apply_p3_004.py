#!/usr/bin/env python3
"""P3-004 Full Patch Script — применить на сервере"""
import os
import shutil

print("=" * 60)
print("P3-004 Full Patch")
print("=" * 60)

# 1. Backup
backup_dir = f".backup_p3_004_{os.popen('date +%Y%m%d_%H%M%S').read().strip()}"
if os.path.exists(backup_dir):
    shutil.rmtree(backup_dir)
shutil.copytree(
    ".",
    backup_dir,
    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "venv", ".git", backup_dir),
)
print(f"✅ Backup: {backup_dir}")

# 2. Patch poster.py — replace send_message fallbacks with branded image
with open("telegram_bot/poster.py", "r") as f:
    content = f.read()

# First fallback (photo error) — replace entire block
old1 = """                logger.warning(
                    f'⚠️ Фото не загрузилось ({photo_err}), отправляем текстом: {article["title"][:50]}...'
                )
                result = await _send_with_retry(
                    lambda: bot.send_message(
                        chat_id=config.TELEGRAM_CHANNEL_ID,
                        text=message_text,
                        disable_web_page_preview=True,
                    ),
                    article_link=link,
                    article_title=title,
                )
                msg_id = getattr(result, "message_id", None)
                analytics_manager.record_message_sent(
                    message_id=msg_id,
                    chat_id=chat_id,
                    article_link=link,
                    article_title=title,
                    source_tag=source_tag,
                    score=score,
                    delivered=True,
                    has_image=False,
                    is_fallback_image=False,
                )"""

new1 = """                logger.warning(
                    f'⚠️ Фото не загрузилось ({photo_err}), генерируем branded image: {article["title"][:50]}...'
                )
                try:
                    branded_bytes = await generate_branded_image(title, summary)
                    from aiogram.types import BufferedInputFile
                    photo = BufferedInputFile(branded_bytes, filename="branded.png")
                    result = await _send_with_retry(
                        lambda: bot.send_photo(
                            chat_id=config.TELEGRAM_CHANNEL_ID,
                            photo=photo,
                            caption=message_text,
                            parse_mode="HTML",
                        ),
                        article_link=link,
                        article_title=title,
                    )
                    msg_id = getattr(result, "message_id", None)
                except Exception as branded_err:
                    logger.warning(f'⚠️ Branded image тоже не сработал ({branded_err}), отправляем текстом')
                    result = await _send_with_retry(
                        lambda: bot.send_message(
                            chat_id=config.TELEGRAM_CHANNEL_ID,
                            text=message_text,
                            disable_web_page_preview=True,
                        ),
                        article_link=link,
                        article_title=title,
                    )
                    msg_id = getattr(result, "message_id", None)
                analytics_manager.record_message_sent(
                    message_id=msg_id,
                    chat_id=chat_id,
                    article_link=link,
                    article_title=title,
                    source_tag=source_tag,
                    score=score,
                    delivered=True,
                    has_image=False,
                    is_fallback_image=False,
                )"""

if old1 in content:
    content = content.replace(old1, new1)
    print("✅ First fallback patched (photo error → branded image)")
else:
    print("❌ First fallback not found")

# Second fallback (no image URL)
old2 = """        else:
            result = await _send_with_retry(
                lambda: bot.send_message(
                    chat_id=config.TELEGRAM_CHANNEL_ID,
                    text=message_text,
                    disable_web_page_preview=True,
                ),
                article_link=link,
                article_title=title,
            )
            msg_id = getattr(result, "message_id", None)
            analytics_manager.record_message_sent(
                message_id=msg_id,
                chat_id=chat_id,
                article_link=link,
                article_title=title,
                source_tag=source_tag,
                score=score,
                delivered=True,
                has_image=False,
                is_fallback_image=False,
            )"""

new2 = """        else:
            try:
                branded_bytes = await generate_branded_image(title, summary)
                from aiogram.types import BufferedInputFile
                photo = BufferedInputFile(branded_bytes, filename="branded.png")
                result = await _send_with_retry(
                    lambda: bot.send_photo(
                        chat_id=config.TELEGRAM_CHANNEL_ID,
                        photo=photo,
                        caption=message_text,
                        parse_mode="HTML",
                    ),
                    article_link=link,
                    article_title=title,
                )
                msg_id = getattr(result, "message_id", None)
            except Exception as branded_err:
                logger.warning(f'⚠️ Branded image не сработал ({branded_err}), отправляем текстом')
                result = await _send_with_retry(
                    lambda: bot.send_message(
                        chat_id=config.TELEGRAM_CHANNEL_ID,
                        text=message_text,
                        disable_web_page_preview=True,
                    ),
                    article_link=link,
                    article_title=title,
                )
                msg_id = getattr(result, "message_id", None)
            analytics_manager.record_message_sent(
                message_id=msg_id,
                chat_id=chat_id,
                article_link=link,
                article_title=title,
                source_tag=source_tag,
                score=score,
                delivered=True,
                has_image=False,
                is_fallback_image=False,
            )"""

if old2 in content:
    content = content.replace(old2, new2)
    print("✅ Second fallback patched (no image → branded image)")
else:
    print("❌ Second fallback not found")

with open("telegram_bot/poster.py", "w") as f:
    f.write(content)

# 3. Patch SearXNG engines
with open("utils/searxng_client.py", "r") as f:
    content = f.read()

old_engines = '"engines": "flickr,openverse"'
new_engines = (
    '"engines": "flickr,openverse,google_images,bing_images,duckduckgo_images,qwant_images"'
)
if old_engines in content:
    content = content.replace(old_engines, new_engines)
    print("✅ SearXNG engines updated")
else:
    print("❌ Engines pattern not found")

with open("utils/searxng_client.py", "w") as f:
    f.write(content)

# 4. Syntax check
print("\n--- Syntax Check ---")
import py_compile

try:
    py_compile.compile("telegram_bot/poster.py", doraise=True)
    print("✅ poster.py syntax OK")
except Exception as e:
    print(f"❌ poster.py syntax error: {e}")

try:
    py_compile.compile("utils/searxng_client.py", doraise=True)
    print("✅ searxng_client.py syntax OK")
except Exception as e:
    print(f"❌ searxng_client.py syntax error: {e}")

print("\n" + "=" * 60)
print("✅ P3-004 PATCHES COMPLETE")
print("=" * 60)
print("\nПерезапусти бота:")
print("  pkill -f bot_runner.py")
print("  nohup venv/bin/python bot_runner.py > logs/bot.log 2>&1 &")
