import os
import re
import asyncio
import logging
from pyrogram import Client, filters, idle
from pyrogram.types import Message

from config import Config
from database import get_user_settings, set_target_channel
from queue_worker import task_queue, worker_loop

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# 1. PEHLE CLIENTS INITIALIZE HONGE
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

# 2. PING COMMAND (Testing ke liye)
@bot.on_message(filters.command("ping") & filters.private)
async def ping_cmd(client: Client, message: Message):
    await message.reply_text("🏓 **Pong! Bot is 100% Active & Replying.**")

# 3. START COMMAND
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    settings = await get_user_settings(user_id)
    
    channel_text = f"`{settings['target_channel']}`" if settings.get('target_channel') else "❌ Not Connected"
    
    text = (
        f"👋 **Hello {message.from_user.mention}!**\n\n"
        f"📌 **Connected Channel:** {channel_text}\n"
        f"📋 **Current Queue:** `{task_queue.qsize()}` tasks pending\n\n"
        "**Kaise use karein?**\n"
        "1. Apne channel me bot ko Admin banayein aur channel se koi bhi message yahan forward karein.\n"
        "2. File Store ka link bhejein (jaise `https://t.me/bot?start=xxx`), bot videos fetch karke aapke channel me bhej dega."
    )
    await message.reply_text(text)

# 4. CHANNEL AUTO-CONNECT HANDLER
@bot.on_message(filters.forwarded & filters.private)
async def detect_channel(client: Client, message: Message):
    if not message.forward_from_chat or message.forward_from_chat.type.name != "CHANNEL":
        return await message.reply_text("❌ Please kisi **Channel** se message forward karein.")

    channel = message.forward_from_chat
    user_id = message.from_user.id

    try:
        me = await client.get_me()
        bot_member = await client.get_chat_member(channel.id, me.id)
        if not bot_member.privileges.can_post_messages:
            return await message.reply_text("❌ Bot channel me add hai par **Post Messages** permission nahi hai!")

        await set_target_channel(user_id, channel.id)
        await message.reply_text(f"✅ **Channel Connected Successfully!**\nTitle: `{channel.title}`\nID: `{channel.id}`")

    except Exception as e:
        await message.reply_text(f"❌ Error: Bot ko pehle channel me **Admin** banayein.\nDetail: `{e}`")

# 5. FILE STORE LINK HANDLER
@bot.on_message(filters.text & filters.private & ~filters.command(["start", "ping", "help"]))
async def link_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    settings = await get_user_settings(user_id)
    target_chat = settings.get("target_channel") or user_id

    # Check for valid t.me/BotUsername?start=XYZ pattern
    match = re.search(r"t\.me/([a-zA-Z0-9_]+)\?start=([a-zA-Z0-9_-]+)", text)
    if not match:
        return await message.reply_text("❌ Invalid Link! Please `https://t.me/bot?start=...` format ka link bhejein.")

    target_bot_username = match.group(1)
    start_param = match.group(2)

    status_msg = await message.reply_text("⏳ Processing link via Userbot...")

    try:
        # Userbot sends /start parameter to the target bot
        sent = await userbot.send_message(target_bot_username, f"/start {start_param}")
        
        # Wait 4 seconds for file store bot to send responses
        await asyncio.sleep(4)

        # Collect response messages
        incoming_messages = []
        async for msg in userbot.get_chat_history(target_bot_username, limit=15):
            if msg.id > sent.id and (msg.video or msg.document or msg.photo):
                incoming_messages.append(msg)

        if not incoming_messages:
            return await status_msg.edit_text("❌ No media found. Link expire ho chuka hai ya bot offline hai.")

        # Add to Queue
        for media_msg in reversed(incoming_messages):
            await task_queue.put({
                "user_id": user_id,
                "target_chat": target_chat,
                "message": media_msg,
                "status_msg": status_msg
            })

        pos = task_queue.qsize()
        await status_msg.edit_text(f"📥 **{len(incoming_messages)} files queue me add ho gayi hain!**\nQueue Position: #{pos}")

    except Exception as e:
        await status_msg.edit_text(f"❌ Error: `{e}`")

# 6. MAIN RUNNER
async def main():
    await bot.start()
    logging.info("Main Bot Started!")

    try:
        await userbot.start()
        logging.info("Userbot Session Connected!")
        # Start queue worker background task
        asyncio.create_task(worker_loop(bot, userbot))
    except Exception as e:
        logging.error(f"Userbot Warning: {e}")

    logging.info("Bot and Userbot Started Successfully!")
    
    # Keeps the bot running properly on Railway
    await idle()
    
    await bot.stop()
    if userbot.is_connected:
        await userbot.stop()

if __name__ == "__main__":
    asyncio.run(main())
