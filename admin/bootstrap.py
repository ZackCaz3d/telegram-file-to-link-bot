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
