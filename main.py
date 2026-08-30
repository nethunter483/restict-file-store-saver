from pyrogram import Client, filters, idle  # <--- 'idle' import karein

# ... (baaki saare handlers waise hi rahenge) ...

# Ek test command check karne ke liye ki bot active hai ya nahi
@bot.on_message(filters.command("ping") & filters.private)
async def ping_cmd(client: Client, message: Message):
    await message.reply_text("🏓 **Pong! Bot is 100% Active & Replying.**")

async def main():
    await bot.start()
    logging.info("Main Bot Started!")

    try:
        await userbot.start()
        logging.info("Userbot Session Connected!")
        asyncio.create_task(worker_loop(bot, userbot))
    except Exception as e:
        logging.error(f"Userbot Warning: {e}")

    logging.info("Bot and Userbot Started Successfully!")
    
    # Official Pyrogram idle method
    await idle()
    
    await bot.stop()
    if userbot.is_connected:
        await userbot.stop()

if __name__ == "__main__":
    asyncio.run(main())
if __name__ == "__main__":
    asyncio.run(main())
