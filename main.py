import re
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import ChatAdminRequired, UserNotParticipant

from config import Config
from database import get_user_settings, set_target_channel
from queue_worker import task_queue, worker_loop

logging.basicConfig(level=logging.INFO)

bot = Client(
    "RestrictedBot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

userbot = Client(
    "UserSession",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    session_string=Config.SESSION_STRING
)

# Start Command
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    settings = await get_user_settings(user_id)
    
    channel_text = f"`{settings['target_channel']}`" if settings['target_channel'] else "❌ Not Connected"
    
    text = (
        f"👋 **Hello {message.from_user.mention}!**\n\n"
        f"📌 **Target Channel:** {channel_text}\n"
        f"📋 **Queue Status:** `{task_queue.qsize()}` tasks pending\n\n"
        "**Features:**\n"
        "1. Send me a File Store link (e.g., `https://t.me/bot?start=xxx`)\n"
        "2. To connect your channel, add this bot as **Admin** in your channel and forward any message here."
    )
    await message.reply_text(text)

# Auto-Detect Target Channel (When user forwards a message from their channel)
@bot.on_message(filters.forwarded & filters.private)
async def detect_channel(client: Client, message: Message):
    if not message.forward_from_chat or message.forward_from_chat.type.name != "CHANNEL":
        return await message.reply_text("❌ Please forward a message from a **Channel** only.")

    channel = message.forward_from_chat
    user_id = message.from_user.id

    try:
        # Check if bot is Admin
        bot_member = await client.get_chat_member(channel.id, (await client.get_me()).id)
        if not bot_member.privileges.can_post_messages:
            return await message.reply_text("❌ Bot channel me add hai par **Post Messages** permission nahi hai!")

        await set_target_channel(user_id, channel.id)
        await message.reply_text(f"✅ **Channel Connected Successfully:**\n`{channel.title}` (`{channel.id}`)")

    except Exception as e:
        await message.reply_text(f"❌ Error: Bot ko pehle channel me **Admin** banayein.\n`{e}`")

# Link Handler for File Store Links
@bot.on_message(filters.text & filters.private & ~filters.command(["start", "help"]))
async def link_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Check if target channel configured
    settings = await get_user_settings(user_id)
    target_chat = settings.get("target_channel") or user_id

    # Pattern for t.me/bot?start=XYZ
    match = re.search(r"t\.me/([a-zA-Z0-9_]+)\?start=([a-zA-Z0-9_-]+)", text)
    if not match:
        return await message.reply_text("❌ Invalid link. Please send a valid `https://t.me/bot?start=...` link.")

    target_bot_username = match.group(1)
    start_param = match.group(2)

    status_msg = await message.reply_text("⏳ Processing link via Userbot...")

    try:
        # Userbot sends /start parameter to the target File Store Bot
        sent = await userbot.send_message(target_bot_username, f"/start {start_param}")
        
        # Wait a few seconds for file store bot to send responses (before auto-delete)
        await asyncio.sleep(4)

        # Collect response messages
        incoming_messages = []
        async for msg in userbot.get_chat_history(target_bot_username, limit=10):
            if msg.id > sent.id and (msg.video or msg.document or msg.photo):
                incoming_messages.append(msg)

        if not incoming_messages:
            return await status_msg.edit_text("❌ No media found or files were already expired/deleted.")

        # Add all media files to FIFO queue
        for media_msg in reversed(incoming_messages):
            await task_queue.put({
                "user_id": user_id,
                "target_chat": target_chat,
                "message": media_msg,
                "status_msg": status_msg
            })

        pos = task_queue.qsize()
        await status_msg.edit_text(f"📥 **{len(incoming_messages)} files added to queue!**\nQueue Position: #{pos}")

    except Exception as e:
        await status_msg.edit_text(f"❌ Failed to fetch: `{e}`")

async def main():
    await bot.start()
    await userbot.start()
    logging.info("Bot and Userbot Started Successfully!")
    
    # Start the single worker loop in background
    asyncio.create_task(worker_loop(bot, userbot))
    
    # Keep alive
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
