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

from pyrogram import filters
from bot.bot import tg_client
from bot.utils.access import is_allowed

@tg_client.on_message(filters.private & filters.command("start"))
async def start_handler(_, message):
    if not message.from_user:
        return

    if not is_allowed(message.from_user.id):
        await message.reply("🚫 This bot is private.")
        return

    await message.reply(
        "👋 Send me a file and I’ll generate a download link.\n"
        "📎 Send images as *File* to keep original quality."
    )
