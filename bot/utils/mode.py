import re
from pyrogram import filters
from bot.bot import tg_client
from cache.redis import redis_client
from bot.utils.access import is_allowed

def get_mode(user_id: int) -> dict:
    data = redis_client.hgetall(f"mode:{user_id}")
    return {
        "ttl": int(data.get("ttl", 0)), 
    }


def parse_ttl(value: str) -> int:
    """
    Parse TTL string to seconds.
    Supported:
      30   -> 30 minutes
      2h   -> 2 hours
      1d   -> 1 day
      0    -> never expire
    """
    m = re.match(r"^(\d+)([mhd]?)$", value.lower())
    if not m:
        return -1

    amount, unit = m.groups()
    amount = int(amount)

    if amount == 0:
        return 0
    if unit == "h":
        return amount * 3600
    if unit == "d":
        return amount * 86400

    return amount * 60


def format_ttl(seconds: int) -> str:
    if seconds == 0:
        return "Never"
    if seconds < 60:
        return f"{seconds} seconds"
    if seconds < 3600:
        return f"{seconds // 60} minutes"
    if seconds < 86400:
        return f"{seconds // 3600} hours"
    return f"{seconds // 86400} days"


@tg_client.on_message(filters.private & filters.command("mode"))
async def mode_handler(_, message):
    if not message.from_user:
        return

    user_id = message.from_user.id
    if not is_allowed(user_id):
        await message.reply("🚫 Admin only")
        return

    args = message.text.split()
    key = f"mode:{user_id}"
    if len(args) == 1:
        user = get_mode(user_id)
        
        if user["ttl"] > 0:
            current = user["ttl"]
            source = "👤 Your TTL"
        else:
            current = 0
            source = "♾ No expiration"

        await message.reply(
            "📌 **Mode (TTL)**\n\n"
            f"Effective TTL: **{format_ttl(current)}**\n"
            f"{source}\n\n"
            "Set expiration for your uploads:\n"
            "`/mode ttl 30` → 30 minutes\n"
            "`/mode ttl 2h` → 2 hours\n"
            "`/mode ttl 1d` → 1 day\n"
            "`/mode ttl 0` → Never expire\n\n"
            "`/mode reset`"
        )
        return

    cmd = args[1].lower()

    if cmd == "ttl":
        if len(args) != 3:
            await message.reply("❌ Usage: `/mode ttl <minutes|h|d>`")
            return

        ttl_seconds = parse_ttl(args[2])

        if ttl_seconds < 0:
            await message.reply(
                "❌ Invalid TTL format\n\n"
                "Examples:\n"
                "`/mode ttl 30`\n"
                "`/mode ttl 2h`\n"
                "`/mode ttl 1d`\n"
                "`/mode ttl 0`"
            )
            return

        if ttl_seconds > 30 * 86400:
            await message.reply("❌ Max TTL is 30 days")
            return

        redis_client.hset(key, mapping={"ttl": ttl_seconds})

        await message.reply(
            "⏳ TTL disabled"
            if ttl_seconds == 0
            else f"⏳ TTL set to **{format_ttl(ttl_seconds)}**"
        )
        return
    
    if cmd == "reset":
        redis_client.delete(key)
        await message.reply("♻️ Mode reset (Never expire)")
        return

    await message.reply("❌ Unknown command")
