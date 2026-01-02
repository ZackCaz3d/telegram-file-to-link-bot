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
