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
import json
import uuid
import os
import re
import time
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, asdict
from typing import Optional

import boto3
from pyrogram import filters
from pyrogram.types import Message
from bot.bot import tg_client
from cache.redis import redis_client
from bot.utils.access import is_allowed
from bot.utils.mode import get_mode, format_ttl
from bot.utils.transfers import tracker
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

# Minimum seconds between status message edits (avoids Telegram flood-waits)
PROGRESS_EDIT_INTERVAL = 2.0

s3 = None
if STORAGE_BACKEND == "s3":
    s3 = boto3.client(
        "s3",
        endpoint_url=AWS_ENDPOINT_URL,
        region_name=AWS_DEFAULT_REGION,
    )


# ── Caption / metadata parsing ───────────────────────────────────────────────

@dataclass
class FileMetadata:
    """Structured metadata extracted from a forwarded channel message."""
    source: Optional[str] = None       # e.g. "fatetraffic", "watercloud_info"
    password: Optional[str] = None     # from .pass: lines
    channel: Optional[str] = None      # branding line like "DAISY CLOUD"
    date_tag: Optional[str] = None     # date from the filename if present
    count: Optional[int] = None        # item count from filename if present


# Patterns that match known caption fields
_RE_PASS      = re.compile(r"\.pass:\s*@?(\S+)", re.IGNORECASE)
_RE_SOURCE_FN = re.compile(r"^@?(\w+?)[\s_]+\d", re.IGNORECASE)          # source from filename
_RE_COUNT     = re.compile(r"(\d{2,})\s*(?:MIX|PCS|FI|COMBO|FRESH|HQ)", re.IGNORECASE)
_RE_DATE_FN   = re.compile(r"(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})")      # dd-mm-yyyy etc
_RE_LINK_LINE = re.compile(r"^\s*(?:📘|👥|📢|\.info|\.chat|\.admin)", re.MULTILINE)


def parse_caption(caption: Optional[str], filename: str) -> FileMetadata:
    """Best-effort extraction of metadata from a channel-style caption + filename."""
    meta = FileMetadata()

    # ── From the filename ────────────────────────────────────────────
    m = _RE_SOURCE_FN.match(filename)
    if m:
        meta.source = m.group(1).lower().strip("_")

    m = _RE_COUNT.search(filename)
    if m:
        meta.count = int(m.group(1))

    m = _RE_DATE_FN.search(filename)
    if m:
        meta.date_tag = m.group(1)

    if not caption:
        return meta

    # ── From the caption body ────────────────────────────────────────
    m = _RE_PASS.search(caption)
    if m:
        meta.password = m.group(1)
        # Password source often == file source when we didn't get one from filename
        if not meta.source:
            meta.source = m.group(1).lower().strip("_")

    # Channel branding — grab the first ALL-CAPS label that isn't a link line
    for line in caption.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue
        if _RE_LINK_LINE.match(line_stripped):
            continue
        # Strip emoji and pipes, check for uppercase branding
        clean = re.sub(r"[\U0001F300-\U0001FAFF⚡|]", "", line_stripped).strip()
        if clean and clean == clean.upper() and len(clean) > 3 and not clean.startswith("."):
            meta.channel = clean.split("|")[0].strip()
            break

    return meta


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip()


def format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    elif n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    elif n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    else:
        return f"{n / 1024 ** 3:.2f} GB"


def progress_bar(pct: float, width: int = 14) -> str:
    filled = round(width * pct)
    return "▓" * filled + "░" * (width - filled)


def sanitize_folder(name: str) -> str:
    """Lowercase, alphanumeric + underscores only."""
    return re.sub(r"[^a-z0-9_\-]", "_", name.lower()).strip("_") or "_unsorted"


def build_s3_key(file_id: str, ext: str, meta: FileMetadata) -> str:
    """
    Build an S3 object key with folder structure:
        <source>/<file_id><ext>     — when source is known
        _unsorted/<file_id><ext>    — fallback
    """
    folder = sanitize_folder(meta.source) if meta.source else "_unsorted"
    return f"{folder}/{file_id}{ext}"


def build_metadata_dict(
    meta: FileMetadata,
    file_id: str,
    original_name: str,
    file_size: int,
    ttl: int,
    expires_at: Optional[datetime],
) -> dict:
    """Build a JSON-serialisable metadata dict for sidecar storage."""
    return {
        **{k: v for k, v in asdict(meta).items() if v is not None},
        "file_id": file_id,
        "original_name": original_name,
        "file_size": file_size,
        "ttl_seconds": ttl,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }


def _write_metadata_sidecar(path: str, meta_dict: dict):
    """Write a .meta.json sidecar next to the stored file (local backend)."""
    meta_path = path + ".meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta_dict, f, indent=2)


async def _safe_edit(msg, text: str):
    """Edit a message, silently ignoring flood-wait / not-modified errors."""
    try:
        await msg.edit(text)
    except Exception:
        pass


# ── Handler ───────────────────────────────────────────────────────────────────

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

    # Check if the semaphore is fully occupied (all slots taken)
    queued = upload_semaphore._value == 0
    if queued:
        status = await message.reply(
            "🕐 **Queued** — all upload slots are busy.\n"
            "Your file will be processed as soon as a slot frees up."
        )
    else:
        status = await message.reply("📥 **Processing…**")

    async with upload_semaphore:
        if queued:
            await _safe_edit(status, "📥 **Slot acquired — starting upload…**")
        await process_upload(message, status)


async def process_upload(message: Message, status):
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
            await status.edit(
                "❌ **File too large**\n\n"
                f"Your file is **{format_bytes(file_size)}** — limit is **{MAX_FILE_MB} MB**"
            )
            return

    # ── Resolve filename early so we can parse metadata ──────────────
    if message.photo:
        original_name = f"{uuid.uuid4().hex}.jpg"
    elif hasattr(media, "file_name") and media.file_name:
        original_name = safe_filename(media.file_name)
    else:
        original_name = f"{uuid.uuid4().hex}.bin"

    caption_text = message.caption or message.text or ""
    meta = parse_caption(caption_text, original_name)

    # ── Download from Telegram with progress ─────────────────────────
    last_edit_time = 0.0

    async def download_progress(current: int, total: int):
        nonlocal last_edit_time
        now = time.monotonic()
        pct = current / total if total else 0
        tracker.update(file_id, current, stage="downloading")
        if now - last_edit_time < PROGRESS_EDIT_INTERVAL and current < total:
            return
        last_edit_time = now
        await _safe_edit(
            status,
            f"⬇️ **Downloading from Telegram…**\n"
            f"`{original_name}`\n\n"
            f"`{progress_bar(pct)}` {pct:.0%}\n"
            f"{format_bytes(current)} / {format_bytes(total)}"
        )

    await status.edit(
        f"⬇️ **Downloading from Telegram…**\n"
        f"`{original_name}`\n\n"
        f"`{'░' * 14}` 0%"
    )
    temp_path = await message.download(progress=download_progress)

    if not temp_path:
        tracker.complete(file_id, stage="failed")
        await status.edit("❌ Download failed")
        return

    file_size = file_size or os.path.getsize(temp_path)
    file_id = uuid.uuid4().hex[:12]
    ext = os.path.splitext(original_name)[1]

    transfer = tracker.start(
        file_id, original_name, file_size,
        message.from_user.id, "upload",
    )

    # ── Store ─────────────────────────────────────────────────────────
    # ── TTL / expiry (needed before metadata sidecar) ──────────────
    user_mode = get_mode(message.from_user.id)
    ttl = user_mode["ttl"] if user_mode["ttl"] > 0 else 0
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=ttl)
        if ttl > 0 else None
    )

    meta_dict = build_metadata_dict(
        meta, file_id, original_name, file_size, ttl, expires_at,
    )

    if STORAGE_BACKEND == "local":
        # Organize into subfolders locally too
        folder = sanitize_folder(meta.source) if meta.source else "_unsorted"
        dest_dir = os.path.join(UPLOAD_DIR, folder)
        os.makedirs(dest_dir, exist_ok=True)
        internal_path = os.path.join(dest_dir, f"{file_id}{ext}")
        os.replace(temp_path, internal_path)
        stored_path = internal_path
        _write_metadata_sidecar(internal_path, meta_dict)
    else:
        # ── S3 upload with progress ──────────────────────────────────
        key = build_s3_key(file_id, ext, meta)
        upload_total = os.path.getsize(temp_path)
        uploaded_so_far = 0
        last_s3_edit = 0.0
        loop = asyncio.get_running_loop()

        def s3_progress_callback(bytes_transferred: int):
            nonlocal uploaded_so_far, last_s3_edit
            uploaded_so_far += bytes_transferred
            tracker.update(file_id, uploaded_so_far, stage="uploading")
            now = time.monotonic()
            pct = uploaded_so_far / upload_total if upload_total else 0
            if now - last_s3_edit < PROGRESS_EDIT_INTERVAL and uploaded_so_far < upload_total:
                return
            last_s3_edit = now
            asyncio.run_coroutine_threadsafe(
                _safe_edit(
                    status,
                    f"⬆️ **Uploading to storage…**\n"
                    f"`{original_name}`\n\n"
                    f"`{progress_bar(pct)}` {pct:.0%}\n"
                    f"{format_bytes(uploaded_so_far)} / {format_bytes(upload_total)}"
                ),
                loop,
            )

        await status.edit(
            f"⬆️ **Uploading to storage…**\n"
            f"`{original_name}`\n\n"
            f"`{'░' * 14}` 0%"
        )
        await asyncio.to_thread(
            s3.upload_file,
            temp_path,
            AWS_S3_BUCKET_NAME,
            key,
            Callback=s3_progress_callback,
        )
        os.remove(temp_path)
        stored_path = key

        # Upload metadata sidecar to S3
        meta_key = key + ".meta.json"
        meta_body = json.dumps(meta_dict, indent=2).encode()
        await asyncio.to_thread(
            s3.put_object,
            Bucket=AWS_S3_BUCKET_NAME,
            Key=meta_key,
            Body=meta_body,
            ContentType="application/json",
        )

    # ── Persist to DB + cache ────────────────────────────────────────
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

    # ── Build the completion message ────────────────────────────────
    link = f"{BASE_URL}/file/{file_id}"

    lines = ["✅ **Upload complete**"]
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    # File details section
    lines.append(f"📄  `{original_name}`")
    lines.append(f"📦  {format_bytes(file_size)}")

    # Parsed metadata section
    meta_lines = []
    if meta.source:
        meta_lines.append(f"📂  Folder: `{sanitize_folder(meta.source)}/`")
    if meta.count:
        meta_lines.append(f"🔢  **{meta.count:,}** items")
    if meta.password:
        meta_lines.append(f"🔑  Password: `{meta.password}`")
    if meta.date_tag:
        meta_lines.append(f"📅  Date: {meta.date_tag}")
    if meta.channel:
        meta_lines.append(f"📡  Channel: {meta.channel}")

    if meta_lines:
        lines.append("")
        lines.extend(meta_lines)

    # Expiry section
    lines.append("")
    if ttl > 0:
        lines.append(f"⏳  Expires in **{format_ttl(ttl)}**")
    else:
        lines.append("♾  **No expiration**")

    # Link (always last, prominent)
    lines.append("")
    lines.append(f"🔗  `{link}`")

    tracker.complete(file_id, stage="complete")
    await status.edit("\n".join(lines))
