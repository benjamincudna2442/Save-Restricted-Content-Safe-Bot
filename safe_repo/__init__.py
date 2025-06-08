# safe_repo

import asyncio
import logging
from pyrogram import Client
from telethon.sync import TelegramClient
from config import API_ID, API_HASH, BOT_TOKEN

loop = asyncio.get_event_loop()

logging.basicConfig(
    format="[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s",
    level=logging.INFO,
)

# Initialize Telethon client
sex = TelegramClient('sexrepo', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Initialize Pyrogram client
app = Client(
    ":RestrictBot:",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=10,
    sleep_threshold=20,
    max_concurrent_transmissions=5
)

async def restrict_bot():
    global BOT_ID, BOT_NAME, BOT_USERNAME
    await app.start()
    try:
        getme = await app.get_me()
        BOT_ID = getme.id
        BOT_USERNAME = getme.username
        BOT_NAME = f"{getme.first_name} {getme.last_name}" if getme.last_name else getme.first_name
    except Exception as e:
        logging.error(f"Failed to retrieve bot information: {e}")
        raise
    finally:
        await app.stop()

# Run the restrict_bot function
if __name__ == "__main__":
    try:
        loop.run_until_complete(restrict_bot())
    except KeyboardInterrupt:
        logging.info("Bot initialization interrupted by user")
    except Exception as e:
        logging.error(f"Error during bot initialization: {e}")
