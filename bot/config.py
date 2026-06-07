import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
BOT_SECRET = os.getenv("BOT_SECRET", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000/api/v1")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

SUPPORTED_LANGS = ("uz", "ru", "en")
DEFAULT_LANG = "uz"
