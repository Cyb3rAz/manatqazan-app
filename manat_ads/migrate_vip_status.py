"""
migrate_vip_status.py
=====================
Adds VIP subscription columns to the users table.

Run:
    python migrate_vip_status.py
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()

_raw_db_url = os.getenv("DATABASE_URL", "").strip()
if not _raw_db_url:
    _raw_db_url = f"sqlite+aiosqlite:///{Path(__file__).parent / 'manat_ads.db'}"
DATABASE_URL: str = _raw_db_url

MIGRATIONS = [
    (
        "vip_status",
        "ALTER TABLE users ADD COLUMN vip_status VARCHAR(20) NOT NULL DEFAULT 'free'",
    ),
    (
        "vip_expires_at",
        "ALTER TABLE users ADD COLUMN vip_expires_at DATETIME",
    ),
]


async def run():
    engine = create_async_engine(DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        # Get existing columns (sync inspection inside async context)
        existing_cols: list[str] = await conn.run_sync(
            lambda sync_conn: [col["name"] for col in inspect(sync_conn).get_columns("users")]
        )

        for col_name, ddl in MIGRATIONS:
            if col_name in existing_cols:
                print(f"[SKIP]  Column '{col_name}' already exists — skipping.")
            else:
                await conn.execute(text(ddl))
                print(f"[OK]    Column '{col_name}' added successfully.")

    await engine.dispose()
    print("\nMigration complete!")


if __name__ == "__main__":
    asyncio.run(run())
