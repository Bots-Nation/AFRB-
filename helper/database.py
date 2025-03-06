import motor.motor_asyncio
import datetime
import pytz
from config import Config
import logging

class Database:
    def __init__(self, uri, database_name):
        try:
            self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
            self._client.server_info()
            logging.info("Successfully connected to MongoDB")
        except Exception as e:
            logging.error(f"Failed to connect to MongoDB: {e}")
            raise e
        self.codeflixbots = self._client[database_name]
        self.col = self.codeflixbots.user
        self.token_links = self.codeflixbots.token_links  # Token links collection

    def new_user(self, id):
        return dict(
            _id=int(id),
            join_date=datetime.datetime.now(pytz.utc).date().isoformat(),
            file_id=None,
            caption=None,
            metadata=True,
            metadata_code="Telegram : @DARKXSIDE78",
            format_template=None,
            rename_count=0,
            first_name="",
            username="",
            token_tasks=[],
            is_premium=False,
            premium_expiry=None,
            token=69,  # Default token value
            ban_status=dict(
                is_banned=False,
                ban_duration=0,
                banned_on=datetime.datetime.max.date().isoformat(),
                ban_reason=''
            )
        )

    async def add_user(self, b, m):
        u = m.from_user
        if not await self.is_user_exist(u.id):
            user = self.new_user(u.id)
            # Add user's actual information
            user["first_name"] = u.first_name or "Unknown"
            user["username"] = u.username or ""
            try:
                await self.col.insert_one(user)
                logging.info(f"User {u.id} added to database")

    async def is_user_exist(self, id):
        try:
            user = await self.col.find_one({"_id": int(id)})
            return bool(user)
        except Exception as e:
            logging.error(f"Error checking if user {id} exists: {e}")
            return False

    async def total_users_count(self):
        try:
            count = await self.col.count_documents({})
            return count
        except Exception as e:
            logging.error(f"Error counting users: {e}")
            return 0

    async def get_all_users(self):
        try:
            all_users = self.col.find({})
            return all_users
        except Exception as e:
            logging.error(f"Error getting all users: {e}")
            return None

    async def delete_user(self, user_id):
        try:
            await self.col.delete_many({"_id": int(user_id)})
        except Exception as e:
            logging.error(f"Error deleting user {user_id}: {e}")

    async def set_thumbnail(self, id, file_id):
        try:
            await self.col.update_one({"_id": int(id)}, {"$set": {"file_id": file_id}})
        except Exception as e:
            logging.error(f"Error setting thumbnail for user {id}: {e}")

    async def get_thumbnail(self, id):
        try:
            user = await self.col.find_one({"_id": int(id)})
            return user.get("file_id", None) if user else None
        except Exception as e:
            logging.error(f"Error getting thumbnail for user {id}: {e}")
            return None

    async def set_caption(self, id, caption):
        try:
            await self.col.update_one({"_id": int(id)}, {"$set": {"caption": caption}})
        except Exception as e:
            logging.error(f"Error setting caption for user {id}: {e}")

    async def get_caption(self, id):
        try:
            user = await self.col.find_one({"_id": int(id)})
            return user.get("caption", None) if user else None
        except Exception as e:
            logging.error(f"Error getting caption for user {id}: {e}")
            return None

    async def set_format_template(self, id, format_template):
        try:
            await self.col.update_one(
                {"_id": int(id)}, {"$set": {"format_template": format_template}}
            )
        except Exception as e:
            logging.error(f"Error setting format template for user {id}: {e}")

    async def get_format_template(self, id):
        try:
            user = await self.col.find_one({"_id": int(id)})
            return user.get("format_template", None) if user else None
        except Exception as e:
            logging.error(f"Error getting format template for user {id}: {e}")
            return None

    async def create_token_link(self, user_id: int, token_id: str, tokens: int):
        expiry = datetime.datetime.now(pytz.utc) + datetime.timedelta(hours=24)
        try:
            await self.token_links.update_one(
                {"_id": token_id},
                {
                    "$set": {
                        "user_id": user_id,
                        "tokens": tokens,
                        "used": False,
                        "expiry": expiry
                    }
                },
                upsert=True
            )
            logging.info(f"Token link created for user {user_id} with token ID {token_id}.")
        except Exception as e:
            logging.error(f"Error creating token link: {e}")

    async def get_token_link(self, token_id: str):
        try:
            token_data = await self.token_links.find_one({"_id": token_id})
            return token_data
        except Exception as e:
            logging.error(f"Error fetching token link for token ID {token_id}: {e}")
            return None

    async def mark_token_used(self, token_id: str):
        try:
            await self.token_links.update_one(
                {"_id": token_id},
                {"$set": {"used": True}}
            )
            logging.info(f"Token {token_id} marked as used.")
        except Exception as e:
            logging.error(f"Error marking token as used: {e}")

    async def set_token(self, user_id, token):
        try:
            await self.col.update_one(
                {"_id": int(user_id)},
                {"$set": {"token": token}}
            )
            logging.info(f"Token updated for user {user_id}.")
        except Exception as e:
            logging.error(f"Error setting token for user {user_id}: {e}")

    async def get_token(self, user_id):
        try:
            user = await self.col.find_one({"_id": int(user_id)})
            return user.get("token", 69) if user else 69
        except Exception as e:
            logging.error(f"Error getting token for user {user_id}: {e}")
            return 69

codeflixbots = Database(Config.DB_URL, Config.DB_NAME)
