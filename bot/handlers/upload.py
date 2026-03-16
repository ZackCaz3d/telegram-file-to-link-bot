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

import asyncio
import uuid
import os
import re
import time
from datetime import datetime, timedelta, timezone

import boto3
from pyrogram import filters
from bot.bot import tg_client
from cache.redis import redis_client
from bot.utils.access import is_allowed
from bot.utils.mode import get_mode, format_ttl
from config import (
    BASE_URL,
    MAX_FILE_MB,
    MAX_CONCURRENT_TRANSFERS,
    STORAGE_BACKEND,
    AWS_ENDPOINT_URL,
    AWS_S3_BUCKET_NAME,
    AWS_DEFAULT_REGION,
)
from db.database import Database

UPLOAD_DIR = os.path.abspath("uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

upload_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TRANSFERS)

# Minimum seconds between status edits (avoids Telegram flood-waits)
PROGRESS_EDIT_INTERVAL = 2.0

s3 = None
if STORAGE_BACKEND == "s3":
    s3 = boto3.client(
        "s3",
        endpoint_url=AWS_ENDPOINT_URL,
        region_name=AWS_DEFAULT_REGION,
    )


def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip()


def format_bytes(n: int) -> str:
    """Human-readable file size."""
    if n < 1024:
        return f"{n} B"
    elif n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    elif n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    else:
        return f"{n / 1024 ** 3:.2f} GB"


def progress_bar(pct: float, width: int = 12) -> str:
    """Render a text-based progress bar.  e.g.  ▓▓▓▓▓▓░░░░░░ 50%"""
    filled = round(width * pct)
    return "▓" * filled + "░" * (width - filled)


@tg_client.on_message(
    filters.private & (
        filters.document
        | filters.video
        | filters.audio
        | filters.photo
        | filters.animation
        | filters.voice
        | filters.video_note
    )
)
async def upload_handler(_, message):
    if not message.from_user:
        return

    if not is_allowed(message.from_user.id):
        await message.reply("🚫 Unauthorized")
        return

    status = await message.reply("📥 Queued for processing…")

    async with upload_semaphore:
        await process_upload(message, status)


async def process_upload(message, status):
    media = (
        message.document
        or message.video
        or message.audio
        or message.photo
        or message.animation
        or message.voice
        or message.video_note
    )

    file_size = getattr(media, "file_size", None)

    if MAX_FILE_MB is not None and file_size:
        max_bytes = MAX_FILE_MB * 1024 * 1024
        if file_size > max_bytes:
            size_mb = file_size / (1024 * 1024)
            await status.edit(
                "❌ **File too large**\n\n"
                f"Your file: **{size_mb:.2f} MB**\n"
                f"Max allowed: **{MAX_FILE_MB} MB**"
            )
            return

    # ── Download from Telegram with progress ─────────────────────────
    last_edit_time = 0.0

    async def download_progress(current: int, total: int):
        nonlocal last_edit_time
        now = time.monotonic()
        pct = current / total if total else 0
        # Only edit if enough time has passed, or we're done
        if now - last_edit_time < PROGRESS_EDIT_INTERVAL and current < total:
            return
        last_edit_time = now
        try:
            await status.edit(
                f"⬇️ **Downloading…**\n\n"
                f"`{progress_bar(pct)}` {pct:.0%}\n"
                f"{format_bytes(current)} / {format_bytes(total)}"
            )
        except Exception:
            pass  # swallow flood-wait / message-not-modified errors

    await status.edit("⬇️ **Downloading…**\n\n`░░░░░░░░░░░░` 0%")
    temp_path = await message.download(progress=download_progress)

    if not temp_path:
        await status.edit("❌ Download failed")
        return

    if message.photo:
        original_name = f"{uuid.uuid4().hex}.jpg"
    elif hasattr(media, "file_name") and media.file_name:
        original_name = safe_filename(media.file_name)
    else:
        original_name = f"{uuid.uuid4().hex}.bin"

    file_size = file_size or os.path.getsize(temp_path)

    file_id = uuid.uuid4().hex[:12]
    ext = os.path.splitext(original_name)[1]

    if STORAGE_BACKEND == "local":
        # Local move — effectively instant, no progress needed
        internal_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
        os.replace(temp_path, internal_path)
        stored_path = internal_path
    else:
        # ── S3 upload with progress ──────────────────────────────────
        key = f"{file_id}{ext}"
        upload_total = os.path.getsize(temp_path)
        uploaded_so_far = 0
        last_s3_edit = 0.0
        loop = asyncio.get_running_loop()

        def s3_progress_callback(bytes_transferred: int):
            nonlocal uploaded_so_far, last_s3_edit
            uploaded_so_far += bytes_transferred
            now = time.monotonic()
            pct = uploaded_so_far / upload_total if upload_total else 0
            if now - last_s3_edit < PROGRESS_EDIT_INTERVAL and uploaded_so_far < upload_total:
                return
            last_s3_edit = now
            # Schedule the async edit from the sync boto3 callback
            asyncio.run_coroutine_threadsafe(
                _safe_edit(
                    status,
                    f"⬆️ **Uploading to S3…**\n\n"
                    f"`{progress_bar(pct)}` {pct:.0%}\n"
                    f"{format_bytes(uploaded_so_far)} / {format_bytes(upload_total)}"
                ),
                loop,
            )

        await status.edit("⬆️ **Uploading to S3…**\n\n`░░░░░░░░░░░░` 0%")
        # Run the blocking S3 upload in a thread so we don't stall the event loop
        await asyncio.to_thread(
            s3.upload_file,
            temp_path,
            AWS_S3_BUCKET_NAME,
            key,
            Callback=s3_progress_callback,
        )
        os.remove(temp_path)
        stored_path = key

    user_mode = get_mode(message.from_user.id)

    if user_mode["ttl"] > 0:
        ttl = user_mode["ttl"]
        ttl_source = "👤 Using your TTL"
    else:
        ttl = 0
        ttl_source = "♾ No expiration"

    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=ttl)
        if ttl > 0 else None
    )

    await Database.pool.execute(
        """
        INSERT INTO files (
            file_id, path, name, downloads, file_size, expires_at
        )
        VALUES ($1, $2, $3, 0, $4, $5)
        """,
        file_id,
        stored_path,
        original_name,
        file_size,
        expires_at,
    )

    redis_client.delete(f"file:{file_id}")
    redis_client.hset(
        f"file:{file_id}",
        mapping={
            "path": stored_path,
            "name": original_name,
            "downloads": 0,
            "file_size": file_size,
            "expires_at": int(expires_at.timestamp()) if expires_at else 0,
        }
    )

    size_mb = file_size / (1024 * 1024)

    await status.edit(
        "✅ **File uploaded**\n\n"
        f"{ttl_source}\n"
        f"📄 **Name:** `{original_name}`\n"
        f"📦 **Size:** `{size_mb:.2f} MB`\n"
        f"⏳ **Expires:** {format_ttl(ttl)}\n\n"
        f"🔗 `{BASE_URL}/file/{file_id}`"
    )


async def _safe_edit(msg, text: str):
    """Edit a message, silently ignoring flood-wait or not-modified errors."""
    try:
        await msg.edit(text)
    except Exception:
        pass
