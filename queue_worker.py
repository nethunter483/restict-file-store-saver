import os
import asyncio
import logging
from pyrogram.errors import FloodWait

task_queue = asyncio.Queue()

async def process_media_task(bot, userbot, task_data):
    user_id = task_data["user_id"]
    target_chat = task_data["target_chat"]
    message = task_data["message"]
    status_msg = task_data["status_msg"]

    try:
        await status_msg.edit_text("⏳ **Downloading protected media...**")
        
        # Download media via userbot (bypasses UI restriction)
        file_path = await userbot.download_media(
            message,
            progress=lambda current, total: None
        )

        if not file_path:
            await status_msg.edit_text("❌ File download failed.")
            return

        await status_msg.edit_text("📤 **Uploading to destination channel...**")

        # Upload to target destination
        if message.video:
            await bot.send_video(
                chat_id=target_chat,
                video=file_path,
                caption=message.caption or "",
                duration=message.video.duration or 0,
                width=message.video.width or 0,
                height=message.video.height or 0
            )
        elif message.document:
            await bot.send_document(
                chat_id=target_chat,
                document=file_path,
                caption=message.caption or ""
            )
        elif message.photo:
            await bot.send_photo(
                chat_id=target_chat,
                photo=file_path,
                caption=message.caption or ""
            )

        # Cleanup local file to save Railway disk
        if os.path.exists(file_path):
            os.remove(file_path)

        await status_msg.edit_text("✅ **Successfully processed and sent!**")

    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception as e:
        logging.error(f"Task Error: {e}")
        await status_msg.edit_text(f"❌ **Error:** `{str(e)}`")
    finally:
        if 'file_path' in locals() and file_path and os.path.exists(file_path):
            os.remove(file_path)

async def worker_loop(bot, userbot):
    while True:
        task_data = await task_queue.get()
        try:
            await process_media_task(bot, userbot, task_data)
        except Exception as err:
            logging.error(f"Worker Error: {err}")
        finally:
            task_queue.task_done()
