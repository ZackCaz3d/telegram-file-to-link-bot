import os
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from cache.redis import redis_client
from db.database import Database
from config import (
    GLOBAL_RATE_LIMIT_REQUESTS,
    GLOBAL_RATE_LIMIT_WINDOW,
)

router = APIRouter()


def get_real_ip(request: Request) -> str:
    return (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0]
        or request.client.host
    )


def rate_limit_response(window: int):
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limited", "retry_after": window},
        headers={"Retry-After": str(window)},
    )


def check_rate_limit(key: str, limit: int, window: int):
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, window)
    if count > limit:
        return rate_limit_response(window)


@router.get("/file/{file_id}")
async def get_file(file_id: str, request: Request):

    ip = get_real_ip(request)

    if GLOBAL_RATE_LIMIT_REQUESTS > 0:
        if resp := check_rate_limit(
            f"rate:global:{ip}",
            GLOBAL_RATE_LIMIT_REQUESTS,
            GLOBAL_RATE_LIMIT_WINDOW,
        ):
            return resp

    key = f"file:{file_id}"
    meta = redis_client.hgetall(key)

    if not meta:
        row = await Database.pool.fetchrow(
            "SELECT path, name, downloads FROM files WHERE file_id=$1",
            file_id,
        )
        if not row:
            raise HTTPException(404, "File not found")

        meta = dict(row)
        redis_client.hset(key, mapping=meta)

    download_key = f"downloaded:{ip}:{file_id}"
    first_download = not redis_client.exists(download_key)

    if first_download:
        redis_client.setex(download_key, 3600, 1)

        await Database.pool.execute(
            "UPDATE files SET downloads = downloads + 1 WHERE file_id=$1",
            file_id,
        )

        redis_client.hincrby(key, "downloads", 1)

    if not os.path.exists(meta["path"]):
        raise HTTPException(404, "File missing")

    return FileResponse(
        path=meta["path"],
        filename=meta["name"],
        media_type="application/octet-stream",
    )
