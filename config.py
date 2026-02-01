"""
SigmaChanBot Configuration Module

Get credentials from:
- API_ID & API_HASH: https://my.telegram.org/apps
- BOT_TOKEN: Talk to @BotFather on Telegram
- Your User ID: Send /start to the bot
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram API credentials
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Admin user IDs (find yours with /start command)
ADMINS = [
    8451372304,
    8580994127,
]

# Bot settings
BOT_USERNAME = "@SigmaChanBot"
BOT_NAME = "SigmaChanBot"
SESSION_NAME = "sigmachanbot_session"
SESSION_DIR = "data"

