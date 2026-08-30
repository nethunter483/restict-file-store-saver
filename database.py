from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

client = AsyncIOMotorClient(Config.MONGO_URI)
db = client[Config.DB_NAME]
users_col = db["users"]

async def get_user_settings(user_id: int):
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

async def set_target_channel(user_id: int, channel_id: int):
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"target_channel": channel_id}},
        upsert=True
    )
