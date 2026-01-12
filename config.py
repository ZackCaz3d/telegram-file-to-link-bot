# Copyright 2025 Aman
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

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

def normalize_base_url(value: str | None) -> str:
    if not value:
        return "http://localhost:8000"
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://{value}"

API_ID = int(require("API_ID"))
API_HASH = require("API_HASH")
BOT_TOKEN = require("BOT_TOKEN")

BASE_URL = normalize_base_url(os.getenv("BASE_URL"))
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

MAX_FILE_MB = env_int("MAX_FILE_MB", None)

MAX_CONCURRENT_TRANSFERS = env_int("MAX_CONCURRENT_TRANSFERS", 3)

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")

AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
AWS_S3_BUCKET_NAME = os.getenv("AWS_S3_BUCKET_NAME")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "auto")
