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
