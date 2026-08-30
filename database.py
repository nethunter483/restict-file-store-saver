from motor.motor_asyncio import AsyncIOMotorClient
from config import Config
import logging

# 5 second timeout taaki freeze na ho
client = AsyncIOMotorClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
db = client[Config.DB_NAME]
users_col = db["users"]

async def get_user_settings(user_id: int):
    try:
        user = await users_col.find_one({"user_id": user_id})
        if not user:
            default_data = {
                "user_id": user_id,
                "target_channel": None,
                "session_string": None
            }
            await users_col.insert_one(default_data)
            return default_data
        return user
    except Exception as e:
        logging.error(f"Database Error in get_user_settings: {e}")
        # Agar DB fail ho toh default return karega taaki bot reply dena na roke
        return {"user_id": user_id, "target_channel": None, "session_string": None}

async def set_target_channel(user_id: int, channel_id: int):
    try:
        await users_col.update_one(
            {"user_id": user_id},
            {"$set": {"target_channel": channel_id}},
            upsert=True
        )
    except Exception as e:
        logging.error(f"Database Error in set_target_channel: {e}")
