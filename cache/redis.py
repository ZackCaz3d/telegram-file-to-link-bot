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

import redis
from config import REDIS_URL

if not REDIS_URL:
    raise RuntimeError("❌ REDIS_URL is required but not set")

try:
    redis_client = redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    redis_client.ping()
    print("✅ Redis connected (required)")
except Exception as e:
    raise RuntimeError(f"❌ Redis connection failed: {e}")

def delete_pattern(pattern: str):
    """
    Safely delete keys by pattern without blocking Redis.
    """
    for key in redis_client.scan_iter(match=pattern):
        redis_client.delete(key)
