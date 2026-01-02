from db.database import Database

async def get_setting(key: str, default: str):
    row = await Database.pool.fetchrow(
        "SELECT value FROM settings WHERE key=$1",
        key,
    )
    return row["value"] if row else default


async def set_setting(key: str, value: str):
    await Database.pool.execute(
        """
        INSERT INTO settings (key, value)
        VALUES ($1, $2)
        ON CONFLICT (key)
        DO UPDATE SET value = EXCLUDED.value
        """,
        key,
        value,
    )
