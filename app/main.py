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
import asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from config import ADMIN_ENABLED
from admin.bootstrap import bootstrap_admin
from admin.routes import router as admin_router

from app.state import cleanup_expired_files
from api.routes import router as file_router
from bot.bot import tg_client
from db.database import Database
import bot.handlers

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

templates = Jinja2Templates(
    directory=os.path.join(BASE_DIR, "admin", "templates")
)

class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response: Response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable"
            )
        return response

app = FastAPI(title="Telegram File Link Bot")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "dev-secret"),
    same_site="lax",
    https_only=True,
)

app.include_router(file_router)

if ADMIN_ENABLED:
    app.include_router(admin_router)

app.mount(
    "/static",
    CachedStaticFiles(directory="static"),
    name="static",
)

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(
    request: Request,
    exc: HTTPException,
):
    context = {
        "request": request,
        "title": "Error",
        "icon": "⚠️",
        "message": exc.detail,
        "hint": None,
    }

    if exc.status_code == 404:
        context.update(
            title="File Not Found",
            icon="🔍",
            message="This download link is invalid or no longer available.",
            hint="The file may have expired or been deleted by the owner.",
        )

    elif exc.status_code == 403:
        context.update(
            title="Access Denied",
            icon="⛔",
            message="You are not allowed to access this file.",
        )

    return templates.TemplateResponse(
        "error.html",
        context,
        status_code=exc.status_code,
    )

async def start_bot():
    try:
        await tg_client.start()
        print("🤖 Pyrogram bot started")
    except Exception as e:
        print("⚠️ Bot start skipped:", e)


async def stop_bot():
    await tg_client.stop()
    print("🛑 Pyrogram bot stopped")

@app.on_event("startup")
async def startup():
    await Database.connect()

    if ADMIN_ENABLED:
        await bootstrap_admin()

    asyncio.create_task(start_bot())
    asyncio.create_task(cleanup_expired_files())


@app.on_event("shutdown")
async def shutdown():
    await Database.close()
    asyncio.create_task(stop_bot())
