import os
from passlib.hash import argon2
from db.database import Database

async def bootstrap_admin():
    if os.getenv("ADMIN_ENABLED", "false").lower() != "true":
        return

    email = os.getenv("ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD")

    if not email or not password:
        return

    count = await Database.pool.fetchval(
        "SELECT COUNT(*) FROM admins"
    )

    if count > 0:
        return

    await Database.pool.execute(
        """
        INSERT INTO admins (email, password_hash)
        VALUES ($1, $2)
        """,
        email,
        argon2.hash(password),
    )

    print("✅ Admin bootstrapped (Argon2)")
