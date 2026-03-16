import os
import json
import asyncio
from datetime import datetime, timezone

import boto3
from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from passlib.hash import argon2

from db.database import Database
from admin.settings_store import get_setting, set_setting
from admin.auth import admin_required
from bot.utils.transfers import tracker
from cache.redis import redis_client
from config import (
    STORAGE_BACKEND,
    AWS_ENDPOINT_URL,
    AWS_S3_BUCKET_NAME,
    AWS_DEFAULT_REGION,
    BASE_URL,
    MAX_FILE_MB,
    MAX_CONCURRENT_TRANSFERS,
    GLOBAL_RATE_LIMIT_REQUESTS,
    GLOBAL_RATE_LIMIT_WINDOW,
    ALLOWED_USER_IDS,
)

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="admin/templates")

s3 = None
if STORAGE_BACKEND == "s3":
    s3 = boto3.client(
        "s3",
        endpoint_url=AWS_ENDPOINT_URL,
        region_name=AWS_DEFAULT_REGION,
    )


# ── Auth ─────────────────────────────────────────────────────────────────────

@router.get("")
async def admin_root():
    return RedirectResponse("/admin/", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    admin = await Database.pool.fetchrow(
        "SELECT id, password_hash FROM admins WHERE email=$1",
        email,
    )

    if not admin or not argon2.verify(password, admin["password_hash"]):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid credentials"},
            status_code=401,
        )

    request.session["admin_id"] = admin["id"]
    return RedirectResponse("/admin/", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


# ── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, auth=Depends(admin_required)):
    if isinstance(auth, RedirectResponse):
        return auth

    stats = await Database.pool.fetchrow("""
        SELECT
          COUNT(*) AS total_files,
          COALESCE(SUM(downloads), 0) AS total_downloads,
          COALESCE(SUM(file_size), 0) AS total_size,
          COUNT(*) FILTER (
            WHERE expires_at IS NULL OR expires_at > NOW()
          ) AS active_files,
          COUNT(*) FILTER (
            WHERE expires_at IS NOT NULL AND expires_at <= NOW()
          ) AS expired_files
        FROM files
    """)

    top_files = await Database.pool.fetch("""
        SELECT file_id, name, downloads, file_size
        FROM files
        ORDER BY downloads DESC
        LIMIT 5
    """)

    recent_files = await Database.pool.fetch("""
        SELECT file_id, name, created_at, file_size
        FROM files
        ORDER BY created_at DESC
        LIMIT 5
    """)

    expiring_files = await Database.pool.fetch("""
        SELECT file_id, name, expires_at
        FROM files
        WHERE expires_at IS NOT NULL AND expires_at > NOW()
        ORDER BY expires_at ASC
        LIMIT 5
    """)

    active_transfers = tracker.get_active()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "page": "dashboard",
            "stats": stats,
            "top_files": top_files,
            "recent_files": recent_files,
            "expiring_files": expiring_files,
            "active_transfers": active_transfers,
            "storage_backend": STORAGE_BACKEND,
        },
    )


# ── Files Management ─────────────────────────────────────────────────────────

@router.get("/files", response_class=HTMLResponse)
async def files_page(
    request: Request,
    q: str = "",
    status_filter: str = "all",
    sort: str = "created_desc",
    page_num: int = Query(1, alias="page", ge=1),
    auth=Depends(admin_required),
):
    if isinstance(auth, RedirectResponse):
        return auth

    per_page = 25
    offset = (page_num - 1) * per_page

    where_clauses = ["name ILIKE $1"]
    params = [f"%{q}%"]

    if status_filter == "active":
        where_clauses.append("(expires_at IS NULL OR expires_at > NOW())")
    elif status_filter == "expired":
        where_clauses.append("expires_at IS NOT NULL AND expires_at <= NOW()")
    elif status_filter == "permanent":
        where_clauses.append("expires_at IS NULL")

    where = " AND ".join(where_clauses)

    sort_map = {
        "created_desc": "created_at DESC",
        "created_asc": "created_at ASC",
        "downloads_desc": "downloads DESC",
        "name_asc": "name ASC",
        "size_desc": "file_size DESC NULLS LAST",
    }
    order = sort_map.get(sort, "created_at DESC")

    count_row = await Database.pool.fetchrow(
        f"SELECT COUNT(*) AS total FROM files WHERE {where}", *params
    )
    total = count_row["total"]

    files = await Database.pool.fetch(
        f"""SELECT file_id, path, name, downloads, file_size, expires_at, created_at
            FROM files WHERE {where}
            ORDER BY {order}
            LIMIT {per_page} OFFSET {offset}""",
        *params,
    )

    total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse(
        "files.html",
        {
            "request": request,
            "page": "files",
            "files": files,
            "query": q,
            "status_filter": status_filter,
            "sort": sort,
            "page_num": page_num,
            "total_pages": total_pages,
            "total_files": total,
            "base_url": BASE_URL,
            "now": datetime.now(timezone.utc),
        },
    )


@router.post("/file/{file_id}/delete")
async def delete_file(file_id: str, auth=Depends(admin_required)):
    if isinstance(auth, RedirectResponse):
        return auth

    row = await Database.pool.fetchrow(
        "SELECT path FROM files WHERE file_id=$1", file_id
    )

    if row:
        path = row["path"]
        try:
            if STORAGE_BACKEND == "local":
                if path and os.path.exists(path):
                    os.remove(path)
                meta_path = path + ".meta.json"
                if os.path.exists(meta_path):
                    os.remove(meta_path)
            elif s3:
                s3.delete_objects(
                    Bucket=AWS_S3_BUCKET_NAME,
                    Delete={
                        "Objects": [
                            {"Key": path},
                            {"Key": path + ".meta.json"},
                        ]
                    },
                )
        except Exception:
            pass

    await Database.pool.execute("DELETE FROM files WHERE file_id=$1", file_id)
    redis_client.delete(f"file:{file_id}")

    return RedirectResponse("/admin/files", status_code=303)


@router.post("/file/{file_id}/disable")
async def disable_file(file_id: str, auth=Depends(admin_required)):
    if isinstance(auth, RedirectResponse):
        return auth

    await Database.pool.execute(
        "UPDATE files SET expires_at = NOW() WHERE file_id=$1", file_id
    )
    redis_client.delete(f"file:{file_id}")

    return RedirectResponse("/admin/files", status_code=303)


@router.post("/files/bulk-delete")
async def bulk_delete(request: Request, auth=Depends(admin_required)):
    if isinstance(auth, RedirectResponse):
        return auth

    form = await request.form()
    file_ids = form.getlist("file_ids")

    for fid in file_ids:
        row = await Database.pool.fetchrow(
            "SELECT path FROM files WHERE file_id=$1", fid
        )
        if row:
            path = row["path"]
            try:
                if STORAGE_BACKEND == "local":
                    if path and os.path.exists(path):
                        os.remove(path)
                    meta_path = path + ".meta.json"
                    if os.path.exists(meta_path):
                        os.remove(meta_path)
                elif s3:
                    s3.delete_objects(
                        Bucket=AWS_S3_BUCKET_NAME,
                        Delete={
                            "Objects": [
                                {"Key": path},
                                {"Key": path + ".meta.json"},
                            ]
                        },
                    )
            except Exception:
                pass

        await Database.pool.execute("DELETE FROM files WHERE file_id=$1", fid)
        redis_client.delete(f"file:{fid}")

    return RedirectResponse("/admin/files", status_code=303)


# ── Storage Browser ──────────────────────────────────────────────────────────

@router.get("/storage", response_class=HTMLResponse)
async def storage_page(
    request: Request,
    prefix: str = "",
    auth=Depends(admin_required),
):
    if isinstance(auth, RedirectResponse):
        return auth

    folders = []
    files = []

    if STORAGE_BACKEND == "s3" and s3:
        paginator = s3.get_paginator("list_objects_v2")
        kwargs = {"Bucket": AWS_S3_BUCKET_NAME, "Delimiter": "/"}
        if prefix:
            kwargs["Prefix"] = prefix

        for page in paginator.paginate(**kwargs):
            for cp in page.get("CommonPrefixes", []):
                folder_name = cp["Prefix"]
                if prefix:
                    folder_name = folder_name[len(prefix):]
                folders.append({
                    "name": folder_name.rstrip("/"),
                    "prefix": cp["Prefix"],
                })

            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key == prefix:
                    continue
                name = key[len(prefix):] if prefix else key
                if name.endswith(".meta.json"):
                    continue
                files.append({
                    "key": key,
                    "name": name,
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                })

    elif STORAGE_BACKEND == "local":
        upload_dir = os.path.abspath("uploads")
        browse_path = os.path.join(upload_dir, prefix) if prefix else upload_dir

        if os.path.isdir(browse_path):
            for entry in sorted(os.listdir(browse_path)):
                full = os.path.join(browse_path, entry)
                rel = os.path.join(prefix, entry) if prefix else entry

                if os.path.isdir(full):
                    folders.append({
                        "name": entry,
                        "prefix": rel + "/",
                    })
                elif not entry.endswith(".meta.json"):
                    stat = os.stat(full)
                    files.append({
                        "key": rel,
                        "name": entry,
                        "size": stat.st_size,
                        "last_modified": datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).isoformat(),
                    })

    # Get total storage stats
    storage_stats = await Database.pool.fetchrow("""
        SELECT
          COALESCE(SUM(file_size), 0) AS total_size,
          COUNT(*) AS total_files
        FROM files
    """)

    return templates.TemplateResponse(
        "storage.html",
        {
            "request": request,
            "page": "storage",
            "folders": folders,
            "files": files,
            "prefix": prefix,
            "storage_backend": STORAGE_BACKEND,
            "storage_stats": storage_stats,
            "bucket_name": AWS_S3_BUCKET_NAME or "N/A",
        },
    )


@router.post("/storage/delete")
async def storage_delete(
    request: Request,
    key: str = Form(...),
    auth=Depends(admin_required),
):
    if isinstance(auth, RedirectResponse):
        return auth

    # Delete from storage
    try:
        if STORAGE_BACKEND == "s3" and s3:
            s3.delete_objects(
                Bucket=AWS_S3_BUCKET_NAME,
                Delete={
                    "Objects": [
                        {"Key": key},
                        {"Key": key + ".meta.json"},
                    ]
                },
            )
        elif STORAGE_BACKEND == "local":
            full_path = os.path.join(os.path.abspath("uploads"), key)
            if os.path.exists(full_path):
                os.remove(full_path)
            meta = full_path + ".meta.json"
            if os.path.exists(meta):
                os.remove(meta)
    except Exception:
        pass

    # Also remove from DB if this matches a stored path
    await Database.pool.execute("DELETE FROM files WHERE path=$1", key)

    prefix = "/".join(key.split("/")[:-1])
    redirect_prefix = f"?prefix={prefix}/" if prefix else ""
    return RedirectResponse(f"/admin/storage{redirect_prefix}", status_code=303)


# ── Active Transfers ─────────────────────────────────────────────────────────

@router.get("/transfers", response_class=HTMLResponse)
async def transfers_page(request: Request, auth=Depends(admin_required)):
    if isinstance(auth, RedirectResponse):
        return auth

    return templates.TemplateResponse(
        "transfers.html",
        {
            "request": request,
            "page": "transfers",
            "active": tracker.get_active(),
            "history": tracker.get_history(),
        },
    )


@router.get("/api/transfers", response_class=JSONResponse)
async def api_transfers(auth=Depends(admin_required)):
    if isinstance(auth, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    return {
        "active": tracker.get_active(),
        "history": tracker.get_history(),
    }


# ── Settings ─────────────────────────────────────────────────────────────────

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, auth=Depends(admin_required)):
    if isinstance(auth, RedirectResponse):
        return auth

    storage_stats = await Database.pool.fetchrow("""
        SELECT
          COALESCE(SUM(file_size), 0) AS used_bytes,
          COUNT(*) AS total_files,
          COALESCE(MAX(file_size), 0) AS largest_file
        FROM files
    """)

    settings = {
        "cleanup_enabled": await get_setting("cleanup_enabled", "true"),
        "default_max_downloads": await get_setting("default_max_downloads", "0"),
        "max_file_mb": await get_setting("max_file_mb", str(MAX_FILE_MB or 0)),
        "max_concurrent_transfers": await get_setting(
            "max_concurrent_transfers", str(MAX_CONCURRENT_TRANSFERS)
        ),
        "rate_limit_requests": await get_setting(
            "rate_limit_requests", str(GLOBAL_RATE_LIMIT_REQUESTS)
        ),
        "rate_limit_window": await get_setting(
            "rate_limit_window", str(GLOBAL_RATE_LIMIT_WINDOW)
        ),
        "allowed_user_ids": await get_setting(
            "allowed_user_ids",
            ",".join(map(str, ALLOWED_USER_IDS)) if ALLOWED_USER_IDS else "",
        ),
    }

    saved = request.query_params.get("saved") == "1"

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "page": "settings",
            "storage_stats": storage_stats,
            "settings": settings,
            "storage_backend": STORAGE_BACKEND,
            "base_url": BASE_URL,
            "bucket_name": AWS_S3_BUCKET_NAME or "N/A",
            "saved": saved,
        },
    )


@router.post("/settings/save")
async def save_settings(
    request: Request,
    auth=Depends(admin_required),
):
    if isinstance(auth, RedirectResponse):
        return auth

    form = await request.form()

    await set_setting("cleanup_enabled", "true" if form.get("cleanup_enabled") else "false")
    await set_setting("default_max_downloads", form.get("default_max_downloads", "0"))
    await set_setting("max_file_mb", form.get("max_file_mb", "0"))
    await set_setting("max_concurrent_transfers", form.get("max_concurrent_transfers", "3"))
    await set_setting("rate_limit_requests", form.get("rate_limit_requests", "60"))
    await set_setting("rate_limit_window", form.get("rate_limit_window", "10"))
    await set_setting("allowed_user_ids", form.get("allowed_user_ids", ""))

    return RedirectResponse("/admin/settings?saved=1", status_code=303)


@router.post("/settings/purge-expired")
async def purge_expired(auth=Depends(admin_required)):
    if isinstance(auth, RedirectResponse):
        return auth

    rows = await Database.pool.fetch("""
        SELECT file_id, path FROM files
        WHERE expires_at IS NOT NULL AND expires_at < NOW()
    """)

    for row in rows:
        path = row["path"]
        try:
            if STORAGE_BACKEND == "local":
                if path and os.path.exists(path):
                    os.remove(path)
                meta_path = path + ".meta.json"
                if os.path.exists(meta_path):
                    os.remove(meta_path)
            elif s3:
                s3.delete_objects(
                    Bucket=AWS_S3_BUCKET_NAME,
                    Delete={
                        "Objects": [
                            {"Key": path},
                            {"Key": path + ".meta.json"},
                        ]
                    },
                )
        except Exception:
            pass
        redis_client.delete(f"file:{row['file_id']}")

    await Database.pool.execute("""
        DELETE FROM files
        WHERE expires_at IS NOT NULL AND expires_at < NOW()
    """)

    return RedirectResponse("/admin/settings?saved=1", status_code=303)


# ── API Endpoints for AJAX ───────────────────────────────────────────────────

@router.get("/api/stats", response_class=JSONResponse)
async def api_stats(auth=Depends(admin_required)):
    if isinstance(auth, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    stats = await Database.pool.fetchrow("""
        SELECT
          COUNT(*) AS total_files,
          COALESCE(SUM(downloads), 0) AS total_downloads,
          COALESCE(SUM(file_size), 0) AS total_size,
          COUNT(*) FILTER (
            WHERE expires_at IS NULL OR expires_at > NOW()
          ) AS active_files
        FROM files
    """)

    return {
        "total_files": stats["total_files"],
        "total_downloads": stats["total_downloads"],
        "total_size": stats["total_size"],
        "active_files": stats["active_files"],
        "active_transfers": len(tracker.get_active()),
    }
