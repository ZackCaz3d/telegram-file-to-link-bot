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
from datetime import datetime, timezone
from db.database import Database
from cache.redis import redis_client

FILE_MAP = {}

CLEANUP_INTERVAL = 30

async def cleanup_expired_files():
    while True:
        try:
            async with Database.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT file_id, path
                    FROM files
                    WHERE expires_at IS NOT NULL
                      AND expires_at < (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
                    """
                )

                for row in rows:
                    file_id = row["file_id"]
                    path = row["path"]

                    try:
                        if os.path.exists(path):
                            os.remove(path)
                    except Exception:
                        pass

                    redis_client.delete(f"file:{file_id}")

                if rows:
                    await conn.execute(
                        """
                        DELETE FROM files
                        WHERE expires_at IS NOT NULL
                          AND expires_at < (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
                        """
                    )

        except Exception as e:
            print("❌ Cleanup error:", e)

        await asyncio.sleep(CLEANUP_INTERVAL)
