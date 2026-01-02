import os
from dotenv import load_dotenv

load_dotenv()


def str2bool(v):
    return str(v).lower() in ("1", "true", "yes", "on")


def env_int(name: str, default=None):
    try:
        value = os.getenv(name)
        return int(value) if value is not None else default
    except ValueError:
        return default


def require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value

API_ID = int(require("API_ID"))
API_HASH = require("API_HASH")
BOT_TOKEN = require("BOT_TOKEN")

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
DATABASE_URL = require("DATABASE_URL")
REDIS_URL = require("REDIS_URL")

GLOBAL_RATE_LIMIT_REQUESTS = env_int("GLOBAL_RATE_LIMIT_REQUESTS", 60)
GLOBAL_RATE_LIMIT_WINDOW = env_int("GLOBAL_RATE_LIMIT_WINDOW", 10)

ALLOWED_USER_IDS = (
    list(map(int, os.getenv("ALLOWED_USER_IDS").split(",")))
    if os.getenv("ALLOWED_USER_IDS")
    else None
)

ADMIN_ENABLED = str2bool(os.getenv("ADMIN_ENABLED", "false"))


# =========================
# Upload limits
# =========================
# Telegram limits:
# - Normal users: ~2 GB
# - Premium users: ~4 GB
#
# Examples:
# MAX_FILE_MB=2048
# MAX_FILE_MB=4096
#
# If unset → unlimited (Telegram controls it)

MAX_FILE_MB = env_int("MAX_FILE_MB", None)
