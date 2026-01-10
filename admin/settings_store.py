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
