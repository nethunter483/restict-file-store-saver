import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram API Credentials (my.telegram.org se lein)
    API_ID = int(os.environ.get("API_ID", "1234567"))
    API_HASH = os.environ.get("API_HASH", "your_api_hash_here")
    
    # Main Bot Token (@BotFather se lein)
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token_here")
    
    # User Account String Session (Protected files fetch karne ke liye)
    SESSION_STRING = os.environ.get("SESSION_STRING", "your_pyrogram_session_string")
    
    # MongoDB URL (Render/Railway environment me set karein)
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://...")
    DB_NAME = os.environ.get("DB_NAME", "RestrictedSaverDB")
    
    # Bot Owner ID
    OWNER_ID = int(os.environ.get("OWNER_ID", "123456789"))
